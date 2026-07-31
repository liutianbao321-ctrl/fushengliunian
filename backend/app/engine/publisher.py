from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.changes import persist_state_events, rebuild_current_states
from app.engine.quality import GateEvidence, all_blocking_gates_pass
from app.engine.state_log import decay_current_states, decay_temperatures
from app.engine.summary import append_chapter_summary
from app.engine.wiki import ingest_revision
from app.models import (
    Chapter,
    ChapterChunk,
    ChapterRevision,
    GenerationRun,
    IndexRun,
    NovelToc,
    OutboxEvent,
    PlotLedger,
    Project,
    QualityGateResult,
    ReaderFeedback,
    SummaryChain,
)
from app.services.events import append_project_event, publish_committed_event
from app.utils.canonical import sha256_text


def utcnow() -> datetime:
    return datetime.now(UTC)


async def create_candidate_revision(
    db: AsyncSession,
    project: Project,
    chapter: Chapter,
    run: GenerationRun,
    *,
    content: str,
    summary: str,
    beat_sheet: dict[str, Any],
    changes: list[dict[str, Any]],
    quality_scores: dict[str, Any],
) -> ChapterRevision:
    locked_chapter = await db.scalar(select(Chapter).where(Chapter.id == chapter.id).with_for_update())
    if locked_chapter is None:
        raise RuntimeError("创建 revision 时章节不存在")
    chapter = locked_chapter
    latest = await db.scalar(
        select(ChapterRevision)
        .where(
            ChapterRevision.project_id == project.id,
            ChapterRevision.chapter_sequence == chapter.chapter_sequence,
        )
        .order_by(ChapterRevision.revision.desc())
        .limit(1)
    )
    body_sha = sha256_text(content)
    existing = await db.scalar(
        select(ChapterRevision).where(
            ChapterRevision.project_id == project.id,
            ChapterRevision.chapter_sequence == chapter.chapter_sequence,
            ChapterRevision.body_sha256 == body_sha,
        )
    )
    if existing:
        return existing
    revision = ChapterRevision(
        project_id=project.id,
        chapter_sequence=chapter.chapter_sequence,
        revision=(latest.revision + 1) if latest else 1,
        generation_run_id=run.id,
        supersedes_id=latest.id if latest else None,
        status="candidate",
        title=chapter.title,
        content=content,
        summary=summary,
        beat_sheet=beat_sheet,
        changes={"items": changes},
        quality_scores=quality_scores,
        body_sha256=body_sha,
        word_count=len(content.replace("\n", "").replace(" ", "")),
    )
    db.add(revision)
    await db.flush()
    return revision


async def persist_gate_results(
    db: AsyncSession,
    revision: ChapterRevision,
    gates: list[GateEvidence],
    *,
    model_name: str,
) -> None:
    for gate in gates:
        result = await db.scalar(
            select(QualityGateResult).where(
                QualityGateResult.chapter_revision_id == revision.id,
                QualityGateResult.gate_name == gate.name,
                QualityGateResult.attempt == 1,
            )
        )
        if result is None:
            result = QualityGateResult(
                chapter_revision_id=revision.id,
                gate_name=gate.name,
                attempt=1,
            )
            db.add(result)
        result.passed = gate.passed
        result.blocking = gate.blocking
        result.score = gate.score
        result.evidence = gate.evidence
        result.model_name = model_name
        result.prompt_version = "quality-gates.v3"


async def stage_generated_draft(
    db: AsyncSession,
    project: Project,
    chapter: Chapter,
    run: GenerationRun,
    *,
    content: str,
    summary: str,
    beat_sheet: dict[str, Any],
    generation_log: dict[str, Any],
) -> None:
    """Expose a usable draft while the non-destructive quality pass continues."""
    locked_chapter = await db.scalar(select(Chapter).where(Chapter.id == chapter.id).with_for_update())
    if locked_chapter is None:
        raise RuntimeError("保存初稿时章节不存在")
    locked_chapter.content = content
    locked_chapter.summary = summary
    locked_chapter.word_count = len(content.replace("\n", "").replace(" ", ""))
    locked_chapter.beat_sheet = beat_sheet
    locked_chapter.status = "draft"
    existing_log = locked_chapter.generation_log or {}
    rewrite_metadata = {
        key: existing_log[key]
        for key in ("rewrite_requested", "rewrite_brief")
        if key in existing_log
    }
    locked_chapter.generation_log = {**generation_log, **rewrite_metadata}
    event = await append_project_event(
        db,
        project.id,
        "generation_draft_ready",
        {
            "run_id": str(run.id),
            "chapter_sequence": chapter.chapter_sequence,
            "analysis_status": "running",
        },
        run.id,
    )
    await db.commit()
    await publish_committed_event(event)


def _chunk_content(content: str, target_chars: int = 900) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in [part.strip() for part in content.split("\n\n") if part.strip()]:
        if current and size + len(paragraph) > target_chars:
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


