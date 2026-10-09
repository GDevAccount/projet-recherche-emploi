"""Erreurs rendues par l'API hors d'une recherche : route, type de l'erreur, compte et date.

Les logs de l'hébergeur ne sont pas conservés : c'est ce qui permet de voir une panne après coup.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "server_errors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("route", sa.Text),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("error_type", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_server_errors_user", "server_errors", ["user_id"])


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
