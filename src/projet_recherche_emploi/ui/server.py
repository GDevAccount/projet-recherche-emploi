"""Point d'entrée de l'interface : l'application Streamlit, plus les pages publiques en HTML simple.

Se lance avec : streamlit run src/projet_recherche_emploi/ui/server.py
"""

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from projet_recherche_emploi.api.public_pages import build_routes
from projet_recherche_emploi.config import Settings

load_dotenv()

app = st.App(Path(__file__).parent / "app.py", routes=build_routes(Settings()))
