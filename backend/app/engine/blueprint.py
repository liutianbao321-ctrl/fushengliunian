"""蓝图域生成引擎：六层大纲（L0-L4）与章内 Beat 卡（L6）生成。

- `run_blueprint_job(db, job)` 由 durable worker（app.services.blueprint_worker）调用，
  根据 job_type 分发到大纲生成或 Beat 卡生成。
- 不支持 LLM 时走 mock 确定性产出，保证契约稳定、可单测。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.engine.worldbuilder import get_genre_writing_contract
from app.models import (
    BeatCard,
    BlueprintJob,
    Chapter,
    CraftRule,
    OutlineNode,
    PacingConfig,
    PlotLedger,
    Project,
)
from app.services.llm_client import llm_client
from app.services.skill_loader import load_skill_prompt
from app.utils.canonical import parse_json_object


def utcnow() -> datetime:
    return datetime.now(UTC)


LAYER_ORDER = ["L0", "L1", "L2", "L3", "L4", "L5"]
# 各层默认生成的节点数；L2（设定）复用 worldbuilder，不在此生成
# 改为小批量：避免一锅烩过多节点导致质量下降和失败全丢
LAYER_NODE_COUNT = {"L1": 1, "L3": 5, "L4": 10}

BEAT_FIELDS = (
    "setup",
    "external_conflict",
    "internal_conflict",
    "protagonist_goal",
    "opponent_goal",
    "difficulty",
    "contrast",
    "suppression",
    "trump_card",
    "twist",
    "showoff",
    "gain",
    "expectation",
)


async def run_blueprint_job(db: AsyncSession, job: BlueprintJob) -> dict[str, Any]:
    job_type = job.job_type
    payload = job.payload or {}
    if job_type == "outline_generate":
        return await generate_outline(db, job.project_id, payload)
    if job_type == "beat_card_generate":
        return await generate_beat_card(db, payload)
    raise ValueError(f"未知的蓝图任务类型: {job_type}")


# --------------------------------------------------------------------------- #
# 大纲生成
# --------------------------------------------------------------------------- #
async def generate_outline(db: AsyncSession, project_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
    layer = str(payload.get("layer") or "L1")
    if layer not in LAYER_ORDER:
        raise ValueError(f"不支持的大纲层: {layer}（应为 L0-L5）")
    if layer not in LAYER_NODE_COUNT:
        raise ValueError(f"层 {layer} 不由蓝图生成引擎直接产出（L2 设定来自 worldbuilder，L0/L5 为用户输入/章纲）")

    parent_id = payload.get("parent_id") or payload.get("regenerate_node_id")
    project = await db.get(Project, project_id)
    if project is None:
        raise ValueError("项目不存在")

    # 重生成：清空该层下既有子节点，再产出全新一批
    await _clear_layer_children(db, project_id, layer, parent_id)

    count = LAYER_NODE_COUNT[layer]
    spec = await _build_outline_spec(db, project, layer, parent_id)
    nodes_data = await _call_blueprint_architect(layer, spec, count)

    created: list[OutlineNode] = []
    for idx, nd in enumerate(nodes_data[:count]):
        if not isinstance(nd, dict):
            continue
        node = OutlineNode(
            id=uuid.uuid4(),
            project_id=project_id,
            layer=layer,
            parent_id=parent_id,
            seq=idx,
            title=str(nd.get("title") or f"{layer} 节点 {idx + 1}"),
            body=str(nd.get("body") or ""),
            status="draft",
            meta=nd.get("meta") or {},
        )
        db.add(node)
        created.append(node)
    await db.commit()
    for node in created:
        await db.refresh(node)
    return {
        "layer": layer,
        "parent_id": str(parent_id) if parent_id else None,
        "created": len(created),
        "nodes": [
            {"id": str(n.id), "layer": n.layer, "title": n.title, "seq": n.seq, "status": n.status}
            for n in created
        ],
    }


async def _clear_layer_children(
    db: AsyncSession, project_id: uuid.UUID, layer: str, parent_id: uuid.UUID | None
) -> None:
    stmt = delete(OutlineNode).where(
        OutlineNode.project_id == project_id, OutlineNode.layer == layer
    )
    if parent_id is None:
        stmt = stmt.where(OutlineNode.parent_id.is_(None))
    else:
        stmt = stmt.where(OutlineNode.parent_id == parent_id)
    await db.execute(stmt)


async def _build_outline_spec(
    db: AsyncSession, project: Project, layer: str, parent_id: uuid.UUID | None
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "title": project.title,
        "genre": project.genre,
        "premise": project.one_sentence,
        "protagonist": project.protagonist_name,
        "protagonist_personality": project.protagonist_personality,
        "golden_finger": getattr(project, "golden_finger", "") or "",
        "intent_brief": getattr(project, "intent_brief", None) or {},
        "writing_contract": get_genre_writing_contract(project.genre),
        "layer": layer,
    }
    if layer in ("L3", "L4"):
        l1 = await db.scalar(
            select(OutlineNode)
            .where(OutlineNode.project_id == project.id, OutlineNode.layer == "L1")
            .order_by(OutlineNode.seq.asc())
            .limit(1)
        )
        if l1 is not None:
            spec["l1_concept"] = {"title": l1.title, "body": l1.body}
    if layer == "L4":
        if parent_id is not None:
            parent = await db.get(OutlineNode, parent_id)
            if parent is not None:
                spec["l3_segment"] = {
                    "title": parent.title,
                    "body": parent.body,
                    "meta": parent.meta,
                }
        existing = list(
            (
                await db.scalars(
                    select(OutlineNode)
                    .where(OutlineNode.project_id == project.id, OutlineNode.layer == "L3")
                    .order_by(OutlineNode.seq.asc())
                )
            ).all()
        )
        spec["l3_count"] = len(existing)
        spec["l3_titles"] = [n.title for n in existing]
    pacing = await db.get(PacingConfig, project.id)
    if pacing is not None:
        spec["pacing"] = {
            "minor_climax_cycle": pacing.minor_climax_cycle,
            "major_climax_cycle": pacing.major_climax_cycle,
            "mode": pacing.mode,
            "opening_mode": pacing.opening_mode,
        }
    a_rules = list(
        (
            await db.scalars(
                select(CraftRule).where(CraftRule.level == "A", CraftRule.enabled == True)  # noqa: E712
            )
        ).all()
    )
    spec["a_level_rules"] = [
        r.rule_text for r in a_rules
        if "涉政涉黄" not in r.rule_text and "色情内容" not in r.rule_text
    ]
    return spec


async def _call_blueprint_architect(layer: str, spec: dict[str, Any], count: int) -> list[dict[str, Any]]:
    settings = get_settings()
    skill = load_skill_prompt("blueprint-architect")
    system_prompt = (
        f"{skill}\n\n---\n你正在执行蓝图架构师节点 {layer}。只输出符合契约的 JSON 对象。"
        if skill
        else f"你正在执行蓝图架构师节点 {layer}。只输出符合契约的 JSON 对象。"
    )
    user_prompt = json.dumps({"layer": layer, "count": count, "spec": spec}, ensure_ascii=False)
    if settings.llm_backend == "mock":
        return _mock_outline_nodes(layer, count, spec)
    raw = await llm_client.complete(
        system_prompt,
        user_prompt,
        response_format="json",
        stream=True,
        max_tokens=settings.generation_max_tokens_structured,
        temperature=0.4,
    )
    data = parse_json_object(raw)
    nodes = data.get("nodes") if isinstance(data.get("nodes"), list) else []
    if not nodes and isinstance(data, dict) and data.get("title"):
        nodes = [data]
    return nodes or _mock_outline_nodes(layer, count, spec)


def _mock_outline_nodes(layer: str, count: int, spec: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = []
    for i in range(count):
        node: dict[str, Any] = {
            "title": f"{layer} 节点 {i + 1}",
            "body": f"（草稿）围绕《{spec.get('title', '作品')}》的设定，生成第 {i + 1} 个规划单元。",
            "meta": {},
        }
        if layer == "L4":
            node["keywords"] = ["关键词A", "关键词B"]
            # 前端契约：nine_lines 为 string[]（九线名称列表）
            node["nine_lines"] = ["主角性格", "配角", "技能", "伙伴", "感情"]
            # 前端契约：sweet_points 元素为 {type, position}
            node["sweet_points"] = [{"type": "优越感", "position": f"第{i + 1}段爽点"}]
            node["foreshadow_ids"] = []
            node["est_chapters"] = 5
        nodes.append(node)
    return nodes


# --------------------------------------------------------------------------- #
# Beat 卡（L6 章内构思卡）生成
# --------------------------------------------------------------------------- #
async def generate_beat_card(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    chapter_id = payload.get("chapter_id")
    if not chapter_id:
        raise ValueError("beat_card_generate 需要 chapter_id")
    if isinstance(chapter_id, str):
        try:
            chapter_id = uuid.UUID(chapter_id)
        except ValueError:
            raise ValueError("chapter_id 必须是章节 UUID")
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None:
        raise ValueError("章节不存在")

    project = await db.get(Project, chapter.project_id)
    open_foreshadows = list(
        (
            await db.scalars(
                select(PlotLedger).where(
                    PlotLedger.project_id == chapter.project_id, PlotLedger.status == "open"
                )
            )
        ).all()
    )
    spec: dict[str, Any] = {
        "book_title": project.title if project else "",
        "genre": project.genre if project else "",
        "chapter_sequence": chapter.chapter_sequence,
        "chapter_title": chapter.title,
        "chapter_summary": chapter.summary,
        "recent_ending": chapter.content[-1500:] if chapter.content else "",
        "open_foreshadows": [
            {
                "description": p.description,
                "type": p.type,
                "planted_chapter": p.planted_chapter,
                "due_chapter": p.due_chapter,
                "is_yy": p.is_yy,
            }
            for p in open_foreshadows
        ],
    }
    pacing = await db.get(PacingConfig, chapter.project_id) if project else None
    if pacing is not None:
        spec["pacing"] = {
            "minor_climax_cycle": pacing.minor_climax_cycle,
            "major_climax_cycle": pacing.major_climax_cycle,
            "mode": pacing.mode,
            "opening_mode": pacing.opening_mode,
        }

    fields = await _call_beat_designer(spec)

    existing = await db.scalar(select(BeatCard).where(BeatCard.chapter_id == chapter_id))
    if existing is not None:
        existing.fields = fields
        existing.status = "draft"
        existing.updated_at = utcnow()
        card = existing
    else:
        card = BeatCard(id=uuid.uuid4(), chapter_id=chapter_id, fields=fields, status="draft")
        db.add(card)
    await db.commit()
    await db.refresh(card)
    return {"chapter_id": str(chapter_id), "beat_card_id": str(card.id), "status": card.status}


async def _call_beat_designer(spec: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    skill = load_skill_prompt("beat-designer")
    system_prompt = (
        f"{skill}\n\n---\n你正在执行 Beat 卡设计师节点。只输出包含 13 个字段的 JSON 对象。"
        if skill
        else "你正在执行 Beat 卡设计师节点。只输出包含 13 个字段的 JSON 对象。"
    )
    user_prompt = json.dumps(spec, ensure_ascii=False)
    if settings.llm_backend == "mock":
        return _mock_beat_fields()
    raw = await llm_client.complete(
        system_prompt,
        user_prompt,
        response_format="json",
        stream=True,
        max_tokens=settings.generation_max_tokens_structured,
        temperature=0.5,
    )
    data = parse_json_object(raw)
    return _normalize_beat_fields(data)


def _normalize_beat_fields(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in BEAT_FIELDS:
        value = data.get(key)
        result[key] = value if isinstance(value, str) and value.strip() else _mock_beat_fields().get(key, "")
    return result


def _mock_beat_fields() -> dict[str, str]:
    return {
        "setup": "前置铺垫已充足，主角处于明确的处境与欲望中。",
        "external_conflict": "外部对手施压，迫使主角必须行动。",
        "internal_conflict": "主角内心有未决的取舍与恐惧。",
        "protagonist_goal": "本章主角想要达成的目标。",
        "opponent_goal": "对手想要阻止或夺取的东西。",
        "difficulty": "主角面临的真实困难与必须付出的代价。",
        "contrast": "以反差衬托主角处境（先抬高对手、贬低主角）。",
        "suppression": "先压抑蓄力，把压力推到临界再释放。",
        "trump_card": "底牌/金手指在此刻出现，改变局势。",
        "twist": "神转折：读者以为走 A，实际走 C。",
        "showoff": "主角出风头，完成地位互换。",
        "gain": "主角得到的实质性好处。",
        "expectation": "留给读者的期待感落点。",
    }
