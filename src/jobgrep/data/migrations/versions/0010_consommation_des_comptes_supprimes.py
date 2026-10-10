"""Consommation des comptes supprimés : des totaux par mois, sans adresse ni contenu.

À la suppression d'un compte, ses lancements sont effacés ; ce qu'ils ont consommé est d'abord additionné ici,
pour que le coût de l'instance reste connu dans la durée.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

COUNT_COLUMNS = (
    "runs",
    "found_count",
    "kept_count",
    "search_calls",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
)


def upgrade() -> None:
    op.create_table(
        "archived_usage",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, nullable=False),
        sa.Column("plan", sa.Text, nullable=False),
        sa.Column("month", sa.Text, nullable=False),
        sa.Column("model", sa.Text),
        *(sa.Column(column, sa.Integer) for column in COUNT_COLUMNS),
        sa.Column("deleted_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
