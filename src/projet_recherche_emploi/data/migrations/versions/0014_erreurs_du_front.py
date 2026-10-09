"""Erreurs survenues dans le navigateur, signalées par le front : écran, type de l'erreur, emplacement dans le code.

Le serveur ne les voit pas : sans cette table, un écran blanc chez un invité ne laisserait aucune trace.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_errors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("route", sa.Text),
        sa.Column("error_type", sa.Text, nullable=False),
        sa.Column("source", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_client_errors_user", "client_errors", ["user_id"])


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
