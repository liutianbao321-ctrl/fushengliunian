from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from typing import Any

import httpx
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.engine.charter import get_charter, render_charter_prompt
from app.engine.genre_knowledge import load_genre_pack, render_genre_prompt
from app.engine.memory_search import search_entity_memory
from app.engine.retrieval import hybrid_search, pageindex_navigate, writing_guide_search, writing_method_card_search
from app.engine.summary import get_latest_summary
from app.engine.worldbuilder import get_genre_writing_contract
from app.models import (
    Chapter,
    ChapterChunk,
    CurrentState,
    FeedbackEvent,
    OutlineNode,
    PlotLedger,
    Project,
    StoryWiki,
    StyleExemplar,
)


def _trim(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    head = max(limit // 3, 1)
    return value[:head] + "\n...[按预算裁剪]...\n" + value[-(limit - head - 14) :]


def _compact_chapter_outline(value: dict[str, Any]) -> dict[str, Any]:
    """Keep the authored chapter contract without recursively embedded UI briefs."""
    allowed = {
        "title_candidates", "reader_experience", "goal", "conflict", "characters", "opening",
        "beats", "style_direction", "hook", "ending_image", "must_avoid", "protagonist_change",
    }
    return {key: value[key] for key in allowed if key in value}


def _compact_story_plan(
    value: dict[str, Any],
    chapter_sequence: int,
    *,
    include_chapter_direction: bool = True,
) -> dict[str, Any]:
    allowed = {
        "title", "goal", "chapter_range", "reader_promise", "starting_state", "central_pressure",
        "midpoint_change", "climax_choice", "ending_state", "progression_gain", "relationship_change",
        "protected_reveals", "ending_hook", "stage", "conflict", "resolution",
    }
    result = {key: value[key] for key in allowed if key in value}
    directions = (
        value.get("chapter_directions") or value.get("first_three_chapters") or []
        if include_chapter_direction
        else []
    )
    current = next(
        (
            item for item in directions
            if isinstance(item, dict) and int(item.get("sequence") or 0) == chapter_sequence
        ),
        None,
    )
    if current:
        result["current_chapter_mandate"] = current
    return result


def _compact_style_profile(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "writing_contract", "author_constitution", "prose", "pov", "pace", "tone", "style_reference",
        "reader_promise", "lasting_feeling", "non_negotiables", "chapter_test", "ai_mandate",
    }
    return {key: value[key] for key in allowed if key in value}


def _serialized_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def _chapter_in_range(chapter_sequence: int, value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, int) for item in value)
        and value[0] <= chapter_sequence <= value[1]
    )


def _strategic_memory(
    style_profile: dict[str, Any], chapter_sequence: int, scene_entities: list[str]
) -> dict[str, Any]:
    """Extract unique long-range intent from the creation blueprint without copying its nested duplicates."""
    blueprint = style_profile.get("creation_blueprint")
    if not isinstance(blueprint, dict):
        return {}
    creation = blueprint.get("creation_v2") if isinstance(blueprint.get("creation_v2"), dict) else {}
    book = blueprint.get("book_blueprint") if isinstance(blueprint.get("book_blueprint"), dict) else {}
    stages = creation.get("stages") if isinstance(creation.get("stages"), list) else []
    current_stage = next(
        (
            stage for stage in stages
            if isinstance(stage, dict) and _chapter_in_range(chapter_sequence, stage.get("chapter_range"))
        ),
        {},
    )
    character_sources = blueprint.get("characters") or creation.get("characters") or []
    relevant_characters = [
        character for character in character_sources
        if isinstance(character, dict) and str(character.get("name") or "") in scene_entities
    ]
    return {
        "core_intent": creation.get("core") or {
            "story_question": blueprint.get("story_question") or book.get("story_question"),
            "reader_promise": book.get("reader_promise"),
            "story_engine": book.get("story_engine"),
        },
        "creative_brief": creation.get("creative_brief") or [],
        "protagonist_design": creation.get("protagonist") or {},
        "current_stage": current_stage,
        "world_rules": creation.get("world") or blueprint.get("world_engine") or {},
        "story_engine": creation.get("engine") or {},
        "confirmed_direction": blueprint.get("creation_direction") or {},
        "external_research": blueprint.get("web_research") or {},
        "promise_ledger": book.get("promise_ledger") or [],
        "opening_strategy": book.get("opening_strategy") if chapter_sequence <= 30 else {},
        "story_engine_variations": book.get("story_engine_variations") or [],
        "endgame_direction": book.get("endgame_direction") or creation.get("core", {}).get("ending_direction"),
        "scene_character_designs": relevant_characters,
        "rule": (
            "creative_brief 是作者可见且可修改的最高优先创作依据；其余结构字段是执行索引。"
            "若二者冲突，以 creative_brief 和作者后来确认的章纲/正文为准。"
            "external_research 只是带来源的现实资料，不是小说 Canon；不得用它覆盖人物经历、世界规则或已发布正文。"
        ),
    }


