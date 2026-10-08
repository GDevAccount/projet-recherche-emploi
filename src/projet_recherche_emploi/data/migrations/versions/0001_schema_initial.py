"""Schéma initial : les cinq tables telles qu'elles existaient avant Alembic.

Les bases créées avant Alembic ont déjà tout ou partie de ces tables, chaque dépôt créant alors la sienne
à son premier usage. Cette migration ne crée donc que les tables manquantes, sans toucher aux autres.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

from projet_recherche_emploi.config import DEFAULT_QUERIES, DEFAULT_USER_ID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))


def _user_id() -> sa.Column:
    return sa.Column("user_id", sa.Integer, nullable=False, server_default=sa.text(str(DEFAULT_USER_ID)))


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "jobs" not in existing_tables:
        op.create_table(
            "jobs",
            _user_id(),
            sa.Column("url", sa.Text, nullable=False),
            sa.Column("title", sa.Text, nullable=False),
            sa.Column("content", sa.Text),
            sa.Column("score", sa.REAL),
            sa.Column("contract_type", sa.Text),
            sa.Column("query", sa.Text),
            sa.Column("match_reason", sa.Text),
            sa.Column("applied", sa.Integer, nullable=False, server_default=sa.text("0")),
            sa.Column("applied_at", sa.Text),
            _created_at(),
            sa.Column("deleted", sa.Integer, nullable=False, server_default=sa.text("0")),
            sa.PrimaryKeyConstraint("user_id", "url"),
        )

    if "rejected_jobs" not in existing_tables:
        op.create_table(
            "rejected_jobs",
            _user_id(),
            sa.Column("url", sa.Text, nullable=False),
            sa.Column("title", sa.Text, nullable=False),
            sa.Column("contract_type", sa.Text),
            sa.Column("query", sa.Text),
            sa.Column("is_real_offer", sa.Integer, nullable=False),
            sa.Column("matches_cv", sa.Integer, nullable=False),
            sa.Column("reject_reason", sa.Text),
            _created_at(),
            sa.PrimaryKeyConstraint("user_id", "url"),
        )

    if "search_queries" not in existing_tables:
        search_queries = op.create_table(
            "search_queries",
            sa.Column("id", sa.Integer, primary_key=True),
            _user_id(),
            sa.Column("contract_type", sa.Text, nullable=False),
            sa.Column("query", sa.Text, nullable=False),
            _created_at(),
            sa.UniqueConstraint("user_id", "query"),
        )
        # Ajoutées à la création de la table seulement : une recherche supprimée ne doit pas revenir.
        # Elles sont calées sur le profil du propriétaire : les autres utilisateurs partent d'une liste vide.
        op.bulk_insert(
            search_queries,
            [
                {"user_id": DEFAULT_USER_ID, "contract_type": contract_type, "query": query}
                for contract_type, query in DEFAULT_QUERIES
            ],
        )

    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("email", sa.Text, unique=True),
            _created_at(),
        )
    # L'identifiant du propriétaire est réservé : sans cette ligne, le premier invité le recevrait,
    # et avec lui les données d'avant les comptes
    op.execute(sa.text("INSERT OR IGNORE INTO users (id) VALUES (:id)").bindparams(id=DEFAULT_USER_ID))

    if "search_runs" not in existing_tables:
        op.create_table(
            "search_runs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, nullable=False),
            _created_at(),
        )


def downgrade() -> None:
    raise NotImplementedError("Le schéma initial ne se défait pas : restaurer la sauvegarde faite avant migration.")