async def prune_superseded_revision_payloads(
    db: AsyncSession,
    project_id,
    chapter_sequence: int | None = None,
    *,
    keep_revision_id=None,
) -> int:
    """Drop large prose payloads from non-canonical revisions; keep ids, hashes and order."""
    filters = [ChapterRevision.project_id == project_id, ChapterRevision.status.in_(["superseded", "deleted"])]
    if chapter_sequence is not None:
        filters.append(ChapterRevision.chapter_sequence == chapter_sequence)
    if keep_revision_id is not None:
        filters.append(ChapterRevision.id != keep_revision_id)
    rows = list((await db.scalars(select(ChapterRevision).where(*filters))).all())
    pruned = 0
    for row in rows:
        if row.content or row.beat_sheet or row.changes:
            row.content = ""
            row.summary = row.summary[:300] if row.summary else "[旧版本正文已清理，仅保留版本号、字数与哈希]"
            row.beat_sheet = {}
            row.changes = {
                "pruned": True,
                "body_sha256": row.body_sha256,
                "reason": "superseded_revision_payload_not_used_for_future_writing",
            }
            pruned += 1
    return pruned


async def refresh_current_chapter_summary(
    db: AsyncSession,
    project_id,
    chapter_sequence: int,
    title: str,
    summary: str,
    volume_sequence: int | None,
) -> None:
    await db.execute(
        delete(SummaryChain).where(
            SummaryChain.project_id == project_id,
            SummaryChain.chapter_sequence >= chapter_sequence,
        )
    )
    chapters = list(
        (
            await db.scalars(
                select(Chapter)
                .where(
                    Chapter.project_id == project_id,
                    Chapter.chapter_sequence >= chapter_sequence,
                    Chapter.summary != "",
                )
                .order_by(Chapter.chapter_sequence.asc())
            )
        ).all()
    )
    seen = {item.chapter_sequence for item in chapters}
    for item in chapters:
        await append_chapter_summary(
            db,
            project_id,
            item.chapter_sequence,
            item.title,
            item.summary,
            item.volume_sequence,
        )
    if chapter_sequence not in seen:
        await append_chapter_summary(db, project_id, chapter_sequence, title, summary, volume_sequence)


