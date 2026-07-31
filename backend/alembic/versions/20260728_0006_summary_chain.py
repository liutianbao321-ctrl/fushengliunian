"""滚动摘要链表。

Revision ID: 20260728_0006_summary_chain
Revises: 20260728_0005_blueprint_domain
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260728_0006_summary_chain"
down_revision: str | None = "20260728_0005_blueprint_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "summary_chains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chapter_sequence", sa.Integer(), nullable=False),
        sa.Column("chapter_summary", sa.Text(), nullable=False),
        sa.Column("rolling_summary", sa.Text(), nullable=False),
        sa.Column("volume_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint(
        "uq_summary_chain_chapter", "summary_chains", ["project_id", "chapter_sequence"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_summary_chain_chapter", "summary_chains")
    op.drop_table("summary_chains")
