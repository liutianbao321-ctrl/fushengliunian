"""统一项目种子、作品知识库与耐久导入任务。

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("imported_works", sa.Column("analysis_attempt", sa.Integer(), server_default="0", nullable=False))
    op.add_column("imported_works", sa.Column("analysis_claim_token", sa.String(64), nullable=True))
    op.add_column("imported_works", sa.Column("analysis_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("imported_works", sa.Column("analysis_error", sa.Text(), nullable=True))
    op.create_index("ix_imported_work_analysis_queue", "imported_works", ["analysis_status", "created_at"])
    op.add_column("imported_chapters", sa.Column("summary", sa.Text(), server_default="", nullable=False))

    op.add_column("chapter_chunks", sa.Column("source", sa.String(20), server_default="native", nullable=False))
    op.add_column(
        "chapter_chunks",
        sa.Column(
            "imported_chapter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("imported_chapters.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_chapter_chunk_source", "chapter_chunks", ["project_id", "source", "chapter_sequence"])

    op.create_table(
        "intent_anchors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(30), server_default="interview", nullable=False),
        sa.Column("confirmed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("locked", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_intent_anchor_project_kind", "intent_anchors", ["project_id", "kind"])

    op.create_table(
        "project_seeds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("source_work_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("imported_works.id", ondelete="SET NULL")),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(20), server_default="confirmed", nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_project_seed_version"),
    )

    op.create_table(
        "work_codex_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("imported_work_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("imported_works.id", ondelete="CASCADE"), nullable=False),
        sa.Column("layer", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("title", sa.String(300), server_default="", nullable=False),
        sa.Column("content", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.8", nullable=False),
        sa.Column("user_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("source_chapter_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_work_codex_layer_kind", "work_codex_entries", ["imported_work_id", "layer", "kind"])

    op.create_table(
        "narrative_dna",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("imported_work_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("imported_works.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hook_patterns", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("pacing_stats", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("pov_habits", sa.Text(), server_default="", nullable=False),
        sa.Column("escalation_curve", sa.Text(), server_default="", nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("imported_work_id", name="uq_narrative_dna_work"),
    )


def downgrade() -> None:
    op.drop_table("narrative_dna")
    op.drop_index("ix_work_codex_layer_kind", table_name="work_codex_entries")
    op.drop_table("work_codex_entries")
    op.drop_table("project_seeds")
    op.drop_index("ix_intent_anchor_project_kind", table_name="intent_anchors")
    op.drop_table("intent_anchors")
    op.drop_index("ix_chapter_chunk_source", table_name="chapter_chunks")
    op.drop_column("chapter_chunks", "imported_chapter_id")
    op.drop_column("chapter_chunks", "source")
    op.drop_column("imported_chapters", "summary")
    op.drop_index("ix_imported_work_analysis_queue", table_name="imported_works")
    op.drop_column("imported_works", "analysis_error")
    op.drop_column("imported_works", "analysis_heartbeat_at")
    op.drop_column("imported_works", "analysis_claim_token")
    op.drop_column("imported_works", "analysis_attempt")
