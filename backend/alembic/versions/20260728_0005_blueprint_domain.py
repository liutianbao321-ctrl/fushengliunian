"""蓝图域：六层大纲树 / Beat 卡 / 伏笔登记表 / 节奏参数 / 负面清单 / 蓝图任务。

Revision ID: 20260728_0005_blueprint_domain
Revises: 20260724_0004
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260728_0005_blueprint_domain"
down_revision: str | None = "20260724_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    cols = [c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)]
    return column in cols


def _create_outline_nodes() -> None:
    if _table_exists("outline_nodes"):
        return
    op.create_table(
        "outline_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("layer", sa.String(length=10), nullable=False),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outline_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=400), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outline_node_project_layer_seq", "outline_nodes", ["project_id", "layer", "seq"])


def _create_beat_cards() -> None:
    if _table_exists("beat_cards"):
        return
    op.create_table(
        "beat_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "chapter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chapters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fields", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint("uq_beat_card_chapter", "beat_cards", ["chapter_id"])


def _create_plot_ledger() -> None:
    if _table_exists("plot_ledger"):
        return
    op.create_table(
        "plot_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("planted_chapter", sa.Integer(), nullable=False),
        sa.Column(
            "mentioned_chapters",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("due_chapter", sa.Integer(), nullable=True),
        sa.Column("resolved_chapter", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("is_yy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "origin_foreshadowing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("foreshadowing.id", ondelete="SET NULL", use_alter=True, name="fk_plot_ledger_origin_fs"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _create_pacing_configs() -> None:
    if _table_exists("pacing_configs"):
        return
    op.create_table(
        "pacing_configs",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("minor_climax_cycle", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("major_climax_cycle", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("sweet_density", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="ladder"),
        sa.Column("opening_mode", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _create_craft_rules() -> None:
    if _table_exists("craft_rules"):
        return
    op.create_table(
        "craft_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("detect_method", sa.String(length=20), nullable=False, server_default="llm_judge"),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="global"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _create_blueprint_jobs() -> None:
    if _table_exists("blueprint_jobs"):
        return
    op.create_table(
        "blueprint_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _add_project_columns() -> None:
    # 蓝图域衔接：金手指与意图书，供大纲生成 prompt 注入
    # Guard: baseline create_all may already include these columns on a fresh DB.
    if not _column_exists("projects", "golden_finger"):
        op.add_column("projects", sa.Column("golden_finger", sa.Text(), nullable=False, server_default=""))
    if not _column_exists("projects", "intent_brief"):
        op.add_column(
            "projects",
            sa.Column("intent_brief", postgresql.JSONB(), nullable=False, server_default="{}"),
        )


def _drop_project_columns() -> None:
    op.drop_column("projects", "intent_brief")
    op.drop_column("projects", "golden_finger")


# v5 §1.8 负面清单三级规则：A 级 6 条 / B 级 8 条 / C 级 3 条
_CRAFT_RULES = [
    # A 级（阻塞，生成后必须修复）
    ("A", "绿帽/虐主超一章不翻盘（如写必须同章翻盘且主角得好处）", "llm_judge", "global"),
    ("A", "主线消失：连续章节无主线推进或主角目标被架空", "llm_judge", "global"),
    ("A", "万能主角：所有困境都被轻松化解、无真实代价", "llm_judge", "global"),
    ("A", "剧情涉政涉黄：出现违反主编红线的政治/色情内容", "llm_judge", "global"),
    ("A", "逻辑硬伤：因果断裂、设定自相矛盾、时间线错乱", "llm_judge", "global"),
    ("A", "人物身份混乱：三人以上对话无说话人指示", "llm_judge", "global"),
    # B 级（警告，建议修复）
    ("B", "主角幼稚：行为明显违背其泛性格设定与既有处境", "llm_judge", "global"),
    ("B", "擂台连篇：机械比武段落无差别堆叠", "llm_judge", "global"),
    ("B", "睡醒变身：突兀获得能力或身份而无因果铺垫", "llm_judge", "global"),
    ("B", "史官评价：作者跳出来做历史/设定总结打断叙事", "llm_judge", "global"),
    ("B", "书中书堆背景：用大段说明性文字倾倒设定", "llm_judge", "global"),
    ("B", "感叹号流升级：每次升级都写成高潮式感叹", "llm_judge", "global"),
    ("B", "类型混杂：都市+修真+西幻等体系乱炖失去类型边界", "llm_judge", "global"),
    ("B", "升级体系过度复杂：自创复杂体系却不复用成熟框架", "llm_judge", "global"),
    # C 级（风格提示）
    ("C", "形容词堆砌：用大量形容词替代具体动作与感官", "llm_judge", "global"),
    ("C", "外貌描写超长：开篇或出场用过长静态外貌描写", "llm_judge", "opening"),
    ("C", "水文注水：无关场景/重复叙述拉长篇幅", "llm_judge", "global"),
]


def _seed_craft_rules() -> None:
    from datetime import UTC, datetime

    # Idempotent: skip if rows already present (e.g. baseline create_all + re-run).
    existing = op.get_bind().execute(sa.text("SELECT count(*) FROM craft_rules")).scalar()
    if existing:
        return
    now = datetime.now(UTC)
    table = sa.table(
        "craft_rules",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("level", sa.String),
        sa.column("rule_text", sa.Text),
        sa.column("detect_method", sa.String),
        sa.column("scope", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    rows = [
        {
            "id": uuid.uuid4(),
            "level": level,
            "rule_text": text,
            "detect_method": method,
            "scope": scope,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
        }
        for (level, text, method, scope) in _CRAFT_RULES
    ]
    op.bulk_insert(table, rows)


def upgrade() -> None:
    _create_outline_nodes()
    _create_beat_cards()
    _create_plot_ledger()
    _create_pacing_configs()
    _create_craft_rules()
    _create_blueprint_jobs()
    _add_project_columns()
    _seed_craft_rules()


def downgrade() -> None:
    _drop_project_columns()
    op.drop_table("blueprint_jobs")
    op.drop_table("craft_rules")
    op.drop_table("pacing_configs")
    op.drop_table("plot_ledger")
    op.drop_table("beat_cards")
    op.drop_index("ix_outline_node_project_layer_seq", table_name="outline_nodes")
    op.drop_table("outline_nodes")
