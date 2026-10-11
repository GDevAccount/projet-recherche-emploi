"""Référentiel des compétences proposées à la saisie d'un poste recherché, rempli depuis skills_catalog.txt.

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa
from alembic import op

from jobgrep.data.skills_catalog import fold_skill, read_catalog

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    skills = op.create_table(
        "skills",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("search_name", sa.Text, nullable=False),
        sa.UniqueConstraint("search_name"),
    )
    op.bulk_insert(skills, [{"name": name, "search_name": fold_skill(name)} for name in read_catalog()])


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
