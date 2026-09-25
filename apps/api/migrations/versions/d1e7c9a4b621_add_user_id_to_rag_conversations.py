"""add user_id to rag conversations

Revision ID: d1e7c9a4b621
Revises: 843141d56b2e
Create Date: 2026-09-25 15:35:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e7c9a4b621"
down_revision: Union[str, Sequence[str], None] = "843141d56b2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rag_conversations",
        sa.Column("user_id", sa.Text(), nullable=True),
    )

    op.create_index(
        "idx_rag_conversations_user_id",
        "rag_conversations",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "idx_rag_conversations_scope",
        "rag_conversations",
        ["client_id", "corpus_id", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_rag_conversations_scope",
        table_name="rag_conversations",
    )
    op.drop_index(
        "idx_rag_conversations_user_id",
        table_name="rag_conversations",
    )
    op.drop_column("rag_conversations", "user_id")