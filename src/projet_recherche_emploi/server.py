"""Point d'entrée de l'interface : l'application Streamlit, plus les pages publiques en HTML simple.

Se lance avec : streamlit run src/projet_recherche_emploi/server.py
"""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from projet_recherche_emploi.public_pages import build_routes

load_dotenv()

app = st.App(Path(__file__).parent / "app.py", routes=build_routes(dict(os.environ)))
