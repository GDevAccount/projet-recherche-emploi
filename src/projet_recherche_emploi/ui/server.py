"""Point d'entrée du serveur en ligne : l'interface Streamlit, l'API sous /api, et les pages publiques.

Tout tient dans un seul processus, à une seule adresse : la base est un fichier sur un volume qui n'est pas
partagé entre machines, et le front qui remplacera Streamlit appellera l'API sans changer d'origine.

Se lance avec : streamlit run src/projet_recherche_emploi/ui/server.py
"""

from pathlib import Path

import streamlit as st

from projet_recherche_emploi.api.main import ApiRoute, create_app
from projet_recherche_emploi.api.public_pages import build_routes

# Charge .env et construit l'application du processus : l'interface et l'API partagent les mêmes services
api = create_app()

app = st.App(
    Path(__file__).parent / "app.py",
    routes=[ApiRoute(api), *build_routes(api.state.container.settings)],
)
