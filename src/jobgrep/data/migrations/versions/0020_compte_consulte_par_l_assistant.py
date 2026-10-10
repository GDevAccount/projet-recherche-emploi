"""Assistant : les outils qu'il a appelés pour une question, et ce que l'évaluation en mesure.

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assistant_messages") as batch:
        batch.add_column(sa.Column("consulted", sa.Text))
    with op.batch_alter_table("assistant_evaluations") as batch:
        batch.add_column(sa.Column("consult_cases", sa.Integer, nullable=False, server_default=sa.text("0")))
        batch.add_column(sa.Column("consult_hits", sa.Integer, nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
