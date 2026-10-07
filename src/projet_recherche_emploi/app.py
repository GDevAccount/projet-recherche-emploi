import hmac
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from projet_recherche_emploi.auth import resolve_user_id
from projet_recherche_emploi.config import DB_PATH, DEFAULT_USER_ID, MAX_SEARCHES_PER_DAY, cv_path
from projet_recherche_emploi.cv_reader import CV_reader
from projet_recherche_emploi.job_repository import JobRepository
from projet_recherche_emploi.query_repository import QueryRepository
from projet_recherche_emploi.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.search_run_repository import SearchRunRepository

load_dotenv()

CONTRACT_TYPES = ["CDI", "freelance", "CDD", "alternance", "stage"]
LOCAL_TIMEZONE = "Europe/Paris"
# Pages publiques en HTML simple, servies par server.py
LEGAL_LINKS = "[Règles de confidentialité](/confidentialite) · [Conditions d'utilisation](/conditions)"
REJECT_NOT_AN_OFFER = "Pas une offre valable"
REJECT_PROFILE_MISMATCH = "Hors profil"


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


def google_login_enabled() -> bool:
    # La section [auth] est écrite par auth_secrets.py quand les variables de connexion Google sont définies
    return st.secrets.load_if_toml_exists() and "auth" in st.secrets


def authenticate() -> int | None:
    """Renvoie l'utilisateur de la session, ou None tant que l'accès n'est pas autorisé."""
    if not google_login_enabled():
        # Sans comptes, toute session est celle de l'utilisateur par défaut
        return DEFAULT_USER_ID if check_password() else None

    if not st.user.is_logged_in:
        st.button("Se connecter avec Google", type="primary", on_click=st.login)
        st.caption(LEGAL_LINKS)
        return None

    email = st.user.get("email")
    # L'utilisateur est gardé en session : le chercher en base à chaque rechargement serait inutile
    if st.session_state.get("user_email") == email:
        return st.session_state["user_id"]

    try:
        user_id = resolve_user_id(DB_PATH, email, st.user.get("email_verified"))
    except ValueError as error:
        st.error(str(error))
        return None
    if user_id is None:
        st.error(f"L'adresse {email} n'est pas autorisée à utiliser cette application.")
        st.button("Se déconnecter", on_click=st.logout)
        return None

    st.session_state["user_email"] = email
    st.session_state["user_id"] = user_id
    return user_id


def render_account() -> None:
    st.caption(f"Connecté : {st.user.get('email')}")
    st.button("Se déconnecter", on_click=st.logout)
    st.caption(LEGAL_LINKS)
    st.divider()


