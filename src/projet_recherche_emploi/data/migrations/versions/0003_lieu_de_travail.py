"""Lieu de travail : une recherche vise un lieu ou le télétravail complet, une offre porte le lieu lu sur sa page.

Une page rejetée garde aussi le détail du verdict : métier recherché, contrat, compétences, niveau, lieu.

Jusqu'ici, le modèle rejetait toute offre hors Île-de-France. Les recherches existantes gardent ce lieu.
La même phrase peut désormais être enregistrée pour plusieurs lieux : l'unicité de search_queries s'étend
au lieu et au télétravail.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

from projet_recherche_emploi.config import DEFAULT_USER_ID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Lieu que le prompt imposait à toutes les recherches avant cette migration
FORMER_LOCATION = "Île-de-France"

COPIED_COLUMNS = "id, user_id, contract_type, query, created_at"


def upgrade() -> None:
    op.add_column("jobs", sa.Column("work_location", sa.Text))
    op.add_column("rejected_jobs", sa.Column("work_location", sa.Text))
    op.add_column("rejected_jobs", sa.Column("matches_location", sa.Integer))
    # Le verdict du filtre, critère par critère : vides pour les pages rejetées avant cette migration
    for criterion in ("matches_search", "matches_contract", "matches_skills", "matches_level"):
        op.add_column("rejected_jobs", sa.Column(criterion, sa.Integer))

    # SQLite ne sait pas changer une contrainte d'unicité : on crée une autre table, on y recopie les lignes,
    # puis elle prend la place de l'ancienne
    op.create_table(
        "search_queries_new",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False, server_default=sa.text(str(DEFAULT_USER_ID))),
        sa.Column("contract_type", sa.Text, nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("location", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("remote", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", "query", "location", "remote"),
    )
    op.execute(
        sa.text(
            f"INSERT INTO search_queries_new ({COPIED_COLUMNS}, location) "
            f"SELECT {COPIED_COLUMNS}, :location FROM search_queries ORDER BY id"
        ).bindparams(location=FORMER_LOCATION)
    )
    op.drop_table("search_queries")
    op.rename_table("search_queries_new", "search_queries")


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
