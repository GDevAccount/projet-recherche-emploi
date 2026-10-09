"""Ce qu'il faut pour suivre le parcours d'un invité : les jours où il vient, et les annonces qu'il ouvre.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_days",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("day", sa.Text, nullable=False),
        sa.UniqueConstraint("user_id", "day"),
    )
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("opened_at", sa.Text))


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
