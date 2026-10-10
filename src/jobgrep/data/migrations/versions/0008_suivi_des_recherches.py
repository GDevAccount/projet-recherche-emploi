"""Suivi des recherches : bilan, durées et jetons de chaque lancement, et journal de chaque page évaluée.

Les lancements d'avant cette migration n'ont que leur date : leurs nouvelles colonnes restent vides.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

RUN_TEXT_COLUMNS = ("status", "error", "finished_at", "model", "prompt_version")
RUN_INTEGER_COLUMNS = (
    "found_count",
    "new_count",
    "kept_count",
    "rejected_count",
    "inserted_count",
    "search_ms",
    "dedupe_ms",
    "evaluate_ms",
    "save_ms",
    "search_calls",
    "input_tokens",
    "output_tokens",
)


def upgrade() -> None:
    for column in RUN_TEXT_COLUMNS:
        op.add_column("search_runs", sa.Column(column, sa.Text))
    for column in RUN_INTEGER_COLUMNS:
        op.add_column("search_runs", sa.Column(column, sa.Integer))

    op.create_table(
        "page_evaluations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("search_run_id", sa.Integer),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("query", sa.Text),
        sa.Column("score", sa.REAL),
        sa.Column("kept", sa.Integer, nullable=False),
        sa.Column("page_kind", sa.Text),
        sa.Column("contract_type", sa.Text),
        sa.Column("work_city", sa.Text),
        sa.Column("work_country", sa.Text),
        sa.Column("work_mode", sa.Text),
        sa.Column("in_accepted_area", sa.Integer),
        sa.Column("open_to_candidates_in_france", sa.Integer),
        sa.Column("matches_search", sa.Integer),
        sa.Column("matches_skills", sa.Integer),
        sa.Column("matches_level", sa.Integer),
        sa.Column("matches_contract", sa.Integer),
        sa.Column("matches_location", sa.Integer),
        sa.Column("reason", sa.Text),
        sa.Column("page_chars", sa.Integer),
        sa.Column("truncated", sa.Integer),
        sa.Column("full_page", sa.Integer),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_page_evaluations_run", "page_evaluations", ["user_id", "search_run_id"])


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