_NODE_CONTEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "world-simulator": (
        "project", "chapter_sequence", "planning_precedence", "story_position", "chapter_outline", "beat_card",
        "scene_entities", "strategic_memory", "living_memory", "canon", "wiki", "active_state",
        "foreshadowing", "retrieval_hits", "charter",
    ),
    "novel-architect": (
        "project", "chapter_sequence", "planning_precedence", "story_position", "chapter_outline", "beat_card",
        "scene_entities", "strategic_memory", "living_memory", "canon", "wiki", "active_state",
        "foreshadowing", "recent_chapters", "retrieval_hits", "pageindex",
        "style_profile", "style_exemplars", "author_feedback", "charter", "genre_pack", "rewrite",
    ),
    "novel-writer": (
        "project", "chapter_sequence", "planning_precedence", "story_position", "chapter_outline", "beat_card",
        "scene_entities", "strategic_memory", "living_memory", "canon", "wiki", "active_state",
        "foreshadowing", "recent_chapters", "retrieval_hits", "pageindex",
        "writing_guidance", "style_profile", "style_exemplars", "author_feedback", "charter", "genre_pack", "rewrite",
    ),
    "novel-editor": (
        "project", "chapter_sequence", "planning_precedence", "chapter_outline", "scene_entities", "strategic_memory",
        "living_memory", "canon", "active_state", "style_profile", "charter", "rewrite",
    ),
    "novel-critic": (
        "project", "chapter_sequence", "planning_precedence", "story_position", "chapter_outline", "scene_entities",
        "strategic_memory", "living_memory", "canon", "active_state", "foreshadowing",
        "style_profile", "charter",
    ),
    "novel-state-extractor": (
        "project", "chapter_sequence", "scene_entities", "strategic_memory", "active_state",
        "foreshadowing", "canon", "wiki",
    ),
}

_NODE_CONTEXT_BUDGETS = {
    "world-simulator": 14_000,
    "novel-architect": 15_000,
    "novel-writer": 15_000,
    "novel-editor": 12_000,
    "novel-critic": 12_000,
    "novel-state-extractor": 10_000,
}


