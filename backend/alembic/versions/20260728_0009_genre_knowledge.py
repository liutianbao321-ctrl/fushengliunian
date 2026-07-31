"""WritingMethodCard 加 genre 列 + SceneTemplate + PlotDevice 表。

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("writing_method_cards", sa.Column("genre", sa.String(50), nullable=True))
    op.create_index("ix_writing_method_card_genre", "writing_method_cards", ["genre"])

    op.create_table(
        "scene_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("scene_type", sa.String(50), nullable=False),
        sa.Column("genre", sa.String(50), nullable=True),
        sa.Column("tension_arc", sa.Text(), nullable=False),
        sa.Column("beats", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("pov_suggestion", sa.Text(), nullable=False, server_default=""),
        sa.Column("entry_condition", sa.Text(), nullable=False, server_default=""),
        sa.Column("exit_condition", sa.Text(), nullable=False, server_default=""),
        sa.Column("emotional_shift", sa.Text(), nullable=False, server_default=""),
        sa.Column("anti_patterns", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "plot_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("device_type", sa.String(50), nullable=False),
        sa.Column("genre", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("setup", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("escalation", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("payoff", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("common_mistakes", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("plot_devices")
    op.drop_table("scene_templates")
    op.drop_index("ix_writing_method_card_genre", table_name="writing_method_cards")
    op.drop_column("writing_method_cards", "genre")
