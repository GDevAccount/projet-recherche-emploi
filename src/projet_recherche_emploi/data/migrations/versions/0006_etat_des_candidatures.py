"""État d'une candidature : à traiter, postulée, entretien, refusée par l'employeur.

La colonne « status » remplace le booléen « applied », qui ne connaissait que les deux premiers.
Les offres déjà postulées gardent leur date de candidature.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("status", sa.Text, nullable=False, server_default="todo"))
    op.add_column("jobs", sa.Column("interview_at", sa.Text))
    op.add_column("jobs", sa.Column("rejected_at", sa.Text))
    op.execute("UPDATE jobs SET status = 'applied' WHERE applied = 1")
    # SQLite retire lui-même la colonne : pas besoin de recopier la table, donc ses contraintes ne bougent pas
    op.execute("ALTER TABLE jobs DROP COLUMN applied")


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
