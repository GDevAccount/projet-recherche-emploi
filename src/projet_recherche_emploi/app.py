import hmac
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from projet_recherche_emploi.config import CV_PATH, DB_PATH
from projet_recherche_emploi.cv_reader import CV_reader
from projet_recherche_emploi.job_repository import JobRepository
from projet_recherche_emploi.query_repository import QueryRepository

CONTRACT_TYPES = ["CDI", "freelance", "CDD", "alternance", "stage"]
LOCAL_TIMEZONE = "Europe/Paris"


def check_password() -> bool:
    """Demande le mot de passe si APP_PASSWORD est défini, et renvoie vrai une fois l'accès autorisé."""
    expected_password = os.environ.get("APP_PASSWORD")
    if not expected_password or st.session_state.get("authenticated"):
        return True

    entered_password = st.text_input("Mot de passe", type="password")
    if entered_password:
        if hmac.compare_digest(entered_password.encode(), expected_password.encode()):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Mot de passe incorrect")
    return False


def render_cv() -> bool:
    """Affiche le dépôt du CV et renvoie vrai si un CV est en place."""
    st.subheader("CV")

    uploaded_file = st.file_uploader("Déposer un CV (PDF)", type="pdf")
    # Le bouton évite de réécrire le fichier à chaque rechargement de la page
    if uploaded_file and st.button("Enregistrer ce CV"):
        try:
            CV_reader(CV_PATH).save_cv(uploaded_file.getvalue())
            st.success("CV enregistré")
        except ValueError as error:
            st.error(str(error))

    cv_path = Path(CV_PATH)
    if not cv_path.is_file():
        st.warning("Aucun CV enregistré")
        return False

    updated_at = datetime.fromtimestamp(cv_path.stat().st_mtime)
    st.caption(f"CV en place, mis à jour le {updated_at:%d/%m/%Y à %H:%M}")
    return True


def render_queries() -> bool:
    """Affiche les recherches enregistrées et renvoie vrai s'il y en a au moins une."""
    st.subheader("Postes recherchés")
    repository = QueryRepository(DB_PATH)

    queries = repository.list_queries()
    if not queries:
        st.warning("Aucune recherche enregistrée")

    for query in queries:
        text_column, button_column = st.columns([5, 1])
        text_column.markdown(f"**{query['contract_type']}** · {query['query']}")
        if button_column.button("✕", key=f"delete_query_{query['id']}", help="Supprimer cette recherche"):
            repository.delete_query(query["id"])
            st.rerun()

    with st.form("add_query", clear_on_submit=True):
        contract_type = st.selectbox("Type de contrat", CONTRACT_TYPES)
        text = st.text_input("Recherche", placeholder="offre d'emploi data engineer en CDI à Lyon")
        submitted = st.form_submit_button("Ajouter")

    if submitted:
        if not text.strip():
            st.error("La recherche est vide")
        elif repository.add_query(contract_type, text.strip()):
            st.rerun()
        else:
            st.warning("Cette recherche existe déjà")

    return bool(queries)


def run_search() -> None:
    with st.status("Recherche en cours, cela peut prendre quelques minutes…", expanded=True) as status:
        try:
            # Import local : importer main.py construit le graph et régénère graph.png
            from projet_recherche_emploi.main import app as graph

            result = graph.invoke({})
        except Exception as error:
            status.update(label="La recherche a échoué", state="error")
            st.error(str(error))
            return

        status.update(label="Recherche terminée", state="complete")
        st.write(
            f"{len(result.get('jobs', []))} page(s) trouvée(s), "
            f"{len(result.get('filtered_jobs', []))} offre(s) retenue(s), "
            f"{result.get('inserted_count', 0)} nouvelle(s) en base."
        )


def to_local_time(column: pd.Series) -> pd.Series:
    # SQLite enregistre les dates en UTC
    return pd.to_datetime(column, utc=True).dt.tz_convert(LOCAL_TIMEZONE).dt.tz_localize(None)


def render_jobs() -> None:
    repository = JobRepository(DB_PATH)

    jobs = repository.list_jobs()
    if not jobs:
        st.info("Aucune offre en base pour l'instant : lancez une recherche.")
        return

    table = pd.DataFrame(jobs)
    table["applied"] = table["applied"].astype(bool)
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
    hide_applied = toggle_column.toggle("Masquer les offres déjà postulées")

    visible = table[table["contract_type"].isin(selected_types)]
    if hide_applied:
        visible = visible[~visible["applied"]]

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
        repository.set_applied(job.url, bool(job.applied))
    if not changed.empty:
        st.rerun()

    # La suppression passe par un bouton : une coche seule ne doit pas suffire à faire disparaître une offre
    to_delete = edited[edited["to_delete"]]
    if not to_delete.empty and st.button(f"Supprimer {len(to_delete)} offre(s)"):
        repository.delete_jobs(to_delete["url"].tolist())
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Recherche d'emploi", page_icon="💼", layout="wide")
    st.title("Recherche d'emploi")

    if not check_password():
        return

    with st.sidebar:
        has_cv = render_cv()
        st.divider()
        has_queries = render_queries()

    if st.button("Lancer une recherche", type="primary", disabled=not (has_cv and has_queries)):
        run_search()
    if not (has_cv and has_queries):
        st.caption("Il faut un CV et au moins une recherche enregistrée pour lancer une recherche.")

    render_jobs()


main()
