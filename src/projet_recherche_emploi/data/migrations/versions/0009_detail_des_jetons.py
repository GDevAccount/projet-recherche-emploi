"""Détail des jetons : ceux lus ou écrits en cache, facturés à un autre tarif, et ceux du raisonnement du modèle.

Vides pour les recherches d'avant cette migration, dont le coût est alors calculé au tarif plein.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TOKEN_COLUMNS = ("cache_read_tokens", "cache_write_tokens", "reasoning_tokens")


def upgrade() -> None:
    for table in ("search_runs", "page_evaluations"):
        for column in TOKEN_COLUMNS:
            op.add_column(table, sa.Column(column, sa.Integer))


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