async def publish_candidate(
    db: AsyncSession,
    project: Project,
    chapter: Chapter,
    run: GenerationRun,
    revision: ChapterRevision,
    changes: list[dict[str, Any]],
    gates: list[GateEvidence],
    generation_log: dict[str, Any],
) -> bool:
    await persist_gate_results(db, revision, gates, model_name=generation_log.get("model", "unknown"))
    locked_chapter = await db.scalar(select(Chapter).where(Chapter.id == chapter.id).with_for_update())
    if locked_chapter is None:
        raise RuntimeError("发布时章节不存在")
    if not gates or not all_blocking_gates_pass(gates):
        revision.status = "review_required"
        locked_chapter.title = revision.title
        locked_chapter.content = revision.content
        locked_chapter.summary = revision.summary
        locked_chapter.word_count = revision.word_count
        locked_chapter.beat_sheet = revision.beat_sheet
        locked_chapter.quality_scores = {
            gate.name: {"passed": gate.passed, "score": gate.score, "blocking": gate.blocking} for gate in gates
        }
        locked_chapter.generation_log = {
            **generation_log,
            "analysis_status": "review_required",
            "analysis_message": "正文已保留，但阻断质量门未通过，未写入 Canon。你可以在编辑器中修改后手动确认发布。",
        }
        locked_chapter.status = "draft"
        project.generation_state = {
            "active": False,
            "auto_write": False,
            "run_id": str(run.id),
            "last_event": {
                "type": "generation_review_required",
                "chapter_sequence": chapter.chapter_sequence,
                "failed_gates": [gate.name for gate in gates if gate.blocking and not gate.passed],
            },
        }
        run.status = "review_required"
        run.claim_token = None
        run.result_revision_id = revision.id
        run.completed_at = utcnow()
        run.current_node = "quality_gate"
        event = await append_project_event(
            db,
            project.id,
            "generation_review_required",
            {
                "run_id": str(run.id),
                "chapter_sequence": chapter.chapter_sequence,
                "chapter_revision_id": str(revision.id),
                "failed_gates": [gate.name for gate in gates if gate.blocking and not gate.passed],
                "quality_gates": [asdict(gate) for gate in gates],
            },
            run.id,
        )
        await db.commit()
        await publish_committed_event(event)
        return False
    published = await db.scalar(
        select(ChapterRevision).where(
            ChapterRevision.project_id == project.id,
            ChapterRevision.chapter_sequence == chapter.chapter_sequence,
            ChapterRevision.status == "published",
        )
    )
    if published and published.id != revision.id:
        published.status = "superseded"
    revision.status = "published"
    revision.published_at = utcnow()

    events = await persist_state_events(db, revision, changes)
    await rebuild_current_states(db, project.id)
    await ingest_revision(db, project.id, revision, events)

    locked_chapter.title = revision.title
    locked_chapter.content = revision.content
    locked_chapter.summary = revision.summary
    locked_chapter.word_count = revision.word_count
    locked_chapter.beat_sheet = revision.beat_sheet
    locked_chapter.quality_scores = {
        gate.name: {"passed": gate.passed, "score": gate.score, "blocking": gate.blocking} for gate in gates
    }
    locked_chapter.generation_log = generation_log
    locked_chapter.status = "completed"
    await db.execute(
        delete(ReaderFeedback).where(
            ReaderFeedback.project_id == project.id,
            ReaderFeedback.chapter_sequence == chapter.chapter_sequence,
        )
    )

    await db.execute(
        delete(ChapterChunk).where(
            ChapterChunk.project_id == project.id,
            ChapterChunk.chapter_sequence == chapter.chapter_sequence,
        )
    )
    entities = sorted({change["entity_key"] for change in changes if change.get("entity_key")})
    for index, content in enumerate(_chunk_content(revision.content)):
        db.add(
            ChapterChunk(
                project_id=project.id,
                chapter_sequence=chapter.chapter_sequence,
                chunk_index=index,
                content=content,
                entities=entities,
                arc_id=f"volume-{chapter.volume_sequence}",
                is_milestone=any(change.get("dimension") in {"conflict", "foreshadowing"} for change in changes),
            )
        )

    toc = await db.scalar(
        select(NovelToc).where(
            NovelToc.project_id == project.id,
            NovelToc.level == "chapter",
            NovelToc.sequence == chapter.chapter_sequence,
        )
    )
    if toc:
        toc.summary = revision.summary[:300]
        toc.characters = entities
        toc.key_events = [str(change.get("new_value", {}).get("value", ""))[:120] for change in changes[:8]]

    for change in changes:
        if change.get("dimension") != "foreshadowing":
            continue
        operation = change.get("operation")
        entity_key = change.get("entity_key", "")
        item = await db.scalar(
            select(PlotLedger).where(
                PlotLedger.project_id == project.id,
                PlotLedger.description == entity_key,
            )
        )
        if operation == "create":
            if not item:
                db.add(
                    PlotLedger(
                        project_id=project.id,
                        type=change.get("evidence", {}).get("type", "dialog"),
                        description=entity_key,
                        planted_chapter=chapter.chapter_sequence,
                        due_chapter=change.get("evidence", {}).get("target_chapter"),
                        mentioned_chapters=[chapter.chapter_sequence],
                        is_yy=change.get("evidence", {}).get("is_yy", False),
                    )
                )
        elif item and operation == "advance":
            item.mentioned_chapters = list(set(item.mentioned_chapters + [chapter.chapter_sequence]))
            item.due_chapter = change.get("evidence", {}).get("target_chapter", item.due_chapter)
            if item.status == "reminded":
                pass
            elif item.due_chapter and item.due_chapter - chapter.chapter_sequence <= 5:
                item.status = "reminded"
        elif item and operation in {"resolve", "abandon"}:
            item.status = "closed" if operation == "resolve" else "expired"
            item.resolved_chapter = chapter.chapter_sequence

    target_revision = chapter.chapter_sequence * 1_000_000 + revision.revision
    for kind in ("hybrid", "pageindex"):
        existing_index = await db.scalar(
            select(IndexRun).where(
                IndexRun.project_id == project.id,
                IndexRun.index_kind == kind,
                IndexRun.target_revision == target_revision,
            )
        )
        if existing_index is None:
            db.add(IndexRun(project_id=project.id, index_kind=kind, target_revision=target_revision, status="queued"))

    await prune_superseded_revision_payloads(
        db,
        project.id,
        chapter.chapter_sequence,
        keep_revision_id=revision.id,
    )

    project.current_chapter = min(chapter.chapter_sequence + 1, project.total_chapters)
    if project.current_chapter > chapter.chapter_sequence:
        from app.services.project_bootstrap import ensure_blank_chapter

        await ensure_blank_chapter(db, project, project.current_chapter)
    project.status = "paused"
    project.generation_state = {
        "active": False,
        "auto_write": bool((project.generation_state or {}).get("auto_write")),
        "run_id": str(run.id),
        "last_event": {"type": "generation_complete", "chapter_sequence": chapter.chapter_sequence},
    }
    run.status = "completed"
    run.claim_token = None
    run.result_revision_id = revision.id
    run.completed_at = utcnow()
    run.current_node = "publish"

    event_payload = {
        "run_id": str(run.id),
        "chapter_sequence": chapter.chapter_sequence,
        "chapter_revision_id": str(revision.id),
        "body_sha256": revision.body_sha256,
        "word_count": revision.word_count,
        "quality_gates": [asdict(gate) for gate in gates],
    }
    event = await append_project_event(db, project.id, "generation_complete", event_payload, run.id)
    db.add(
        OutboxEvent(
            event_key=f"chapter-published:{revision.id}",
            aggregate_type="chapter_revision",
            aggregate_id=revision.id,
            event_type="chapter.published",
            payload=event_payload,
        )
    )
    await db.commit()
    await publish_committed_event(event)

    await refresh_current_chapter_summary(
        db,
        project.id,
        chapter.chapter_sequence,
        revision.title,
        revision.summary,
        chapter.volume_sequence,
    )
    await decay_temperatures(db, project.id, chapter.chapter_sequence)
    await decay_current_states(db, project.id, chapter.chapter_sequence)
    await db.commit()

    return True
