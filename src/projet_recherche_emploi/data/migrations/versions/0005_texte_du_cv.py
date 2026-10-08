"""Texte du CV, coordonnées retirées : c'est lui que le filtre envoie au modèle, plus le PDF.

La table part vide. Le texte d'un CV déposé avant cette migration est écrit à sa première lecture
(CvService.read_text), à partir du PDF resté en place.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cv_texts",
        sa.Column("user_id", sa.Integer, primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
