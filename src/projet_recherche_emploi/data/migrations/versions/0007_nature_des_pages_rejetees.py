"""Nature d'une page rejetée : liste d'offres, article, fiche métier, page d'accueil, offre expirée, formation.

Elle précise le motif « pas une offre valable ». Les pages déjà rejetées n'en ont pas : rien ne permet
de la retrouver sans les faire réévaluer.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rejected_jobs", sa.Column("page_kind", sa.Text))


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
