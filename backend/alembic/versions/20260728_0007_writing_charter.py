"""创作宪章表。

Revision ID: 0007
Revises: 20260728_0006_summary_chain
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "20260728_0006_summary_chain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "writing_charters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("narrative_focus", sa.Text(), nullable=False, server_default=""),
        sa.Column("red_lines", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("mandates", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("target_readers", sa.Text(), nullable=False, server_default=""),
        sa.Column("tone_reference", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint("uq_writing_charter_project", "writing_charters", ["project_id"])


def downgrade() -> None:
    op.drop_constraint("uq_writing_charter_project", "writing_charters")
    op.drop_table("writing_charters")
