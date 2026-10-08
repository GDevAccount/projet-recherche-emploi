"""Écrans de l'interface. Chacun reçoit l'utilisateur et le service qu'il affiche : aucune règle métier ici."""

from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from projet_recherche_emploi.config import CONTRACT_TYPES, LOCAL_TIMEZONE
from projet_recherche_emploi.errors import AppError
from projet_recherche_emploi.schemas import SearchProgress
from projet_recherche_emploi.services.cv_service import CvService
from projet_recherche_emploi.services.job_service import JobService
from projet_recherche_emploi.services.query_service import QueryService
from projet_recherche_emploi.services.search_service import SearchService

REJECT_NOT_AN_OFFER = "Pas une offre valable"
REJECT_PROFILE_MISMATCH = "Hors profil"


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
        text_column.markdown(f"**{query.contract_type}** · {query.query}")
        if button_column.button("✕", key=f"delete_query_{query.id}", help="Supprimer cette recherche"):
            try:
                queries.delete_query(user_id, query.id)
            except AppError:
                # Déjà supprimée depuis un autre onglet : le rechargement la fait disparaître
                pass
            st.rerun()

    with st.form("add_query", clear_on_submit=True):
        contract_type = st.selectbox("Type de contrat", CONTRACT_TYPES)
        text = st.text_input("Recherche", placeholder="offre d'emploi data engineer en CDI à Lyon")
        submitted = st.form_submit_button("Ajouter")

    if submitted:
        try:
            queries.add_query(user_id, contract_type, text)
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

    applied_count = int(table["applied"].sum())
    total_column, applied_column, remaining_column = st.columns(3)
    total_column.metric("Offres", len(table))
    applied_column.metric("Postulées", applied_count)
    remaining_column.metric("À traiter", len(table) - applied_count)

    contract_column, toggle_column = st.columns([3, 2])
    contract_types = sorted(table["contract_type"].dropna().unique())
    selected_types = contract_column.multiselect("Type de contrat", contract_types, default=contract_types)
    search_text = contract_column.text_input("Rechercher", placeholder="Nom d'entreprise, mot-clé…").strip()
    hide_applied = toggle_column.toggle("Masquer les offres déjà postulées")

    visible = table[table["contract_type"].isin(selected_types)]
    if hide_applied:
        visible = visible[~visible["applied"]]
    if search_text:
        searched = visible["title"].fillna("") + " " + visible["match_reason"].fillna("")
        visible = visible[searched.str.contains(search_text, case=False, regex=False)]
        st.caption(f"{len(visible)} offre(s) pour « {search_text} »")

    columns = ["applied", "title", "contract_type", "url", "match_reason", "created_at", "applied_at", "to_delete"]
    # Sans clé, le tableau repart d'un état vierge dès que les données changent
    edited = st.data_editor(
        visible[columns],
        column_config={
            "applied": st.column_config.CheckboxColumn("Postulé"),
            "title": st.column_config.TextColumn("Offre", width="large"),
            "contract_type": st.column_config.TextColumn("Contrat"),
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

    changed = edited[edited["applied"].to_numpy() != visible["applied"].to_numpy()]
    for job in changed.itertuples():
        try:
            jobs.set_applied(user_id, job.url, bool(job.applied))
        except AppError as error:
            st.error(str(error))
    if not changed.empty:
        st.rerun()

    # La suppression passe par un bouton : une coche seule ne doit pas suffire à faire disparaître une offre
    to_delete = edited[edited["to_delete"]]
    if not to_delete.empty and st.button(f"Supprimer {len(to_delete)} offre(s)"):
        jobs.delete_jobs(user_id, to_delete["url"].tolist())
        st.rerun()


def render_rejected_jobs(user_id: int, jobs: JobService) -> None:
    rejected_jobs = jobs.list_rejected_jobs(user_id)
    if not rejected_jobs:
        st.info("Aucune page rejetée en base pour l'instant.")
        return

    table = pd.DataFrame([job.model_dump() for job in rejected_jobs])
    table["created_at"] = to_local_time(table["created_at"])
    # Une page qui n'est pas une offre n'a pas de profil à comparer : ce motif passe en premier
    table["motive"] = REJECT_NOT_AN_OFFER
    table.loc[table["is_real_offer"], "motive"] = REJECT_PROFILE_MISMATCH

    not_an_offer_count = int((table["motive"] == REJECT_NOT_AN_OFFER).sum())
    total_column, offer_column, profile_column = st.columns(3)
    total_column.metric("Pages rejetées", len(table))
    offer_column.metric(REJECT_NOT_AN_OFFER, not_an_offer_count)
    profile_column.metric(REJECT_PROFILE_MISMATCH, len(table) - not_an_offer_count)
    st.caption(
        f"« {REJECT_NOT_AN_OFFER} » regroupe les listes d'offres, les articles, les offres expirées "
        "et les offres hors région parisienne : la colonne « Raison du rejet » précise le cas."
    )

    motive_column, query_column = st.columns(2)
    motives = sorted(table["motive"].unique())
    selected_motives = motive_column.multiselect("Motif", motives, default=motives)
    queries = sorted(table["query"].dropna().unique())
    selected_queries = query_column.multiselect("Recherche d'origine", queries, default=queries)
    search_text = st.text_input(
        "Rechercher", placeholder="Site, mot-clé de la raison…", key="rejected_search"
    ).strip()

    visible = table[table["motive"].isin(selected_motives) & table["query"].isin(selected_queries)]
    if search_text:
        searched = visible["title"] + " " + visible["url"] + " " + visible["reject_reason"].fillna("")
        visible = visible[searched.str.contains(search_text, case=False, regex=False)]
        st.caption(f"{len(visible)} page(s) pour « {search_text} »")

    st.dataframe(
        visible[["motive", "title", "url", "reject_reason", "contract_type", "query", "created_at"]],
        column_config={
            "motive": st.column_config.TextColumn("Motif"),
            "title": st.column_config.TextColumn("Page", width="large"),
            "url": st.column_config.LinkColumn("Lien", display_text="Ouvrir"),
            "reject_reason": st.column_config.TextColumn("Raison du rejet", width="large"),
            "contract_type": st.column_config.TextColumn("Contrat"),
            "query": st.column_config.TextColumn("Recherche d'origine"),
            "created_at": st.column_config.DatetimeColumn("Rejetée le", format="DD/MM/YYYY HH:mm"),
        },
        hide_index=True,
        width="stretch",
    )
