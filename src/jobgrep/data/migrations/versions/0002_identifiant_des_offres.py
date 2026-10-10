"""Identifiant entier des offres : la clé de jobs passe du couple utilisateur + URL à une colonne id.

Une URL ne tient pas dans le chemin d'une route : avec un identifiant, l'API désigne une offre par /api/jobs/42.
Le couple utilisateur + URL reste unique, c'est lui qui écarte une offre déjà en base.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

from jobgrep.config import DEFAULT_USER_ID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

COPIED_COLUMNS = (
    "user_id, url, title, content, score, contract_type, query, match_reason, applied, applied_at, created_at, deleted"
)


def upgrade() -> None:
    # SQLite ne sait pas changer la clé primaire d'une table : on en crée une autre, on y recopie les lignes,
    # puis elle prend la place de l'ancienne
    op.create_table(
        "jobs_new",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False, server_default=sa.text(str(DEFAULT_USER_ID))),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("content", sa.Text),
        sa.Column("score", sa.REAL),
        sa.Column("contract_type", sa.Text),
        sa.Column("query", sa.Text),
        sa.Column("match_reason", sa.Text),
        sa.Column("applied", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("applied_at", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("user_id", "url"),
    )
    # Les colonnes sont nommées : une base ancienne peut les avoir dans un autre ordre.
    # Les identifiants suivent l'ordre d'arrivée des offres.
    op.execute(
        f"INSERT INTO jobs_new ({COPIED_COLUMNS}) SELECT {COPIED_COLUMNS} FROM jobs ORDER BY created_at, rowid"
    )
    op.drop_table("jobs")
    op.rename_table("jobs_new", "jobs")


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
