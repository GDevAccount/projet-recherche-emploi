import streamlit as st
from dotenv import load_dotenv

from projet_recherche_emploi.config import MAX_SEARCHES_PER_DAY, configure_logging
from projet_recherche_emploi.container import get_container
from projet_recherche_emploi.ui import views
from projet_recherche_emploi.ui.auth import authenticate, google_login_enabled, render_account


def main() -> None:
    load_dotenv()
    configure_logging()
    # Construit une seule fois par processus : Streamlit relance ce script à chaque interaction
    container = get_container()

    st.set_page_config(page_title="Recherche d'emploi", page_icon="💼", layout="wide")
    st.title("Recherche d'emploi")

    # Rien ne s'affiche avant ce contrôle
    user_id = authenticate(container.auth)
    if user_id is None:
        return

    with st.sidebar:
        if google_login_enabled():
            render_account()
        views.render_cv(user_id, container.cv)
        st.divider()
        views.render_queries(user_id, container.queries)

    can_search = container.search.can_search(user_id)
    remaining = container.search.remaining_searches(user_id)
    if st.button("Lancer une recherche", type="primary", disabled=not can_search or remaining == 0):
        views.run_search(user_id, container.search)
        remaining = container.search.remaining_searches(user_id)
    if not can_search:
        st.caption("Il faut un CV et au moins une recherche enregistrée pour lancer une recherche.")
    if remaining is not None:
        st.caption(f"Recherches restantes aujourd'hui : {remaining} sur {MAX_SEARCHES_PER_DAY}.")

    jobs_tab, rejected_tab = st.tabs(["Offres retenues", "Pages rejetées"])
    with jobs_tab:
        views.render_jobs(user_id, container.jobs)
    with rejected_tab:
        views.render_rejected_jobs(user_id, container.jobs)


main()
