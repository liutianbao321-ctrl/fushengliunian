"""Add persistent pre-project creation studio.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "creation_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("state", sa.String(40), server_default="RAW_IDEA", nullable=False),
        sa.Column("input_payload", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("selected_direction", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("foundation", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("foundation_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_creation_sessions_user_updated", "creation_sessions", ["user_id", "updated_at"])
    op.create_table(
        "creation_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("creation_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("parent_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("creation_artifacts.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "artifact_type", "version", name="uq_creation_artifact_version"),
    )
    op.create_index("ix_creation_artifacts_session_type", "creation_artifacts", ["session_id", "artifact_type"])
    op.create_table(
        "creation_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("creation_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_type", sa.String(50), nullable=False),
        sa.Column("options", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("chosen_index", sa.Integer()),
        sa.Column("chosen_payload", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("user_note", sa.Text()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "viability_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("creation_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("foundation_version", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(20), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("blocking_issues", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("warnings", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("author_confirmed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "foundation_version", name="uq_viability_review_foundation"),
    )


def downgrade() -> None:
    op.drop_table("viability_reviews")
    op.drop_table("creation_decisions")
    op.drop_index("ix_creation_artifacts_session_type", table_name="creation_artifacts")
    op.drop_table("creation_artifacts")
    op.drop_index("ix_creation_sessions_user_updated", table_name="creation_sessions")
    op.drop_table("creation_sessions")
