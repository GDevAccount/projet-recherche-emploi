"""Corrections du tri : pages écartées remises dans les offres, et offres supprimées avec leur motif.

Chaque ligne garde le verdict contredit et la version du prompt qui l'avait rendu.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

CRITERIA = ("matches_search", "matches_contract", "matches_skills", "matches_level", "matches_location")


def upgrade() -> None:
    op.create_table(
        "corrections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("query", sa.Text),
        sa.Column("reason", sa.Text),
        sa.Column("page_kind", sa.Text),
        *(sa.Column(criterion, sa.Integer) for criterion in CRITERIA),
        sa.Column("model_reason", sa.Text),
        sa.Column("search_run_id", sa.Integer),
        sa.Column("model", sa.Text),
        sa.Column("prompt_version", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_corrections_user", "corrections", ["user_id"])


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
