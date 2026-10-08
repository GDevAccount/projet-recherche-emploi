FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock .python-version README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Base SQLite et CV : monter un volume persistant sur ce dossier
ENV DATA_DIR=/data
RUN mkdir -p /data

EXPOSE 8501

# La configuration de connexion Google doit exister avant le démarrage de Streamlit (voir auth_secrets.py)
# La base est migrée avant aussi : une migration qui échoue arrête le déploiement au lieu de casser la première visite
CMD ["sh", "-c", "uv run --no-sync python -m projet_recherche_emploi.ui.auth_secrets && uv run --no-sync projet-recherche-emploi migrate && exec uv run --no-sync streamlit run src/projet_recherche_emploi/ui/server.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true"]
