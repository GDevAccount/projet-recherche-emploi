import streamlit as st

from projet_recherche_emploi.config import DEFAULT_USER_ID
from projet_recherche_emploi.errors import AppError
from projet_recherche_emploi.services.auth_service import AuthService

# Pages publiques en HTML simple, servies par server.py
LEGAL_LINKS = "[Règles de confidentialité](/confidentialite) · [Conditions d'utilisation](/conditions)"


def google_login_enabled() -> bool:
    # La section [auth] est écrite par auth_secrets.py quand les variables de connexion Google sont définies
    return st.secrets.load_if_toml_exists() and "auth" in st.secrets


def authenticate(auth: AuthService) -> int | None:
    """Renvoie l'utilisateur de la session, ou None tant que l'accès n'est pas autorisé."""
    if not google_login_enabled():
        # Sans comptes, toute session est celle de l'utilisateur par défaut
        return DEFAULT_USER_ID if _check_password(auth) else None

    if not st.user.is_logged_in:
        st.button("Se connecter avec Google", type="primary", on_click=st.login)
        st.caption(LEGAL_LINKS)
        return None

    email = st.user.get("email")
    # L'utilisateur est gardé en session : le chercher en base à chaque rechargement serait inutile
    if st.session_state.get("user_email") == email:
        return st.session_state["user_id"]

    try:
        user_id = auth.resolve_user_id(email, st.user.get("email_verified"))
    except AppError as error:
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


def _check_password(auth: AuthService) -> bool:
    """Demande le mot de passe si APP_PASSWORD est défini, et renvoie vrai une fois l'accès autorisé."""
    if not auth.password_required or st.session_state.get("authenticated"):
        return True

    entered_password = st.text_input("Mot de passe", type="password")
    if entered_password:
        if auth.password_matches(entered_password):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Mot de passe incorrect")
    return False
