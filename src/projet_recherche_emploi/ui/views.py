"""Écrans de l'interface. Chacun reçoit l'utilisateur et le service qu'il affiche : aucune règle métier ici."""

from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from projet_recherche_emploi.config import CONTRACT_TYPES, LOCAL_TIMEZONE
from projet_recherche_emploi.errors import AppError
from projet_recherche_emploi.schemas import REJECT_NOT_AN_OFFER, SearchProgress
from projet_recherche_emploi.services.cv_service import CvService
from projet_recherche_emploi.services.job_service import JobService
from projet_recherche_emploi.services.query_service import QueryService
from projet_recherche_emploi.services.search_service import SearchService

NOT_STATED = "non précisé"
REMOTE_LABEL = "télétravail complet"
ANYWHERE_LABEL = "toute la France"


def render_cv(user_id: int, cv: CvService) -> None:
    st.subheader("CV")

    uploaded_file = st.file_uploader("Déposer un CV (PDF)", type="pdf")
    # Le bouton évite de réécrire le fichier à chaque rechargement de la page
    if uploaded_file and st.button("Enregistrer ce CV"):
        try:
            cv.save_cv(user_id, uploaded_file.getvalue())
            st.success("CV enregistré")
        except AppError as error:
            st.error(str(error))

    updated_at = cv.get_status(user_id).updated_at
    if updated_at is None:
        st.warning("Aucun CV enregistré")
    else:
        local_time = updated_at.astimezone(ZoneInfo(LOCAL_TIMEZONE))
        st.caption(f"CV en place, mis à jour le {local_time:%d/%m/%Y à %H:%M}")


def render_queries(user_id: int, queries: QueryService) -> None:
    st.subheader("Postes recherchés")

    saved_queries = queries.list_queries(user_id)
    if not saved_queries:
        st.warning("Aucune recherche enregistrée")

    for query in saved_queries:
        text_column, button_column = st.columns([5, 1])
        place = REMOTE_LABEL if query.remote else query.location or ANYWHERE_LABEL
        text_column.markdown(f"**{query.contract_type}** · {query.query} · *{place}*")
        if button_column.button("✕", key=f"delete_query_{query.id}", help="Supprimer cette recherche"):
            try:
                queries.delete_query(user_id, query.id)
            except AppError:
                # Déjà supprimée depuis un autre onglet : le rechargement la fait disparaître
                pass
            st.rerun()

    with st.form("add_query", clear_on_submit=True):
        contract_type = st.selectbox(
            "Type de contrat", CONTRACT_TYPES, help="Ajouté à la recherche s'il n'y figure pas déjà."
        )
        text = st.text_input(
            "Recherche",
            placeholder="ingénieur IA générative LLM RAG",
            help="Le métier visé, suivi de ses spécialités. Seules les offres de ce métier sont retenues, "
            "même si votre CV en couvre d'autres. Inutile d'écrire le contrat ou le lieu : ils sont ajoutés.",
        )
        location = st.text_input(
            "Lieu",
            placeholder="Lyon, Bretagne, Île-de-France…",
            help="Ville, département ou région. Vide : toute la France.",
        )
        remote = st.checkbox(
            "Télétravail complet uniquement",
            help="Ne retient que les postes 100 % à distance, en France comme à l'étranger. Le lieu est alors ignoré.",
        )
        submitted = st.form_submit_button("Ajouter")

    if submitted:
        try:
            queries.add_query(user_id, contract_type, text, location, remote)
        except AppError as error:
            st.error(str(error))
        else:
            st.rerun()


def run_search(user_id: int, search: SearchService) -> None:
    with st.status("Recherche en cours, cela peut prendre quelques minutes…", expanded=True) as status:
        progress_bar = st.progress(0.0)

        def show_progress(event: SearchProgress) -> None:
            if event.total:
                progress_bar.progress(event.done / event.total, text=event.message)
            else:
                st.write(event.message)

        try:
            summary = search.run_search(user_id, show_progress)
        except Exception as error:
            status.update(label="La recherche a échoué", state="error")
            st.error(str(error))
            return
        progress_bar.empty()

        status.update(label="Recherche terminée", state="complete")
        st.write(
            f"{summary.found} page(s) trouvée(s), "
            f"{summary.new} pas encore évaluée(s), "
            f"{summary.kept} offre(s) retenue(s), "
            f"{summary.rejected} rejetée(s), "
            f"{summary.inserted} nouvelle(s) en base."
        )


def to_local_time(column: pd.Series) -> pd.Series:
    # Les dates sont enregistrées en UTC
    return pd.to_datetime(column, utc=True).dt.tz_convert(LOCAL_TIMEZONE).dt.tz_localize(None)


