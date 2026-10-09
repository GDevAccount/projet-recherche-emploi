"""Appels au moteur de recherche : ce que chacun a rendu, et ce que ses pages sont devenues.

Une ligne par appel et par lancement, pour savoir quel poste recherché rapporte et lequel coûte pour rien.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engine_calls",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("search_run_id", sa.Integer, nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("search_text", sa.Text, nullable=False),
        sa.Column("international", sa.Integer, nullable=False),
        sa.Column("found_count", sa.Integer, nullable=False),
        sa.Column("unique_count", sa.Integer),
        sa.Column("new_count", sa.Integer),
        sa.Column("kept_count", sa.Integer),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_engine_calls_user", "engine_calls", ["user_id"])


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
