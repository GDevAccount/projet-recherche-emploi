# Le front Angular est construit à part : l'image finale ne contient ni Node ni node_modules
FROM node:22-slim AS frontend

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
# Clé de licence PrimeNG, passée par « fly deploy --build-arg ». Vide : le front affiche un bandeau de licence
ARG PRIMEUI_LICENSE=""
RUN npm run build -- --define "PRIMEUI_LICENSE='${PRIMEUI_LICENSE}'"

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock .python-version README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Emplacement par défaut de FRONTEND_DIR (config.py)
COPY --from=frontend /frontend/dist ./frontend/dist

# Base SQLite et CV : monter un volume persistant sur ce dossier
ENV DATA_DIR=/data
RUN mkdir -p /data

EXPOSE 8000

# La base est migrée et la configuration de connexion contrôlée avant de servir : une migration qui échoue,
# ou une connexion à moitié réglée, arrête le déploiement au lieu de casser la première visite
CMD ["sh", "-c", "uv run --no-sync projet-recherche-emploi migrate && exec uv run --no-sync projet-recherche-emploi serve"]
