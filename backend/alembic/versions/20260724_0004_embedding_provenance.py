"""Record vector model provenance.

Revision ID: 20260724_0004
Revises: 20260723_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260724_0004"
down_revision: str | None = "20260723_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("chapter_chunks", "writing_knowledge_chunks", "writing_method_cards")


def _column_exists(table: str, column: str) -> bool:
    cols = [c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)]
    return column in cols


def upgrade() -> None:
    # The baseline imports current ORM metadata, so on a brand-new database these
    # columns already exist. Guard to stay idempotent (matches 0002/0003 pattern).
    if _column_exists("chapter_chunks", "embedding_model"):
        return
    for table in TABLES:
        op.add_column(table, sa.Column("embedding_model", sa.String(length=100), nullable=True))
        op.add_column(table, sa.Column("embedding_dimensions", sa.Integer(), nullable=True))


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_column(table, "embedding_dimensions")
        op.drop_column(table, "embedding_model")
