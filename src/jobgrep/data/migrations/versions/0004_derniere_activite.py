"""Dernière activité d'un compte, pour supprimer ceux qui ne servent plus.

Les comptes existants sont datés du jour de la migration : faute de savoir quand ils ont servi
pour la dernière fois, leur délai repart de zéro.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_seen_at", sa.Text))
    op.execute("UPDATE users SET last_seen_at = CURRENT_TIMESTAMP")


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
