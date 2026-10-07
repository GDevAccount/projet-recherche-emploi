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
CMD ["sh", "-c", "uv run --no-sync python -m projet_recherche_emploi.auth_secrets && exec uv run --no-sync streamlit run src/projet_recherche_emploi/server.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true"]
