"""Évaluations de l'assistant : ce que chaque passage du banc de questions de référence a mesuré.

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

COUNTERS = (
    "cases",
    "passed",
    "outcome_hits",
    "retrieval_cases",
    "retrieval_hits",
    "cited_hits",
    "answer_cases",
    "correct",
    "judged",
    "faithful",
    "off_topic_cases",
    "off_topic_refused",
    "input_tokens",
    "output_tokens",
    "embedding_tokens",
    "judge_input_tokens",
    "judge_output_tokens",
    "duration_ms",
)


def upgrade() -> None:
    op.create_table(
        "assistant_evaluations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("embedding_model", sa.Text, nullable=False),
        sa.Column("judge_model", sa.Text, nullable=False),
        sa.Column("prompt_version", sa.Text, nullable=False),
        sa.Column("reciprocal_rank_sum", sa.REAL, nullable=False),
        *(sa.Column(counter, sa.Integer, nullable=False) for counter in COUNTERS),
        sa.Column("details", sa.Text, nullable=False),
    )


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