def start_of_local_day() -> str:
    """Renvoie minuit du jour en cours à Paris, en UTC et au format des dates SQLite."""
    midnight = datetime.now(ZoneInfo(LOCAL_TIMEZONE)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def remaining_searches(user_id: int) -> int | None:
    """Renvoie le nombre de recherches encore permises aujourd'hui, ou None si l'utilisateur n'est pas limité."""
    # Le propriétaire paie les clés API : le quota ne protège que des recherches des invités
    if user_id == DEFAULT_USER_ID:
        return None
    used = SearchRunRepository(DB_PATH, user_id).count_runs_since(start_of_local_day())
    return max(0, MAX_SEARCHES_PER_DAY - used)


def render_cv(user_id: int) -> bool:
    """Affiche le dépôt du CV et renvoie vrai si un CV est en place."""
    st.subheader("CV")

    uploaded_file = st.file_uploader("Déposer un CV (PDF)", type="pdf")
    # Le bouton évite de réécrire le fichier à chaque rechargement de la page
    if uploaded_file and st.button("Enregistrer ce CV"):
        try:
            CV_reader(cv_path(user_id)).save_cv(uploaded_file.getvalue())
            # Les rejets valaient pour l'ancien CV : ces pages peuvent convenir au nouveau
            RejectedJobRepository(DB_PATH, user_id).clear()
            st.success("CV enregistré")
        except ValueError as error:
            st.error(str(error))

    cv_file = cv_path(user_id)
    if not cv_file.is_file():
        st.warning("Aucun CV enregistré")
        return False

    updated_at = datetime.fromtimestamp(cv_file.stat().st_mtime)
    st.caption(f"CV en place, mis à jour le {updated_at:%d/%m/%Y à %H:%M}")
    return True


def render_queries(user_id: int) -> bool:
    """Affiche les recherches enregistrées et renvoie vrai s'il y en a au moins une."""
    st.subheader("Postes recherchés")
    repository = QueryRepository(DB_PATH, user_id)

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


def run_search(user_id: int) -> None:
    # Le lancement est compté avant la recherche : même en échec, elle a pu consommer des crédits
    limit = None if user_id == DEFAULT_USER_ID else MAX_SEARCHES_PER_DAY
    if not SearchRunRepository(DB_PATH, user_id).record_run(start_of_local_day(), limit):
        st.error("Quota de recherches atteint pour aujourd'hui.")
        return

    with st.status("Recherche en cours, cela peut prendre quelques minutes…", expanded=True) as status:
        try:
            # Import local : importer main.py construit le graph et régénère graph.png
            from projet_recherche_emploi.main import app as graph

            progress_bar = st.progress(0.0)
            result = {}
            # Le mode « custom » remonte l'avancement écrit par les nœuds, « values » l'état du graph
            for mode, chunk in graph.stream({"user_id": user_id}, stream_mode=["custom", "values"]):
                if mode == "values":
                    result = chunk
                elif chunk.get("total"):
                    progress_bar.progress(chunk["done"] / chunk["total"], text=chunk["message"])
                else:
                    st.write(chunk["message"])
            progress_bar.empty()
        except Exception as error:
            status.update(label="La recherche a échoué", state="error")
            st.error(str(error))
            return

        status.update(label="Recherche terminée", state="complete")
        st.write(
            f"{len(result.get('jobs', []))} page(s) trouvée(s), "
            f"{len(result.get('new_jobs', []))} pas encore évaluée(s), "
            f"{len(result.get('filtered_jobs', []))} offre(s) retenue(s), "
            f"{len(result.get('rejected_jobs', []))} rejetée(s), "
            f"{result.get('inserted_count', 0)} nouvelle(s) en base."
        )


def to_local_time(column: pd.Series) -> pd.Series:
    # SQLite enregistre les dates en UTC
    return pd.to_datetime(column, utc=True).dt.tz_convert(LOCAL_TIMEZONE).dt.tz_localize(None)


def render_jobs(user_id: int) -> None:
    repository = JobRepository(DB_PATH, user_id)

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
        repository.set_applied(job.url, bool(job.applied))
    if not changed.empty:
        st.rerun()

    # La suppression passe par un bouton : une coche seule ne doit pas suffire à faire disparaître une offre
    to_delete = edited[edited["to_delete"]]
    if not to_delete.empty and st.button(f"Supprimer {len(to_delete)} offre(s)"):
        repository.delete_jobs(to_delete["url"].tolist())
        st.rerun()


def render_rejected_jobs(user_id: int) -> None:
    rejected_jobs = RejectedJobRepository(DB_PATH, user_id).list_rejected_jobs()
    if not rejected_jobs:
        st.info("Aucune page rejetée en base pour l'instant.")
        return

    table = pd.DataFrame(rejected_jobs)
    table["created_at"] = to_local_time(table["created_at"])
    # Une page qui n'est pas une offre n'a pas de profil à comparer : ce motif passe en premier
    table["motive"] = REJECT_NOT_AN_OFFER
    table.loc[table["is_real_offer"] == 1, "motive"] = REJECT_PROFILE_MISMATCH

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


def main() -> None:
    st.set_page_config(page_title="Recherche d'emploi", page_icon="💼", layout="wide")
    st.title("Recherche d'emploi")

    user_id = authenticate()
    if user_id is None:
        return

    with st.sidebar:
        if google_login_enabled():
            render_account()
        has_cv = render_cv(user_id)
        st.divider()
        has_queries = render_queries(user_id)

    remaining = remaining_searches(user_id)
    can_search = has_cv and has_queries and remaining != 0
    if st.button("Lancer une recherche", type="primary", disabled=not can_search):
        run_search(user_id)
        remaining = remaining_searches(user_id)
    if not (has_cv and has_queries):
        st.caption("Il faut un CV et au moins une recherche enregistrée pour lancer une recherche.")
    if remaining is not None:
        st.caption(f"Recherches restantes aujourd'hui : {remaining} sur {MAX_SEARCHES_PER_DAY}.")

    jobs_tab, rejected_tab = st.tabs(["Offres retenues", "Pages rejetées"])
    with jobs_tab:
        render_jobs(user_id)
    with rejected_tab:
        render_rejected_jobs(user_id)


main()