def render_jobs(user_id: int, jobs: JobService) -> None:
    saved_jobs = jobs.list_jobs(user_id)
    if not saved_jobs:
        st.info("Aucune offre en base pour l'instant : lancez une recherche.")
        return

    table = pd.DataFrame([job.model_dump() for job in saved_jobs])
    table["created_at"] = to_local_time(table["created_at"])
    table["applied_at"] = to_local_time(table["applied_at"])
    table["to_delete"] = False
    # Sans cela, le filtre par contrat masquerait les offres dont la page ne dit pas le contrat
    table["contract_type"] = table["contract_type"].fillna(NOT_STATED)
    table["work_location"] = table["work_location"].fillna(NOT_STATED)

    applied_count = int(table["applied"].sum())
    total_column, applied_column, remaining_column = st.columns(3)
    total_column.metric("Offres", len(table))
    applied_column.metric("Postulées", applied_count)
    remaining_column.metric("À traiter", len(table) - applied_count)

    contract_column, toggle_column = st.columns([3, 2])
    contract_types = sorted(table["contract_type"].unique())
    selected_types = contract_column.multiselect("Type de contrat", contract_types, default=contract_types)
    search_text = contract_column.text_input("Rechercher", placeholder="Nom d'entreprise, ville, mot-clé…").strip()
    hide_applied = toggle_column.toggle("Masquer les offres déjà postulées")

    visible = table[table["contract_type"].isin(selected_types)]
    if hide_applied:
        visible = visible[~visible["applied"]]
    if search_text:
        searched = (
            visible["title"].fillna("") + " " + visible["work_location"] + " " + visible["match_reason"].fillna("")
        )
        visible = visible[searched.str.contains(search_text, case=False, regex=False)]
        st.caption(f"{len(visible)} offre(s) pour « {search_text} »")

    columns = [
        "applied",
        "title",
        "contract_type",
        "work_location",
        "url",
        "match_reason",
        "created_at",
        "applied_at",
        "to_delete",
    ]
    # Sans clé, le tableau repart d'un état vierge dès que les données changent
    edited = st.data_editor(
        visible[columns],
        column_config={
            "applied": st.column_config.CheckboxColumn("Postulé"),
            "title": st.column_config.TextColumn("Offre", width="large"),
            "contract_type": st.column_config.TextColumn("Contrat"),
            "work_location": st.column_config.TextColumn("Lieu de travail"),
            "url": st.column_config.LinkColumn("Lien", display_text="Ouvrir"),
            "match_reason": st.column_config.TextColumn("Pourquoi ça correspond", width="large"),
            "created_at": st.column_config.DatetimeColumn("Trouvée le", format="DD/MM/YYYY HH:mm"),
            "applied_at": st.column_config.DatetimeColumn("Postulé le", format="DD/MM/YYYY HH:mm"),
            "to_delete": st.column_config.CheckboxColumn("Supprimer"),
        },
        disabled=[column for column in columns if column not in ("applied", "to_delete")],
        hide_index=True,
        width="stretch",
    )

    # Le tableau n'affiche pas l'identifiant : ses lignes sont celles de visible, dans le même ordre
    changed = edited["applied"].to_numpy() != visible["applied"].to_numpy()
    for job_id, applied in zip(visible["id"][changed], edited["applied"][changed], strict=True):
        try:
            jobs.set_applied(user_id, int(job_id), bool(applied))
        except AppError as error:
            st.error(str(error))
    if changed.any():
        st.rerun()

    # La suppression passe par un bouton : une coche seule ne doit pas suffire à faire disparaître une offre
    to_delete = visible["id"][edited["to_delete"].to_numpy()].tolist()
    if to_delete and st.button(f"Supprimer {len(to_delete)} offre(s)"):
        jobs.delete_jobs(user_id, to_delete)
        st.rerun()


def render_rejected_jobs(user_id: int, jobs: JobService) -> None:
    rejected_jobs = jobs.list_rejected_jobs(user_id)
    if not rejected_jobs:
        st.info("Aucune page rejetée en base pour l'instant.")
        return

    table = pd.DataFrame([job.model_dump() for job in rejected_jobs])
    table["created_at"] = to_local_time(table["created_at"])
    table["failed_criteria"] = table["failed_criteria"].str.join(", ")

    counts = table["motive"].value_counts()
    total_column, *motive_columns = st.columns(len(counts) + 1)
    total_column.metric("Pages rejetées", len(table))
    for column, (label, count) in zip(motive_columns, counts.items(), strict=True):
        column.metric(label, int(count))
    st.caption(
        f"« {REJECT_NOT_AN_OFFER} » regroupe les listes d'offres, les articles et les offres expirées. "
        "Le motif est le premier critère en défaut ; la colonne « Critères en défaut » les donne tous. "
        "Les pages écartées pour leur métier, leur contrat ou leur lieu sont réévaluées quand vous ajoutez "
        "une recherche."
    )

    motive_column, query_column = st.columns(2)
    motives = sorted(table["motive"].unique())
    selected_motives = motive_column.multiselect("Motif", motives, default=motives)
    queries = sorted(table["query"].dropna().unique())
    selected_queries = query_column.multiselect("Recherche d'origine", queries, default=queries)
    search_text = st.text_input("Rechercher", placeholder="Site, mot-clé de la raison…", key="rejected_search").strip()

    visible = table[table["motive"].isin(selected_motives) & table["query"].isin(selected_queries)]
    if search_text:
        searched = visible["title"] + " " + visible["url"] + " " + visible["reject_reason"].fillna("")
        visible = visible[searched.str.contains(search_text, case=False, regex=False)]
        st.caption(f"{len(visible)} page(s) pour « {search_text} »")

    st.dataframe(
        visible[
            [
                "motive",
                "title",
                "url",
                "reject_reason",
                "failed_criteria",
                "contract_type",
                "work_location",
                "query",
                "created_at",
            ]
        ],
        column_config={
            "motive": st.column_config.TextColumn("Motif"),
            "title": st.column_config.TextColumn("Page", width="large"),
            "url": st.column_config.LinkColumn("Lien", display_text="Ouvrir"),
            "reject_reason": st.column_config.TextColumn("Raison du rejet", width="large"),
            "failed_criteria": st.column_config.TextColumn("Critères en défaut"),
            "contract_type": st.column_config.TextColumn("Contrat"),
            "work_location": st.column_config.TextColumn("Lieu de travail"),
            "query": st.column_config.TextColumn("Recherche d'origine"),
            "created_at": st.column_config.DatetimeColumn("Rejetée le", format="DD/MM/YYYY HH:mm"),
        },
        hide_index=True,
        width="stretch",
    )
