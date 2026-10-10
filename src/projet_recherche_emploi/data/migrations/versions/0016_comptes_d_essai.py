"""Ce qu'il faut pour un essai sans connexion : la clé d'un compte d'essai, et le compte des essais ouverts.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("trial_key", sa.Text))
        batch.create_unique_constraint("uq_users_trial_key", ["trial_key"])
    op.create_table(
        "trial_starts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ip_hash", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("ix_trial_starts_created_at", "trial_starts", ["created_at"])


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
