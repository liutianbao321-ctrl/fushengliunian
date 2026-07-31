"""Add imported works, market data, reader feedback, and immersive sessions.

Revision ID: 20260721_0002
Revises: 20260719_0001
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260721_0002"
down_revision = "20260719_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The original baseline imports current ORM metadata. On a brand-new database it
    # therefore already contains this revision; older deployed databases do not.
    if "imported_works" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "imported_works",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("source_platform", sa.String(length=100), nullable=True),
        sa.Column("total_chapters", sa.Integer(), nullable=False),
        sa.Column("total_words", sa.Integer(), nullable=False),
        sa.Column("genre", sa.String(length=50), nullable=True),
        sa.Column("sub_genre", sa.String(length=100), nullable=True),
        sa.Column("analysis_status", sa.String(length=20), nullable=False),
        sa.Column("analysis_progress", sa.Float(), nullable=False),
        sa.Column("breakpoint_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("style_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extracted_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rights_status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "market_tracks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("track_name", sa.String(length=200), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("genre", sa.String(length=50), nullable=False),
        sa.Column("sub_genre", sa.String(length=100), nullable=True),
        sa.Column("heat", sa.Integer(), nullable=False),
        sa.Column("heat_trend", sa.String(length=20), nullable=False),
        sa.Column("competition", sa.String(length=20), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("monetization", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("benchmark_works", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("taste_tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("golden_formula", sa.Text(), nullable=True),
        sa.Column("platform_tips", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trope_library",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trope_name", sa.String(length=200), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("hook_template", sa.Text(), nullable=True),
        sa.Column("pacing_formula", sa.Text(), nullable=True),
        sa.Column("source_works", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=True),
        sa.Column("genre", sa.String(length=50), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "hot_novels",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("platform", sa.String(length=100), nullable=True),
        sa.Column("genre", sa.String(length=50), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("synopsis", sa.Text(), nullable=True),
        sa.Column("rank_position", sa.Integer(), nullable=True),
        sa.Column("public_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reviews_summary", sa.Text(), nullable=True),
        sa.Column("sample_hook", sa.Text(), nullable=True),
        sa.Column("track_id", sa.UUID(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["track_id"], ["market_tracks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "imported_chapters",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("work_id", sa.UUID(), nullable=False),
        sa.Column("chapter_sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("analysis_status", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["work_id"], ["imported_works.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_id", "chapter_sequence", name="uq_imported_chapter_seq"),
    )
    op.create_table(
        "reader_feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("chapter_sequence", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("chase_score", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("readers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("thrill_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk_points", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "immersive_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("work_id", sa.UUID(), nullable=False),
        sa.Column("character_name", sa.String(length=200), nullable=False),
        sa.Column("experience_style", sa.String(length=20), nullable=True),
        sa.Column("segments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("character_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_id"], ["imported_works.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "projects",
        sa.Column("creation_mode", sa.String(length=20), server_default="inspired", nullable=False),
    )
    op.add_column("projects", sa.Column("channel", sa.String(length=20), nullable=True))
    op.add_column("projects", sa.Column("track", sa.String(length=200), nullable=True))
    op.add_column("projects", sa.Column("source_work_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_project_source_work",
        "projects",
        "imported_works",
        ["source_work_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("projects", "creation_mode", server_default=None)
    op.add_column(
        "story_wiki",
        sa.Column("source", sa.String(length=20), server_default="generated", nullable=False),
    )
    op.alter_column("story_wiki", "source", server_default=None)


def downgrade() -> None:
    op.drop_column("story_wiki", "source")
    op.drop_constraint("fk_project_source_work", "projects", type_="foreignkey")
    op.drop_column("projects", "source_work_id")
    op.drop_column("projects", "track")
    op.drop_column("projects", "channel")
    op.drop_column("projects", "creation_mode")
    op.drop_table("immersive_sessions")
    op.drop_table("reader_feedback")
    op.drop_table("imported_chapters")
    op.drop_table("hot_novels")
    op.drop_table("trope_library")
    op.drop_table("market_tracks")
    op.drop_table("imported_works")
