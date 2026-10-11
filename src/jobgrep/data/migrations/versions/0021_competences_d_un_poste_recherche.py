"""Postes recherchés : les compétences, saisies à part du métier.

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("search_queries") as batch:
        batch.add_column(sa.Column("skills", sa.Text, nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
