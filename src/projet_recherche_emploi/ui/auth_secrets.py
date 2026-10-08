"""Écrit la configuration de connexion Google de Streamlit à partir des variables d'environnement.

Streamlit ne lit cette configuration que dans .streamlit/secrets.toml, et il en a besoin dès son
démarrage pour reconnaître le cookie d'une session déjà ouverte. Ce module est donc lancé avant
Streamlit : python -m projet_recherche_emploi.ui.auth_secrets
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from projet_recherche_emploi.config import Settings
from projet_recherche_emploi.errors import ConfigurationError

SECRETS_PATH = Path(".streamlit") / "secrets.toml"
GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"

# Réglage -> clé de la section [auth] de Streamlit
AUTH_SETTINGS = {
    "auth_redirect_uri": "redirect_uri",
    "auth_cookie_secret": "cookie_secret",
    "google_client_id": "client_id",
    "google_client_secret": "client_secret",
}


def build_secrets(settings: Settings) -> str | None:
    """Renvoie le contenu de secrets.toml, ou None si la connexion Google n'est pas demandée."""
    values = {name: getattr(settings, name) for name in AUTH_SETTINGS}
    # AUTH_COOKIE_SECRET seul ne demande rien : il signe aussi les sessions de l'API, avec ou sans Google
    if not any(value for name, value in values.items() if name != "auth_cookie_secret"):
        return None

    # Un réglage porte le nom de sa variable d'environnement, en minuscules
    missing = [name.upper() for name, value in values.items() if not value]
    if not settings.owner_email:
        missing.append("OWNER_EMAIL")
    if missing:
        raise ConfigurationError(f"Connexion Google incomplète, variable(s) manquante(s) : {', '.join(missing)}")

    lines = ["[auth]"]
    # json.dumps produit une chaîne entre guillemets valide en TOML
    lines += [f"{AUTH_SETTINGS[name]} = {json.dumps(value)}" for name, value in values.items()]
    lines.append(f"server_metadata_url = {json.dumps(GOOGLE_METADATA_URL)}")
    return "\n".join(lines) + "\n"


def main() -> None:
    load_dotenv()
    try:
        secrets = build_secrets(Settings())
    except ConfigurationError as error:
        # Démarrer quand même ouvrirait l'application sans la connexion attendue
        sys.exit(str(error))

    if secrets is None:
        print("Connexion Google non configurée : l'accès reste protégé par APP_PASSWORD s'il est défini.")
        if SECRETS_PATH.exists():
            print(
                f"Attention : {SECRETS_PATH} existe encore et reste lu par Streamlit. "
                "Le supprimer pour la désactiver."
            )
        return

    SECRETS_PATH.parent.mkdir(exist_ok=True)
    SECRETS_PATH.write_text(secrets, encoding="utf-8")
    print(f"Connexion Google configurée dans {SECRETS_PATH}")


if __name__ == "__main__":
    main()
