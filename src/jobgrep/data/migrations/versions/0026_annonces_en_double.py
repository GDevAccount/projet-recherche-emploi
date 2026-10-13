"""Annonces en double : l'empreinte du texte d'une offre, et la marque d'une page écartée pour cela.

Revision ID: 0026
Revises: 0025
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("text_fingerprint", sa.Text, nullable=True))
    op.add_column("rejected_jobs", sa.Column("duplicate", sa.Integer, nullable=True))


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
