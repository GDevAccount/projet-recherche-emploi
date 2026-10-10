"""Assistant : la note donnée à une réponse, et la question qui ouvre une conversation.

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assistant_messages") as batch:
        batch.add_column(sa.Column("feedback", sa.Text))
        batch.add_column(sa.Column("starts_conversation", sa.Integer, nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
