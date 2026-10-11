"""Erreurs du navigateur : celles d'un visiteur sans session sont gardées aussi, sans compte.

Revision ID: 0025
Revises: 0024
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite ne sait pas rendre une colonne facultative en place : la table est recopiée
    with op.batch_alter_table("client_errors") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer, nullable=True)


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
