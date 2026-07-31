"""补齐用户控制、反馈与章节意图领域表。

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("taste_profiles"):
        op.create_table(
            "taste_profiles",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("preferred_genres", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
            sa.Column("preferred_pacing", sa.String(20), server_default="mixed", nullable=False),
            sa.Column("preferred_tension", sa.String(20), server_default="medium", nullable=False),
            sa.Column("dialogue_preference", sa.String(20), server_default="natural", nullable=False),
            sa.Column("description_density", sa.String(20), server_default="moderate", nullable=False),
            sa.Column("avoid_patterns", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
            sa.Column("favorite_patterns", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
            sa.Column("distilled_from", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", name="uq_taste_profile_user"),
        )

    if not _table_exists("style_exemplars"):
        op.create_table(
            "style_exemplars",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("chapter_sequence", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(50), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source", sa.String(20), server_default="user_selection", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists("feedback_events"):
        op.create_table(
            "feedback_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("chapter_sequence", sa.Integer(), nullable=True),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("payload", postgresql.JSONB(), server_default="{}", nullable=False),
            sa.Column("distilled", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_feedback_events_pending", "feedback_events", ["project_id", "distilled"])

    if not _table_exists("decision_points"):
        op.create_table(
            "decision_points",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("chapter_sequence", sa.Integer(), nullable=True),
            sa.Column("decision_type", sa.String(50), nullable=False),
            sa.Column("options", postgresql.JSONB(), server_default="[]", nullable=False),
            sa.Column("chosen_index", sa.Integer(), nullable=True),
            sa.Column("user_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists("character_voice_cards"):
        op.create_table(
            "character_voice_cards",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("character_name", sa.String(200), nullable=False),
            sa.Column("catch_phrases", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
            sa.Column("sentence_patterns", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
            sa.Column("avoid_topics", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
            sa.Column("subtext_patterns", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
            sa.Column("emotional_range", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
            sa.Column("last_updated_chapter", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("project_id", "character_name", name="uq_voice_card_character"),
        )

    if not _table_exists("control_settings"):
        op.create_table(
            "control_settings",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("mode", sa.String(20), server_default="copilot", nullable=False),
            sa.Column("gate_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("brief_duration_seconds", sa.Integer(), server_default="30", nullable=False),
            sa.Column("auto_publish", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("chapter_overrides", postgresql.JSONB(), server_default="{}", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("project_id", name="uq_control_setting_project"),
        )

    if not _table_exists("intent_briefs"):
        op.create_table(
            "intent_briefs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("chapter_sequence", sa.Integer(), nullable=False),
            sa.Column("why_this_chapter", sa.Text(), nullable=False),
            sa.Column("position", postgresql.JSONB(), server_default="{}", nullable=False),
            sa.Column("scene_entities", postgresql.JSONB(), server_default="[]", nullable=False),
            sa.Column("character_states", postgresql.JSONB(), server_default="{}", nullable=False),
            sa.Column("due_foreshadowing", postgresql.JSONB(), server_default="[]", nullable=False),
            sa.Column("writing_contract", postgresql.JSONB(), server_default="{}", nullable=False),
            sa.Column("status", sa.String(20), server_default="pending", nullable=False),
            sa.Column("user_verdict", sa.String(20), nullable=True),
            sa.Column("user_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("project_id", "chapter_sequence", name="uq_intent_brief_chapter"),
        )


def downgrade() -> None:
    for table_name in (
        "intent_briefs",
        "control_settings",
        "character_voice_cards",
        "decision_points",
        "feedback_events",
        "style_exemplars",
        "taste_profiles",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
