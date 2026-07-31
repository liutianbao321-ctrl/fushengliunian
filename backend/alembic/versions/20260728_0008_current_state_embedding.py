"""CurrentState 加 embedding 向量列。

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("current_states", sa.Column("embedding", Vector(1024), nullable=True))
    op.add_column("current_states", sa.Column("embedding_model", sa.String(100), nullable=True))
    op.add_column("current_states", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))
    op.create_index("ix_current_state_embedding", "current_states", ["embedding"], postgresql_using="ivfflat")


def downgrade() -> None:
    op.drop_index("ix_current_state_embedding", table_name="current_states")
    op.drop_column("current_states", "embedding_dimensions")
    op.drop_column("current_states", "embedding_model")
    op.drop_column("current_states", "embedding")