def _fit_node_context(view: dict[str, Any], budget: int) -> list[str]:
    """Trim only re-fetchable evidence; authored constraints and current story state are protected."""
    reductions: list[str] = []

    def over_budget() -> bool:
        return _serialized_size(view) > budget

    guidance = view.get("writing_guidance")
    if over_budget() and isinstance(guidance, dict) and guidance.get("source_excerpts"):
        guidance["source_excerpts"] = []
        reductions.append("writing_guidance.source_excerpts")
    pageindex = view.get("pageindex")
    if over_budget() and isinstance(pageindex, dict) and pageindex.get("source_excerpts"):
        pageindex["source_excerpts"] = []
        reductions.append("pageindex.source_excerpts")
    if over_budget() and isinstance(view.get("genre_pack"), dict):
        genre = view["genre_pack"]
        if genre.get("scene_templates") or genre.get("plot_devices"):
            genre["scene_templates"] = []
            genre["plot_devices"] = []
            reductions.append("genre_pack.examples")
    if over_budget() and isinstance(view.get("retrieval_hits"), list):
        view["retrieval_hits"] = view["retrieval_hits"][:5]
        reductions.append("retrieval_hits.after_top_5")
    if over_budget() and isinstance(view.get("wiki"), list):
        view["wiki"] = [
            {**item, "content": _trim(str(item.get("content") or ""), 700)}
            for item in view["wiki"][:8] if isinstance(item, dict)
        ]
        reductions.append("wiki.low_priority_details")
    if over_budget() and isinstance(view.get("retrieval_hits"), list):
        view["retrieval_hits"] = view["retrieval_hits"][:3]
        reductions.append("retrieval_hits.after_top_3")
    if over_budget() and isinstance(view.get("retrieval_hits"), list):
        view["retrieval_hits"] = [
            {**item, "content": _trim(str(item.get("content") or ""), 500)}
            for item in view["retrieval_hits"] if isinstance(item, dict)
        ]
        reductions.append("retrieval_hits.long_excerpts")
    if over_budget() and isinstance(view.get("wiki"), list):
        view["wiki"] = [
            {**item, "content": _trim(str(item.get("content") or ""), 350)}
            for item in view["wiki"][:6] if isinstance(item, dict)
        ]
        reductions.append("wiki.after_top_6")
    return reductions


def context_for_node(pack: dict[str, Any], node_name: str) -> dict[str, Any]:
    """Create a task-specific context view while retaining the complete canonical pack in memory/storage."""
    canonical = "novel-critic" if node_name.startswith("novel-critic") else (
        "novel-editor" if node_name.startswith("novel-editor") else node_name
    )
    fields = _NODE_CONTEXT_FIELDS.get(canonical, _NODE_CONTEXT_FIELDS["novel-writer"])
    view = {field: deepcopy(pack[field]) for field in fields if field in pack}
    view["context_manifest"] = {
        "schema_version": "node-context.v1",
        "node": canonical,
        "included_sections": [field for field in fields if field in pack],
        "source_pack_characters": int(pack.get("serialized_characters") or _serialized_size(pack)),
        "retrieval_policy": "完整资料保存在项目知识库；本视图包含本节点的常驻约束与按章召回结果。",
    }
    budget = _NODE_CONTEXT_BUDGETS.get(canonical, 14_500)
    view["context_manifest"]["input_character_budget"] = budget
    view["context_manifest"]["reduced_refetchable_sections"] = []
    view["context_manifest"]["protected_context_over_budget"] = False
    view["serialized_characters"] = 0
    reductions = _fit_node_context(view, budget)
    view["context_manifest"]["reduced_refetchable_sections"] = reductions
    if _serialized_size(view) > budget:
        reductions.extend(item for item in _fit_node_context(view, budget) if item not in reductions)
        view["context_manifest"]["reduced_refetchable_sections"] = reductions
    view["serialized_characters"] = _serialized_size(view)
    view["serialized_characters"] = _serialized_size(view)
    view["context_manifest"]["protected_context_over_budget"] = view["serialized_characters"] > budget
    return view


