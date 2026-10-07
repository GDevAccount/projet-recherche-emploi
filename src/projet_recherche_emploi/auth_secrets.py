"""Écrit la configuration de connexion Google de Streamlit à partir des variables d'environnement.

Streamlit ne lit cette configuration que dans .streamlit/secrets.toml, et il en a besoin dès son
démarrage pour reconnaître le cookie d'une session déjà ouverte. Ce module est donc lancé avant
Streamlit : python -m projet_recherche_emploi.auth_secrets
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

SECRETS_PATH = Path(".streamlit") / "secrets.toml"
GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"

# Variable d'environnement -> clé de la section [auth] de Streamlit
AUTH_VARIABLES = {
    "AUTH_REDIRECT_URI": "redirect_uri",
    "AUTH_COOKIE_SECRET": "cookie_secret",
    "GOOGLE_CLIENT_ID": "client_id",
    "GOOGLE_CLIENT_SECRET": "client_secret",
}


def build_secrets(environment: dict[str, str]) -> str | None:
    """Renvoie le contenu de secrets.toml, ou None si la connexion Google n'est pas demandée."""
    values = {name: environment.get(name, "").strip() for name in AUTH_VARIABLES}
    if not any(values.values()):
        return None

    missing = [name for name, value in values.items() if not value]
    if not environment.get("OWNER_EMAIL", "").strip():
        missing.append("OWNER_EMAIL")
    if missing:
        raise ValueError(f"Connexion Google incomplète, variable(s) manquante(s) : {', '.join(missing)}")

    lines = ["[auth]"]
    # json.dumps produit une chaîne entre guillemets valide en TOML
    lines += [f"{AUTH_VARIABLES[name]} = {json.dumps(value)}" for name, value in values.items()]
    lines.append(f"server_metadata_url = {json.dumps(GOOGLE_METADATA_URL)}")
    return "\n".join(lines) + "\n"


def main() -> None:
    load_dotenv()
    try:
        secrets = build_secrets(dict(os.environ))
    except ValueError as error:
        # Démarrer quand même ouvrirait l'application sans la connexion attendue
        sys.exit(str(error))

    if secrets is None:
        print("Connexion Google non configurée : l'accès reste protégé par APP_PASSWORD s'il est défini.")
        if SECRETS_PATH.exists():
            print(f"Attention : {SECRETS_PATH} existe encore et reste lu par Streamlit. Le supprimer pour la désactiver.")
        return

    SECRETS_PATH.parent.mkdir(exist_ok=True)
    SECRETS_PATH.write_text(secrets, encoding="utf-8")
    print(f"Connexion Google configurée dans {SECRETS_PATH}")


if __name__ == "__main__":
    main()
