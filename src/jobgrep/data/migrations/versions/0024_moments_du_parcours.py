"""Historique du parcours : chaque moment gardé sans son compte, pour survivre aux suppressions.

Rien n'est repris de ce qui est déjà en base : les comptes supprimés n'y sont plus, et un historique
reconstitué sans eux se lirait comme complet. Il commence donc à cette migration.

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("day", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("plan", sa.Text, nullable=False),
        sa.Column("detail", sa.Text),
    )
    op.create_index("ix_account_events_day", "account_events", ["day"])


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