async def build_context_pack(db: AsyncSession, project: Project, chapter_sequence: int) -> dict[str, Any]:
    current_chapter = await db.scalar(
        select(Chapter).where(
            Chapter.project_id == project.id,
            Chapter.chapter_sequence == chapter_sequence,
        )
    )
    recent_stmt: Select[tuple[Chapter]] = (
        select(Chapter)
        .where(
            Chapter.project_id == project.id,
            Chapter.chapter_sequence < chapter_sequence,
            Chapter.content.is_not(None),
            Chapter.content != "",
        )
        .order_by(Chapter.chapter_sequence.desc())
        .limit(5)
    )
    outline_node = await db.scalar(
        select(OutlineNode).where(
            OutlineNode.project_id == project.id,
            OutlineNode.layer == "L5",
            OutlineNode.seq == chapter_sequence,
        )
    )
    raw_outline_content = (outline_node.meta if outline_node else {}) or {}
    outline_content = _compact_chapter_outline(raw_outline_content)
    volume_outline_node = await db.scalar(
        select(OutlineNode).where(
            OutlineNode.project_id == project.id,
            OutlineNode.layer == "L4",
            OutlineNode.seq == (current_chapter.volume_sequence if current_chapter else 1),
        )
    )
    arc_outlines_nodes = list(
        (
            await db.scalars(
                select(OutlineNode).where(
                    OutlineNode.project_id == project.id,
                    OutlineNode.layer == "L3",
                )
            )
        ).all()
    )
    current_arc = next(
        (
            node
            for node in arc_outlines_nodes
            if node.meta.get("chapter_range")
            and node.meta["chapter_range"][0] <= chapter_sequence <= node.meta["chapter_range"][1]
        ),
        None,
    )
    entities = list(
        dict.fromkeys(
            [
                project.protagonist_name,
                *outline_content.get("characters", []),
                *outline_content.get("cast", []),
            ]
        )
    )

    wiki_filter = StoryWiki.project_id == project.id
    if entities:
        wiki_filter = or_(
            wiki_filter & StoryWiki.title.in_(entities), wiki_filter & StoryWiki.aliases.overlap(entities)
        )
    wiki_pages = list(
        (
            await db.scalars(
                select(StoryWiki).where(wiki_filter).order_by(StoryWiki.last_updated_chapter.desc()).limit(24)
            )
        ).all()
    )
    canon_pages = list(
        (
            await db.scalars(
                select(StoryWiki)
                .where(StoryWiki.project_id == project.id, StoryWiki.category.in_(["canon_rule", "worldview"]))
                .limit(12)
            )
        ).all()
    )
    page_map = {page.id: page for page in [*wiki_pages, *canon_pages]}

    hot_states = list(
        (
            await db.scalars(
                select(CurrentState)
                .where(
                    CurrentState.project_id == project.id,
                    CurrentState.last_chapter_sequence < chapter_sequence,
                    or_(
                        CurrentState.temperature.in_(["hot", "warm"]),
                        CurrentState.entity_key.in_(entities),
                    ),
                )
                .order_by(CurrentState.last_chapter_sequence.desc(), CurrentState.confidence.desc())
                .limit(50)
            )
        ).all()
    )
    foreshadows = list(
        (
            await db.scalars(
                select(PlotLedger)
                .where(
                    PlotLedger.project_id == project.id,
                    PlotLedger.status.in_(["open", "reminded"]),
                    PlotLedger.planted_chapter < chapter_sequence,
                )
                .order_by(PlotLedger.is_yy.desc(), PlotLedger.due_chapter.asc().nullslast())
                .limit(10)
            )
        ).all()
    )
    recent = list(reversed(list((await db.scalars(recent_stmt)).all())))
    retrieval_query = " ".join(
        str(value) for value in [outline_content.get("goal"), outline_content.get("hook"), *entities] if value
    )
    try:
        hits = await hybrid_search(
            db,
            project.id,
            retrieval_query or project.one_sentence,
            entities=entities,
            chapter_before=chapter_sequence,
            limit=10,
        )
    except (httpx.HTTPError, ValueError):
        hits = []
    pageindex_nodes: list[dict[str, Any]] = []
    pageindex_excerpts: list[dict[str, Any]] = []
    if chapter_sequence > 5:
        try:
            pageindex_nodes = await pageindex_navigate(
                db, project.id, retrieval_query or project.one_sentence,
                thread_id=f"context:{project.id}:{chapter_sequence}", max_nodes=6,
            )
            ranges = [node.get("chapter_range") for node in pageindex_nodes]
            range_filters = [
                ChapterChunk.chapter_sequence.between(int(value[0]), min(int(value[1]), chapter_sequence - 1))
                for value in ranges
                if isinstance(value, list) and len(value) == 2 and value[0] is not None and value[1] is not None
            ]
            if range_filters:
                chunks = list(
                    (
                        await db.scalars(
                            select(ChapterChunk)
                            .where(ChapterChunk.project_id == project.id, or_(*range_filters))
                            .order_by(ChapterChunk.chapter_sequence.desc(), ChapterChunk.chunk_index.asc())
                            .limit(8)
                        )
                    ).all()
                )
                pageindex_excerpts = [
                    {"chapter_sequence": chunk.chapter_sequence, "content": _trim(chunk.content, 1200)}
                    for chunk in chunks
                ]
        except Exception:
            pageindex_nodes, pageindex_excerpts = [], []
    guide_query = " ".join(
        str(value)
        for value in (
            project.genre,
            outline_content.get("reader_experience"),
            outline_content.get("goal"),
            outline_content.get("conflict"),
            outline_content.get("style_direction"),
        )
        if value
    )
    guide_tags = [tag for tag in ("人物", "情节", "对白", "节奏", "伏笔", "悬疑", "言情", "玄幻") if tag in guide_query]
    method_cards: list[dict[str, Any]] = []
    guide_excerpts: list[dict[str, Any]] = []
    if get_settings().writing_knowledge_enabled:
        try:
            method_cards = await writing_method_card_search(db, guide_query, tags=guide_tags or None, limit=4)
            guide_excerpts = await writing_guide_search(db, guide_query, tags=guide_tags or None, limit=4)
        except Exception:
            # The story pipeline remains available while a separately rebuildable guide index is offline.
            method_cards = []
            guide_excerpts = []
    if method_cards:
        # Method cards are already source-grounded executable summaries; keep one excerpt only for traceability.
        guide_excerpts = guide_excerpts[:1]

    entity_memory_hits = await search_entity_memory(
        db, project.id,
        query=retrieval_query or project.one_sentence,
        entities=entities,
        chapter_before=chapter_sequence,
        limit=16,
    )

    latest_chain = await get_latest_summary(db, project.id)

    style_exemplars = list(
        (
            await db.scalars(
                select(StyleExemplar)
                .where(
                    StyleExemplar.project_id == project.id,
                    StyleExemplar.chapter_sequence < chapter_sequence,
                )
                .order_by(StyleExemplar.created_at.desc())
                .limit(4)
            )
        ).all()
    )
    feedback_events = list(
        (
            await db.scalars(
                select(FeedbackEvent)
                .where(
                    FeedbackEvent.project_id == project.id,
                    FeedbackEvent.chapter_sequence < chapter_sequence,
                    FeedbackEvent.event_type == "manuscript_edit",
                )
                .order_by(FeedbackEvent.created_at.desc())
                .limit(3)
            )
        ).all()
    )

    genre_pack = None
    try:
        genre_pack = await load_genre_pack(db, project.genre, limit_cards=4, limit_scenes=3, limit_devices=3)
    except Exception:
        pass

    complexity = len(entities) + len(foreshadows)
    # 这是输入字符预算而非内容目标。前期不为凑窗口注入无关资料，长篇后期允许召回自然增长。
    token_budget = 32_000 if complexity > 12 else 28_000 if complexity > 6 else 24_000
    pack = {
        "schema_version": "context-pack.v3",
        "token_budget": token_budget,
        "project": {
            "title": project.title,
            "genre": project.genre,
            "premise": project.one_sentence,
            "protagonist": project.protagonist_name,
            "protagonist_personality": project.protagonist_personality,
        },
        "chapter_sequence": chapter_sequence,
        "story_position": {
            "volume_sequence": current_chapter.volume_sequence if current_chapter else 1,
            "volume_title": volume_outline_node.title if volume_outline_node else "",
            "volume_plan": _compact_story_plan(
                (volume_outline_node.meta if volume_outline_node else {}) or {},
                chapter_sequence,
                include_chapter_direction=False,
            ),
            "arc_title": current_arc.title if current_arc else "",
            "arc_plan": _compact_story_plan(
                (current_arc.meta if current_arc else {}) or {},
                chapter_sequence,
                include_chapter_direction=False,
            ),
        },
        "chapter_outline": outline_content,
        "planning_precedence": [
            "author_instruction",
            "published_previous_chapter_ending_for_opening_continuity",
            "chapter_outline",
            "published_story_facts",
            "latest_dynamic_creative_brief",
            "volume_goal_and_protected_reveals",
            "early_opening_draft",
        ],
        "scene_entities": entities,
        "strategic_memory": _strategic_memory(
            project.style_profile if isinstance(project.style_profile, dict) else {},
            chapter_sequence,
            entities,
        ),
        "living_memory": {
            "rule": (
                "这是人物带进本章的主观余波，不是待复述的前情摘要；"
                "只让它改变注意、误读、措辞或动作。rolling_summary 是前 10 章的压缩脉络，"
                "用于感知情节节奏和未闭合钩子，不直接复述。"
            ),
            "previous_ending": (
                recent[-1].content[-2000:] if recent and recent[-1].content else ""
            ),
            "previous_summary": recent[-1].summary if recent else "",
            "rolling_summary": latest_chain.rolling_summary if latest_chain else "",
            "long_range_summary": latest_chain.volume_summary if latest_chain else "",
            "carried_residue": [
                {
                    "character": hit.entity_key,
                    "field": hit.field,
                    "value": hit.value,
                    "chapter": hit.chapter_sequence,
                    "confidence": hit.confidence,
                    "relevance": round(hit.score, 2),
                }
                for hit in entity_memory_hits
            ],
        },
        "canon": [
            {"slug": page.slug, "content": page.content}
            for page in page_map.values()
            if page.category in {"canon_rule", "worldview"}
        ],
        "wiki": [
            {
                "slug": page.slug,
                "title": page.title,
                "category": page.category,
                "content": page.content,
                "sources": page.source_chapters,
            }
            for page in page_map.values()
            if page.category not in {"canon_rule", "worldview"}
        ],
        "active_state": [
            {
                "entity_type": state.entity_type,
                "entity_key": state.entity_key,
                "field": state.field,
                "value": state.value,
                "confidence": state.confidence,
                "source_event_id": str(state.source_event_id),
            }
            for state in hot_states
        ],
        "foreshadowing": [
            {
                "content": item.description,
                "type": item.type,
                "is_yy": item.is_yy,
                "planted_chapter": item.planted_chapter,
                "target_chapter": item.due_chapter,
                "mentioned_chapters": item.mentioned_chapters,
                "status": item.status,
            }
            for item in foreshadows
        ],
        "recent_chapters": [
            {
                "sequence": chapter.chapter_sequence,
                "title": chapter.title,
                "summary": chapter.summary,
            }
            for chapter in recent
        ],
        "retrieval_hits": [asdict(hit) for hit in hits],
        "pageindex": {"selected_nodes": pageindex_nodes, "source_excerpts": pageindex_excerpts},
        "writing_guidance": {
            "method_cards": method_cards,
            "source_excerpts": guide_excerpts,
            "rule": "只把方法当建议，不得把教程内容写成故事事实；引用建议必须保留来源 ID。",
        },
        "style_profile": {
            **_compact_style_profile(project.style_profile if isinstance(project.style_profile, dict) else {}),
            "writing_contract": (
                project.style_profile.get("writing_contract")
                if isinstance(project.style_profile, dict) and project.style_profile.get("writing_contract")
                else get_genre_writing_contract(project.genre)
            ),
        },
        "style_exemplars": [
            {
                "chapter_sequence": item.chapter_sequence,
                "category": item.category,
                "content": item.content,
                "rule": "这是作者亲自改写并保留的正面范例；学习叙述距离和措辞习惯，不复制句子。",
            }
            for item in style_exemplars
        ],
        "author_feedback": [
            {
                "chapter_sequence": item.chapter_sequence,
                "change_ratio": item.payload.get("change_ratio"),
                "inserted_characters": item.payload.get("inserted_characters"),
                "deleted_characters": item.payload.get("deleted_characters"),
            }
            for item in feedback_events
        ],
    }
    charter = await get_charter(db, project.id)
    if charter:
        pack["charter"] = {
            "narrative_focus": charter.narrative_focus,
            "red_lines": charter.red_lines,
            "mandates": charter.mandates,
            "target_readers": charter.target_readers,
            "tone_reference": charter.tone_reference,
        }
        pack["charter_prompt"] = render_charter_prompt(charter)
    if genre_pack:
        pack["genre_pack"] = {
            "genre": genre_pack.genre,
            "method_cards": genre_pack.method_cards,
            "scene_templates": genre_pack.scene_templates,
            "plot_devices": genre_pack.plot_devices,
        }
        pack["genre_prompt"] = render_genre_prompt(genre_pack)
    rewrite_log = (current_chapter.generation_log or {}) if current_chapter else {}
    rewrite_brief = rewrite_log.get("rewrite_brief") if rewrite_log.get("rewrite_requested") else None
    if rewrite_brief:
        pack["rewrite"] = rewrite_brief
    serialized_size = _serialized_size(pack)
    if serialized_size > token_budget:
        pack["retrieval_hits"] = pack["retrieval_hits"][:5]
        pack["pageindex"]["source_excerpts"] = pack["pageindex"]["source_excerpts"][:3]
        pack["writing_guidance"]["source_excerpts"] = pack["writing_guidance"]["source_excerpts"][:2]
        pack["wiki"] = [{**page, "content": _trim(page["content"], 1200)} for page in pack["wiki"][:12]]
        pack["canon"] = [{**page, "content": _trim(page["content"], 1200)} for page in pack["canon"][:8]]
        pack["active_state"] = pack["active_state"][:24]
        pack["living_memory"]["carried_residue"] = pack["living_memory"]["carried_residue"][:10]
        pack["recent_chapters"] = pack["recent_chapters"][-3:]
        pack["budget_trimmed"] = True
    else:
        pack["budget_trimmed"] = False
    if _serialized_size(pack) > token_budget:
        pack["writing_guidance"]["source_excerpts"] = []
        pack["pageindex"]["source_excerpts"] = []
        pack["retrieval_hits"] = pack["retrieval_hits"][:3]
        pack["wiki"] = [{**page, "content": _trim(page["content"], 700)} for page in pack["wiki"][:8]]
        pack["canon"] = [{**page, "content": _trim(page["content"], 700)} for page in pack["canon"][:6]]
    pack["serialized_characters"] = _serialized_size(pack)
    return pack


