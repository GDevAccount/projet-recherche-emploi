"""Dépôt d'un CV : chaque lecture du CV par le modèle, qui en tire les postes à rechercher.

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cv_extractions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("queries_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("model", sa.Text),
        sa.Column("prompt_version", sa.Text),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cache_read_tokens", sa.Integer),
        sa.Column("cache_write_tokens", sa.Integer),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_cv_extractions_user", "cv_extractions", ["user_id"])


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
