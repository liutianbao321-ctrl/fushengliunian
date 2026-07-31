from __future__ import annotations

import asyncio
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.engine.changes import keep_evidenced_changes, merge_extractions
from app.engine.context import build_context_pack
from app.engine.humanizer import calculate_anti_ai_scores
from app.engine.publisher import create_candidate_revision, publish_candidate, stage_generated_draft
from app.engine.quality import evaluate_quality_gates
from app.engine.runtime import run_agent_node
from app.models import BeatCard, Chapter, ChapterRevision, GenerationNodeRun, GenerationRun, Project
from app.services.events import append_project_event, publish_committed_event
from app.utils.canonical import payload_hash


def utcnow() -> datetime:
    return datetime.now(UTC)


class GenerationPaused(RuntimeError):
    pass


HARD_REVIEW_CATEGORIES = {
    "canon_contradiction",
    "knowledge_boundary",
    "missing_required_scene",
    "broken_causality",
    "character_betrayal",
    "author_non_negotiable",
}

NARRATIVE_REPAIR_CATEGORIES = {
    "consciousness_continuity",
    "character_specificity",
    "dialogue_subtext",
    "pov_immersion",
    "prose_naturalness",
    "broken_causality",
}


def _review_score(review: dict[str, Any]) -> float:
    try:
        return float(review.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _prose_length(content: str) -> int:
    return len("".join(content.split()))


def _hard_review_issues(review: dict[str, Any]) -> list[dict[str, Any]]:
    issues = review.get("issues") if isinstance(review.get("issues"), list) else []
    return [
        issue
        for issue in issues
        if isinstance(issue, dict)
        and (
            issue.get("blocking") is True
            or str(issue.get("hard_category") or issue.get("category") or "") in HARD_REVIEW_CATEGORIES
        )
        and len(str(issue.get("evidence") or "").strip()) >= 4
    ]


def _repairable_review_issues(review: dict[str, Any]) -> list[dict[str, Any]]:
    """Select evidenced narrative failures that need an edit, not another comment."""
    hard = _hard_review_issues(review)
    hard_ids = {str(issue.get("id") or id(issue)) for issue in hard}
    issues = review.get("issues") if isinstance(review.get("issues"), list) else []
    narrative = [
        issue
        for issue in issues
        if isinstance(issue, dict)
        and str(issue.get("id") or id(issue)) not in hard_ids
        and str(issue.get("severity") or "").lower() in {"critical", "major"}
        and str(issue.get("category") or "") in NARRATIVE_REPAIR_CATEGORIES
        and len(str(issue.get("evidence") or "").strip()) >= 4
    ]
    return [*hard, *narrative[:4]]


def _evidence_occurs_in_content(issue: dict[str, Any], content: str) -> bool:
    """Reject critic paraphrases: repair evidence must be locatable verbatim in the draft."""
    evidence = issue.get("evidence")
    if isinstance(evidence, dict):
        evidence = evidence.get("quote") or evidence.get("text") or ""
    evidence_text = str(evidence or "").strip()
    compact_content = "".join(content.split())
    quoted = re.findall(r"['‘“\"]([^'’”\"]{4,240})['’”\"]", evidence_text)
    candidates = quoted or [evidence_text.removeprefix("正文：").removeprefix("正文:")]
    return any("".join(candidate.split()) in compact_content for candidate in candidates)


def _cross_chapter_evidence_occurs(
    issue: dict[str, Any], content: str, previous_ending: str
) -> bool:
    """Require verbatim evidence from both sides before accepting a transition diagnosis."""
    category = str(issue.get("hard_category") or issue.get("category") or "")
    if category not in {"consciousness_continuity", "broken_causality", "canon_contradiction"}:
        return False
    evidence = issue.get("evidence")
    if isinstance(evidence, dict):
        evidence = evidence.get("quote") or evidence.get("text") or ""
    evidence_text = str(evidence or "").strip()
    if not previous_ending.strip() or not any(marker in evidence_text for marker in ("上一章", "前章", "上章")):
        return False

    fragments = [
        fragment.strip(" ：:'‘’\"“”")
        for line in evidence_text.splitlines()
        for fragment in re.split(r"(?:\.{3,}|…+|；)", line)
    ]
    fragments = [
        re.sub(r"^(?:上一章(?:结尾)?|前章(?:结尾)?|上章(?:结尾)?|本章(?:开头)?|第\d+章(?:开头)?)[：:]", "", fragment)
        for fragment in fragments
    ]
    fragments = [fragment for fragment in fragments if len("".join(fragment.split())) >= 6]
    compact_previous = "".join(previous_ending.split())
    compact_current = "".join(content.split())
    return (
        any("".join(fragment.split()) in compact_previous for fragment in fragments)
        and any("".join(fragment.split()) in compact_current for fragment in fragments)
    )


def _evidenced_repair_issues(
    review: dict[str, Any], content: str, previous_ending: str = ""
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = _repairable_review_issues(review)
    accepted = [
        issue
        for issue in candidates
        if _evidence_occurs_in_content(issue, content)
        or _cross_chapter_evidence_occurs(issue, content, previous_ending)
    ]
    rejected = [issue for issue in candidates if issue not in accepted]
    return accepted, rejected


def _rewrite_draft(context_pack: dict[str, Any], chapter: Chapter) -> dict[str, str] | None:
    rewrite = context_pack.get("rewrite")
    if not isinstance(rewrite, dict):
        return None
    source = str(rewrite.get("source_content") or "").strip()
    if not source:
        return None
    return {"content": source, "summary": chapter.summary}


async def _resolve_beat_card(
    db: AsyncSession,
    project: Project,
    chapter: Chapter,
    chapter_outline: dict[str, Any],
) -> dict[str, Any]:
    """在 writer 前解析本章 Beat 卡：confirmed 优先；否则复用 draft；否则生成并存 draft。

    不阻断自动流：仅在尚无任何卡时生成一次，生成失败则降级为空卡继续写正文。
    """
    existing = await db.scalar(select(BeatCard).where(BeatCard.chapter_id == chapter.id))
    if existing is not None and isinstance(existing.fields, dict) and existing.fields:
        return existing.fields if isinstance(existing.fields, dict) else {}
    outline_beats = chapter_outline.get("beats") if isinstance(chapter_outline, dict) else None
    if isinstance(outline_beats, list) and len(outline_beats) >= 1:
        return {}
    try:
        from app.engine.blueprint import generate_beat_card

        await generate_beat_card(db, {"chapter_id": str(chapter.id)})
        card = await db.scalar(select(BeatCard).where(BeatCard.chapter_id == chapter.id))
        return card.fields if card and isinstance(card.fields, dict) else {}
    except Exception:
        return {}


async def _record_progress(db: AsyncSession, run: GenerationRun, node_name: str, status: str) -> None:
    order = [
        "world-simulator",
        "novel-architect",
        "novel-guardian",
        "novel-writer",
        "novel-humanizer",
        "novel-critic-draft",
        "novel-editor-repair",
        "novel-critic-recheck",
        "novel-state-extractor",
    ]
    progress = (
        int(((order.index(node_name) + (1 if status == "completed" else 0)) / len(order)) * 100)
        if node_name in order
        else 0
    )
    event = await append_project_event(
        db,
        run.project_id,
        "generation_progress",
        {
            "run_id": str(run.id),
            "chapter_sequence": run.chapter_sequence,
            "node": node_name,
            "step": node_name,
            "status": status,
            "progress": progress,
        },
        run.id,
    )
    await db.commit()
    await publish_committed_event(event)


async def _run_node(
    db: AsyncSession,
    run: GenerationRun,
    node_name: str,
    payload: dict[str, Any],
    *,
    cache_bust: bool = False,
) -> dict[str, Any]:
    await db.refresh(run)
    if run.status == "pausing":
        raise GenerationPaused("生成已在节点边界暂停")
    input_hash = payload_hash(payload)
    # 重试路径（如 Guardian 失败后的修复型重跑）绕过 input_hash 缓存，
    # 否则同输入会命中旧缓存被跳过，导致重试必然失败。
    if not cache_bust:
        completed = await db.scalar(
            select(GenerationNodeRun)
            .where(
                GenerationNodeRun.run_id == run.id,
                GenerationNodeRun.node_name == node_name,
                GenerationNodeRun.input_hash == input_hash,
                GenerationNodeRun.status == "completed",
            )
            .order_by(GenerationNodeRun.attempt.desc())
            .limit(1)
        )
        if completed:
            return completed.output_payload

    max_attempt = await db.scalar(
        select(func.max(GenerationNodeRun.attempt)).where(
            GenerationNodeRun.run_id == run.id,
            GenerationNodeRun.node_name == node_name,
        )
    )
    attempt = int(max_attempt or 0) + 1
    node = GenerationNodeRun(
        run_id=run.id,
        node_name=node_name,
        attempt=attempt,
        input_payload=payload,
        input_hash=input_hash,
        status="running",
        model_name=get_settings().llm_model,
        prompt_version=f"{node_name}.v1",
    )
    db.add(node)
    run.current_node = node_name
    run.heartbeat_at = utcnow()
    await db.commit()
    await _record_progress(db, run, node_name, "running")
    try:
        output = await asyncio.wait_for(
            run_agent_node(node_name, payload, f"{run.id}:{node_name}:{attempt}"),
            timeout=float(get_settings().generation_node_timeout_seconds),
        )
    except TimeoutError as exc:
        message = f"{node_name} 节点超过 {get_settings().generation_node_timeout_seconds} 秒仍未完成"
        node.status = "failed"
        node.error_message = message
        node.completed_at = utcnow()
        await db.commit()
        await _record_progress(db, run, node_name, "failed")
        raise TimeoutError(message) from exc
    except Exception as exc:
        node.status = "failed"
        node.error_message = str(exc)[:4000]
        node.completed_at = utcnow()
        await db.commit()
        await _record_progress(db, run, node_name, "failed")
        raise
    node.output_payload = output
    node.output_hash = payload_hash(output)
    node.status = "completed"
    node.completed_at = utcnow()
    run.heartbeat_at = utcnow()
    await db.commit()
    await _record_progress(db, run, node_name, "completed")
    return output


async def _run_observers(
    db: AsyncSession,
    run: GenerationRun,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    names = ["observer-social", "observer-environment", "observer-narrative"]
    cached: dict[str, dict[str, Any]] = {}
    pending: list[tuple[str, GenerationNodeRun]] = []
    for name in names:
        input_hash = payload_hash(payload)
        completed = await db.scalar(
            select(GenerationNodeRun).where(
                GenerationNodeRun.run_id == run.id,
                GenerationNodeRun.node_name == name,
                GenerationNodeRun.input_hash == input_hash,
                GenerationNodeRun.status == "completed",
            )
        )
        if completed:
            cached[name] = completed.output_payload
            continue
        max_attempt = await db.scalar(
            select(func.max(GenerationNodeRun.attempt)).where(
                GenerationNodeRun.run_id == run.id,
                GenerationNodeRun.node_name == name,
            )
        )
        node = GenerationNodeRun(
            run_id=run.id,
            node_name=name,
            attempt=int(max_attempt or 0) + 1,
            input_payload=payload,
            input_hash=input_hash,
            status="running",
            model_name=get_settings().llm_model,
            prompt_version=f"{name}.v1",
        )
        db.add(node)
        pending.append((name, node))
    await db.commit()
    for name, _ in pending:
        await _record_progress(db, run, name, "running")

    results = await asyncio.gather(
        *(run_agent_node(name, payload, f"{run.id}:{name}:{node.attempt}") for name, node in pending),
        return_exceptions=True,
    )
    for (name, node), result in zip(pending, results, strict=False):
        node.completed_at = utcnow()
        if isinstance(result, Exception):
            node.status = "failed"
            node.error_message = str(result)[:4000]
        else:
            node.status = "completed"
            node.output_payload = result
            node.output_hash = payload_hash(result)
            cached[name] = result
    await db.commit()
    for name, node in pending:
        await _record_progress(db, run, name, node.status)
    failures = [node for _, node in pending if node.status == "failed"]
    if failures:
        raise RuntimeError(
            "Observer 并行提取失败: " + "；".join(node.error_message or node.node_name for node in failures)
        )
    return [cached[name] for name in names]


async def run_chapter_pipeline(db: AsyncSession, run: GenerationRun) -> bool:
    project = await db.get(Project, run.project_id)
    chapter = await db.scalar(
        select(Chapter).where(
            Chapter.project_id == run.project_id,
            Chapter.chapter_sequence == run.chapter_sequence,
        )
    )
    if project is None or chapter is None:
        raise RuntimeError("生成项目或章节不存在")

    context_pack = await build_context_pack(db, project, chapter.chapter_sequence)
    beat_card_fields = await _resolve_beat_card(db, project, chapter, context_pack.get("chapter_outline", {}))
    if beat_card_fields:
        context_pack["beat_card"] = beat_card_fields
    simulation = await _run_node(db, run, "world-simulator", {"context_pack": context_pack})
    # Guardian 失败→带反馈重跑 Architect，最多 3 轮；重跑路径绕过缓存并注入失败理由
    MAX_GUARDIAN_ROUNDS = 3
    guardian_feedback: Any = None
    beat_sheet: dict[str, Any] | None = None
    guardian: dict[str, Any] = {}
    for attempt_no in range(1, MAX_GUARDIAN_ROUNDS + 1):
        architect_payload: dict[str, Any] = {
            "context_pack": context_pack,
            "world_simulation": simulation,
        }
        if guardian_feedback is not None:
            architect_payload["guardian_feedback"] = guardian_feedback
        beat_sheet = await _run_node(
            db,
            run,
            "novel-architect",
            architect_payload,
            cache_bust=guardian_feedback is not None,
        )
        guardian = await _run_node(
            db,
            run,
            "novel-guardian",
            {"context_pack": context_pack, "world_simulation": simulation, "beat_sheet": beat_sheet},
        )
        if guardian.get("passed"):
            break
        if attempt_no < MAX_GUARDIAN_ROUNDS:
            guardian_feedback = guardian.get("failures") or guardian.get("issues") or guardian
    if not guardian.get("passed"):
        raise RuntimeError(
            "Guardian 未通过（已带反馈重试 " + str(MAX_GUARDIAN_ROUNDS) + " 轮）: "
            + str(guardian.get("failures") or guardian.get("issues"))
        )

    draft = _rewrite_draft(context_pack, chapter)
    if draft is None:
        draft = await _run_node(
            db,
            run,
            "novel-writer",
            {
                "context_pack": context_pack,
                "world_simulation": simulation,
                "beat_sheet": beat_sheet,
                "requirements": {"target_length": [3400, 4200], "hard_length_range": [2800, 5500]},
            },
        )
    rewrite = context_pack.get("rewrite") if isinstance(context_pack.get("rewrite"), dict) else None
    if rewrite and not rewrite.get("reextract_state"):
        optimized = await _run_node(
            db,
            run,
            "novel-editor",
            {
                "context_pack": context_pack,
                "beat_sheet": beat_sheet,
                "draft": draft,
                "critique": {
                    "issues": [
                        {
                            "id": "user-direction",
                            "category": "用户优化要求",
                            "problem": "按用户主动提出的方向优化正文",
                            "fix": rewrite.get("instruction") or rewrite.get("focus") or "改善正文",
                        }
                    ]
                },
                "requirements": {"preserve_complete_event_chain": True, "hard_length_range": [1000, 6500]},
            },
        )
        draft = {"content": optimized["content"], "summary": optimized.get("summary") or draft.get("summary", "")}
    # The writer owns the manuscript voice. A generic full-chapter polish pass
    # tended to average away character-specific phrasing before author review.
    content = str(draft["content"])
    summary = str(draft.get("summary") or "")
    initial_metrics = calculate_anti_ai_scores(content)
    await stage_generated_draft(
        db,
        project,
        chapter,
        run,
        content=content,
        summary=summary,
        beat_sheet=beat_sheet,
        generation_log={
            "run_id": str(run.id),
            "model": get_settings().llm_model,
            "analysis_status": "running",
            "analysis_message": "初稿已生成，正在独立审稿、返修和检查故事状态",
        },
    )
    draft_review = await _run_node(
        db,
        run,
        "novel-critic-draft",
        {"context_pack": context_pack, "beat_sheet": beat_sheet, "content": content},
    )
    final_review = draft_review
    final_metrics = initial_metrics
    editor_changes: list[dict[str, Any]] = []
    hard_issues = _hard_review_issues(draft_review)
    previous_ending = str(context_pack.get("living_memory", {}).get("previous_ending") or "")
    repair_issues, rejected_review_evidence = _evidenced_repair_issues(
        draft_review, content, previous_ending
    )
    editorial_rounds: list[dict[str, Any]] = [{
        "round": 0, "stage": "初稿", "score": _review_score(draft_review),
        "passed": bool(draft_review.get("passed")), "accepted": True,
        "word_count": _prose_length(content),
        "hard_issues": len(hard_issues),
        "narrative_issues": len(repair_issues) - len(hard_issues),
    }]
    if repair_issues:
        try:
            edited = await _run_node(
                db,
                run,
                "novel-editor-repair",
                {
                    "context_pack": context_pack,
                    "beat_sheet": beat_sheet,
                    "draft": {"content": content, "summary": summary},
                    "critique": {**draft_review, "issues": repair_issues},
                    "revision_pass": 1,
                    "requirements": {
                        "repair_only_evidenced_issues": True,
                        "preserve_complete_event_chain": True,
                        "do_not_copy_critic_examples_verbatim": True,
                    },
                },
            )
        except Exception as exc:
            editorial_rounds.append({
                "round": 1, "stage": "证据问题定向返修", "score": None, "passed": False,
                "accepted": False, "word_count": None, "status": "failed", "error": str(exc)[:160],
            })
        else:
            content = str(edited["content"])
            summary = str(edited.get("summary") or summary)
            editor_changes = list(edited.get("edits", []))
            final_metrics = calculate_anti_ai_scores(content)
            final_review = await _run_node(
                db, run, "novel-critic-recheck",
                {"context_pack": context_pack, "beat_sheet": beat_sheet, "content": content},
            )
            editorial_rounds.append({
                "round": 1, "stage": "证据问题定向返修", "score": _review_score(final_review),
                "passed": bool(final_review.get("passed")), "accepted": True,
                "word_count": _prose_length(content), "hard_issues": len(_hard_review_issues(final_review)),
            })
    evidence_rejections: list[dict[str, Any]] = []
    extraction_error: str | None = None
    if rewrite:
        previous = await db.scalar(
            select(ChapterRevision)
            .where(
                ChapterRevision.project_id == project.id,
                ChapterRevision.chapter_sequence == chapter.chapter_sequence,
                ChapterRevision.status == "published",
            )
            .order_by(ChapterRevision.revision.desc())
            .limit(1)
        )
        changes = (
            [item for item in previous.changes["items"] if isinstance(item, dict)]
            if previous and isinstance(previous.changes, dict) and isinstance(previous.changes.get("items"), list)
            else []
        )
        merge_issues = []
    else:
        extraction_payload = {
            "context_pack": context_pack, "beat_sheet": beat_sheet, "content": content, "summary": summary,
        }
        try:
            extraction = await _run_node(db, run, "novel-state-extractor", extraction_payload)
            changes, merge_issues = merge_extractions([extraction])
            changes, evidence_rejections = keep_evidenced_changes(changes, content)
        except Exception as exc:
            changes, merge_issues = [], []
            extraction_error = str(exc)[:500]
    quality_scores = {
        "anti_ai": final_metrics,
        "editorial_score": final_review.get("score"),
        "change_conflicts": len(merge_issues),
    }
    revision = await create_candidate_revision(
        db,
        project,
        chapter,
        run,
        content=content,
        summary=summary,
        beat_sheet=beat_sheet,
        changes=changes,
        quality_scores=quality_scores,
    )
    unresolved_cross_chapter_issues = [
        issue
        for issue in _repairable_review_issues(final_review)
        if _cross_chapter_evidence_occurs(issue, content, previous_ending)
    ]
    gates = await evaluate_quality_gates(
        db,
        project,
        chapter.chapter_sequence,
        content,
        beat_sheet,
        guardian,
        changes,
        editorial_review=final_review,
        change_conflicts=len(merge_issues),
        unresolved_cross_chapter_issues=unresolved_cross_chapter_issues,
    )
    generation_log = {
        "run_id": str(run.id),
        "model": get_settings().llm_model,
        "simulation_id": simulation.get("simulation_id"),
        "node_versions": {
            "architect": "v2-consciousness-thread",
            "guardian": "v1",
            "writer": "v3-consciousness-continuity",
            "critic": "v3-narrative-continuity",
            "editor": "v3-evidenced-narrative-repair",
            "humanizer": "disabled-by-default-v2",
            "state_extractor": "v2-narrative-residue",
        },
        "change_merge_issues": [asdict(issue) for issue in merge_issues],
        "analysis_status": "completed",
        "analysis_message": "正文已完成独立审稿、返修、状态提取和发布门检查",
        "draft_review": draft_review,
        "final_review": final_review,
        "editor_changes": editor_changes,
        "editorial_rounds": editorial_rounds,
        "rejected_review_evidence": [
            {"id": issue.get("id"), "category": issue.get("category"), "reason": "正文中找不到逐字证据"}
            for issue in rejected_review_evidence
        ],
        "state_extraction": {
            "changes": len(changes),
            "rejected_without_evidence": evidence_rejections,
            "merge_conflicts": len(merge_issues),
            "error": extraction_error,
        },
    }
    published = await publish_candidate(db, project, chapter, run, revision, changes, gates, generation_log)
    # 非阻塞伏笔 lint：章节完成后扫描 plot_ledger，逾期伏笔标记 expired（失败不阻断发布）
    try:
        from app.engine.quality import lint_plot_ledger

        await lint_plot_ledger(db, project.id, chapter.chapter_sequence)
    except Exception:
        pass
    return published