def summarize_creation_brief(pack: dict[str, Any]) -> dict[str, Any]:
    """把完整 context pack 压缩成用户可读、章纲可直接注入的创作简报。"""
    chapter = int(pack.get("chapter_sequence") or 1)
    due_foreshadowing = []
    for item in pack.get("foreshadowing", []):
        target = item.get("target_chapter")
        distance = target - chapter if isinstance(target, int) else None
        if distance is not None and distance <= 0:
            urgency = "overdue"
        elif distance is not None and distance <= 5:
            urgency = "due"
        else:
            urgency = "active"
        due_foreshadowing.append({**item, "urgency": urgency})

    character_states: dict[str, list[dict[str, Any]]] = {}
    for state in pack.get("active_state", []):
        key = str(state.get("entity_key") or "")
        if key:
            character_states.setdefault(key, []).append({"field": state.get("field"), "value": state.get("value")})

    position = pack.get("story_position", {})
    reasons = []
    urgent = [f for f in due_foreshadowing if f["urgency"] in {"overdue", "due"}]
    if urgent:
        reasons.append(f"有 {len(urgent)} 条伏笔进入推进或回收窗口")
    if position.get("arc_title"):
        reasons.append(f"当前需要完成事件弧「{position['arc_title']}」的阶段任务")
    if not reasons:
        reasons.append("承接前章结果并推动当前卷目标")

    return {
        "schema_version": "creation-brief.v1",
        "chapter_sequence": chapter,
        "position": position,
        "why_this_chapter": "；".join(reasons),
        "recent_chapters": pack.get("recent_chapters", []),
        "scene_entities": pack.get("scene_entities", []),
        "character_states": character_states,
        "due_foreshadowing": due_foreshadowing,
        "writing_contract": pack.get("style_profile", {}).get("writing_contract", {}),
        "author_constitution": pack.get("style_profile", {}).get("author_constitution", {}),
        "writing_guidance": pack.get("writing_guidance", {}),
        "charter_prompt": pack.get("charter_prompt", ""),
        "charter": pack.get("charter", {}),
        "genre_prompt": pack.get("genre_prompt", ""),
        "genre_pack": pack.get("genre_pack", {}),
    }
