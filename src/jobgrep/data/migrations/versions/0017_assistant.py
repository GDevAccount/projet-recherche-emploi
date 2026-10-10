"""Ce qu'il faut à l'assistant : les passages des textes du site, et les questions qui lui sont posées.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_passages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("page_title", sa.Text, nullable=False),
        sa.Column("section", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.Column("embedding_model", sa.Text, nullable=False),
        sa.Column("embedding", sa.Text, nullable=False),
    )
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("question", sa.Text),
        sa.Column("answer", sa.Text),
        sa.Column("sources", sa.Text),
        sa.Column("retrieved", sa.Text),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("model", sa.Text),
        sa.Column("prompt_version", sa.Text),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cache_read_tokens", sa.Integer),
        sa.Column("cache_write_tokens", sa.Integer),
        sa.Column("embedding_model", sa.Text),
        sa.Column("embedding_tokens", sa.Integer),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("created_at", sa.Text, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_assistant_messages_user", "assistant_messages", ["user_id"])


def downgrade() -> None:
    raise NotImplementedError("Cette migration ne se défait pas : restaurer la sauvegarde faite avant migration.")
