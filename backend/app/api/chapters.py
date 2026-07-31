import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.context import build_context_pack, summarize_creation_brief
from app.engine.publisher import prune_superseded_revision_payloads, refresh_current_chapter_summary, utcnow
from app.engine.worldbuilder import get_genre_writing_contract
from app.models import (
    BeatCard,
    Chapter,
    ChapterChunk,
    ChapterRevision,
    Foreshadowing,
    IndexRun,
    NovelToc,
    Outline,
    OutlineNode,
    PlotLedger,
    Project,
    ReaderFeedback,
    StateEvent,
    User,
    WikiRevision,
)
from app.schemas import (
    ChapterLightOptimizeRequest,
    ChapterPlanGenerateRequest,
    ChapterPlanWindowUpdate,
    ChapterRead,
    ChapterRewriteRequest,
    ChapterUpdate,
    OutlineRead,
    OutlineUpdate,
)
from app.services.auth import get_current_user
from app.services.feedback import capture_manuscript_feedback
from app.utils.canonical import payload_hash, sha256_text

router = APIRouter(prefix="/projects/{project_id}", tags=["chapters"])


async def promote_optimized_revision(
    db: AsyncSession,
    chapter: Chapter,
    revision: ChapterRevision,
    edits: list[dict[str, str]],
) -> None:
    """Make a wording-only optimization the canonical source used everywhere."""
    published_revisions = list(
        (
            await db.scalars(
                select(ChapterRevision).where(
                    ChapterRevision.project_id == chapter.project_id,
                    ChapterRevision.chapter_sequence == chapter.chapter_sequence,
                    ChapterRevision.status == "published",
                    ChapterRevision.id != revision.id,
                )
            )
        ).all()
    )
    canonical_source = max(published_revisions, key=lambda item: item.revision, default=None)
    if canonical_source is None and revision.supersedes_id is not None:
        canonical_source = await db.get(ChapterRevision, revision.supersedes_id)
    if canonical_source is not None:
        source_changes = canonical_source.changes if isinstance(canonical_source.changes, dict) else {}
        revision.changes = {**source_changes, "light_edits": edits}
        state_events = list(
            (
                await db.scalars(
                    select(StateEvent).where(StateEvent.chapter_revision_id == canonical_source.id)
                )
            ).all()
        )
        for event in state_events:
            event.chapter_revision_id = revision.id
            event.chapter_revision = revision.revision
            evidence = dict(event.evidence or {})
            quote = str(evidence.get("quote") or "")
            for edit in edits:
                if edit["find"] in quote:
                    quote = quote.replace(edit["find"], edit["replace"], 1)
            if quote:
                evidence["quote"] = quote
                event.evidence = evidence
        wiki_revisions = list(
            (
                await db.scalars(
                    select(WikiRevision).where(WikiRevision.chapter_revision_id == canonical_source.id)
                )
            ).all()
        )
        for wiki_revision in wiki_revisions:
            wiki_revision.chapter_revision_id = revision.id
            wiki_revision.sources = [
                {
                    **source,
                    "chapter_revision": revision.revision,
                    "chapter_revision_id": str(revision.id),
                    "body_sha256": revision.body_sha256,
                }
                for source in (wiki_revision.sources or [])
            ]
    for published in published_revisions:
        published.status = "superseded"
    if canonical_source is not None and canonical_source.id != revision.id:
        canonical_source.status = "superseded"
    revision.status = "published"
    revision.published_at = utcnow()

    old_chunks = list(
        (
            await db.scalars(
                select(ChapterChunk).where(
                    ChapterChunk.project_id == chapter.project_id,
                    ChapterChunk.chapter_sequence == chapter.chapter_sequence,
                )
            )
        ).all()
    )
    chunk_entities = sorted({entity for chunk in old_chunks for entity in chunk.entities})
    is_milestone = any(chunk.is_milestone for chunk in old_chunks)
    await db.execute(
        delete(ChapterChunk).where(
            ChapterChunk.project_id == chapter.project_id,
            ChapterChunk.chapter_sequence == chapter.chapter_sequence,
        )
    )
    from app.engine.publisher import _chunk_content

    for index, content in enumerate(_chunk_content(revision.content)):
        db.add(
            ChapterChunk(
                project_id=chapter.project_id,
                chapter_sequence=chapter.chapter_sequence,
                chunk_index=index,
                content=content,
                entities=chunk_entities,
                arc_id=f"volume-{chapter.volume_sequence}",
                is_milestone=is_milestone,
            )
        )

    target_revision = chapter.chapter_sequence * 1_000_000 + revision.revision
    for kind in ("hybrid", "pageindex"):
        existing_index = await db.scalar(
            select(IndexRun).where(
                IndexRun.project_id == chapter.project_id,
                IndexRun.index_kind == kind,
                IndexRun.target_revision == target_revision,
            )
        )
        if existing_index is None:
            db.add(
                IndexRun(
                    project_id=chapter.project_id,
                    index_kind=kind,
                    target_revision=target_revision,
                    status="queued",
                )
            )
    await refresh_current_chapter_summary(
        db,
        chapter.project_id,
        chapter.chapter_sequence,
        revision.title,
        revision.summary,
        chapter.volume_sequence,
    )
    await prune_superseded_revision_payloads(
        db,
        chapter.project_id,
        chapter.chapter_sequence,
        keep_revision_id=revision.id,
    )
    await db.execute(
        delete(ReaderFeedback).where(
            ReaderFeedback.project_id == chapter.project_id,
            ReaderFeedback.chapter_sequence == chapter.chapter_sequence,
        )
    )


async def sync_chapter_blueprint(db: AsyncSession, chapter: Chapter) -> None:
    """Keep the compatibility outline, canonical L5 node and Beat Card aligned."""
    volume_node = await db.scalar(
        select(OutlineNode).where(
            OutlineNode.project_id == chapter.project_id,
            OutlineNode.layer == "L4",
            OutlineNode.seq == chapter.volume_sequence,
        )
    )
    node = await db.scalar(
        select(OutlineNode).where(
            OutlineNode.project_id == chapter.project_id,
            OutlineNode.layer == "L5",
            OutlineNode.seq == chapter.chapter_sequence,
        )
    )
    if node is None:
        node = OutlineNode(
            project_id=chapter.project_id,
            parent_id=volume_node.id if volume_node else None,
            layer="L5",
            seq=chapter.chapter_sequence,
        )
        db.add(node)
    node.title = chapter.title
    node.body = str(chapter.beat_sheet.get("goal") or chapter.summary or "")
    node.status = "confirmed" if chapter.beat_sheet else "draft"
    node.meta = chapter.beat_sheet or {}

    plan = chapter.beat_sheet or {}
    beats = [item for item in plan.get("beats", []) if isinstance(item, dict)]
    first = beats[0] if beats else {}
    last = beats[-1] if beats else {}
    protagonist_change = plan.get("protagonist_change") or {}
    opening = plan.get("opening") or {}
    contract = {
        "entry_state": opening.get("situation") or first.get("event") or "",
        "pov": (plan.get("characters") or [""])[0],
        "desire": protagonist_change.get("desire") or plan.get("goal") or "",
        "opposition": plan.get("conflict") or first.get("obstacle") or "",
        "knowledge_boundary": "只使用已发布正文、现场观察与本章章纲允许的信息",
        "turn": last.get("turn") or last.get("event") or "",
        "exit_state": last.get("outcome") or protagonist_change.get("end") or "",
        "emotional_residue": protagonist_change.get("end") or plan.get("ending_image") or "",
        "promise_movement": plan.get("hook") or "",
    }
    card = await db.scalar(select(BeatCard).where(BeatCard.chapter_id == chapter.id))
    if card is None:
        db.add(
            BeatCard(
                chapter_id=chapter.id,
                fields=contract,
                status="draft",
            )
        )
    else:
        card.fields = contract
        card.status = "draft"


async def ensure_project(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> Project:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user_id))
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


@router.get("/outlines", response_model=list[OutlineRead])
async def get_outlines(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OutlineRead]:
    await ensure_project(db, project_id, current_user.id)
    rows = list(
        (
            await db.scalars(
                select(Outline)
                .where(Outline.project_id == project_id)
                .order_by(Outline.level.asc(), Outline.sequence.asc())
            )
        ).all()
    )
    return [OutlineRead.model_validate(row) for row in rows]


@router.put("/outlines/{outline_id}", response_model=OutlineRead)
async def update_outline(
    project_id: uuid.UUID,
    outline_id: uuid.UUID,
    payload: OutlineUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OutlineRead:
    await ensure_project(db, project_id, current_user.id)
    outline = await db.scalar(select(Outline).where(Outline.id == outline_id, Outline.project_id == project_id))
    if not outline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="大纲不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(outline, field, value)
    await db.commit()
    await db.refresh(outline)
    return OutlineRead.model_validate(outline)


@router.get("/chapters", response_model=list[ChapterRead])
async def list_chapters(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChapterRead]:
    await ensure_project(db, project_id, current_user.id)
    chapters = list(
        (
            await db.scalars(
                select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_sequence.asc())
            )
        ).all()
    )
    return [ChapterRead.model_validate(chapter) for chapter in chapters]


@router.get("/chapter-directory")
async def get_chapter_directory(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return a compact TOC without transferring multi-million-word chapter bodies."""
    await ensure_project(db, project_id, current_user.id)
    rows = (
        await db.execute(
            select(
                Chapter.id,
                Chapter.volume_sequence,
                Chapter.chapter_sequence,
                Chapter.title,
                Chapter.summary,
                Chapter.status,
                Chapter.word_count,
                Chapter.beat_sheet,
                (Chapter.content != "").label("has_content"),
                Chapter.updated_at,
            )
            .where(Chapter.project_id == project_id)
            .order_by(Chapter.chapter_sequence.asc())
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "volume_sequence": row.volume_sequence,
            "chapter_sequence": row.chapter_sequence,
            "title": row.title,
            "summary": row.summary,
            "status": row.status,
            "word_count": row.word_count,
            "has_plan": bool((row.beat_sheet or {}).get("beats")),
            "has_content": bool(row.has_content),
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/chapters/plan-window")
async def plan_chapter_window(
    project_id: uuid.UUID,
    start_sequence: int = 1,
    count: int = 3,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await ensure_project(db, project_id, current_user.id)
    if start_sequence < 1 or count < 1 or count > 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="规划范围必须是1至5章（建议每批3章，分批规划更可控）",
        )
    count = min(count, project.total_chapters - start_sequence + 1)
    if count < 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已经到达全书计划的最后一章")
    protected = await db.scalar(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_sequence.between(start_sequence, start_sequence + count - 1),
            Chapter.content != "",
        ).limit(1)
    )
    if protected:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="规划范围内已有正文，请从后面的章节开始规划")

    context_pack = await build_context_pack(db, project, start_sequence)
    brief = summarize_creation_brief(context_pack)
    start_chapter = await db.scalar(
        select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_sequence == start_sequence)
    )
    volume_sequence = start_chapter.volume_sequence if start_chapter else 1
    volume_outline = await db.scalar(
        select(Outline).where(
            Outline.project_id == project_id,
            Outline.level == "volume",
            Outline.sequence == volume_sequence,
        )
    )
    from app.services.ai_assist import generate_chapter_plan_window

    try:
        chapters = await generate_chapter_plan_window(
            book_title=project.title,
            premise=project.one_sentence,
            start_sequence=start_sequence,
            count=count,
            previous_summary="\n".join(
                f"第{item['sequence']}章：{item['summary']}" for item in brief["recent_chapters"]
            ),
            story_context=str({
                "character_states": brief["character_states"],
                "due_foreshadowing": brief["due_foreshadowing"],
                "scene_entities": brief["scene_entities"],
            }),
            volume_context=str(_chapter_planning_context(
                volume_outline.content if volume_outline else {},
                brief["position"].get("arc_plan", {}),
                start_sequence,
            )),
            style_profile=project.style_profile if isinstance(project.style_profile, dict) else {},
            target_words=project.target_words,
        )
        return {"start_sequence": start_sequence, "count": count, "chapters": chapters}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.put("/chapters/plan-window", response_model=list[ChapterRead])
async def save_chapter_plan_window(
    project_id: uuid.UUID,
    payload: ChapterPlanWindowUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChapterRead]:
    project = await ensure_project(db, project_id, current_user.id)
    items = payload.chapters
    sequences = [item.chapter_sequence for item in items]
    if sequences != list(range(sequences[0], sequences[0] + len(sequences))) or sequences[-1] > project.total_chapters:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="章节必须按连续序号提交")
    existing = list(
        (
            await db.scalars(
                select(Chapter)
                .where(Chapter.project_id == project_id, Chapter.chapter_sequence.in_(sequences))
                .with_for_update()
            )
        ).all()
    )
    if any(chapter.content.strip() for chapter in existing):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不能覆盖已有正文的章节")
    by_sequence = {chapter.chapter_sequence: chapter for chapter in existing}
    from app.services.project_bootstrap import ensure_blank_chapter

    saved: list[Chapter] = []
    for item in items:
        chapter = by_sequence.get(item.chapter_sequence)
        if chapter is None:
            chapter = await ensure_blank_chapter(db, project, item.chapter_sequence)
        chapter.title = item.title.strip()
        chapter.summary = str(item.plan.get("goal") or "")
        chapter.beat_sheet = item.plan
        chapter.status = "planned"
        outline = await db.scalar(
            select(Outline).where(
                Outline.project_id == project_id,
                Outline.level == "chapter",
                Outline.sequence == item.chapter_sequence,
            )
        )
        if outline is None:
            volume_outline = await db.scalar(
                select(Outline).where(
                    Outline.project_id == project_id,
                    Outline.level == "volume",
                    Outline.sequence == chapter.volume_sequence,
                )
            )
            outline = Outline(
                project_id=project_id,
                parent_id=volume_outline.id if volume_outline else None,
                level="chapter",
                sequence=item.chapter_sequence,
                title=chapter.title,
                content=chapter.beat_sheet,
                is_sealed=False,
            )
            db.add(outline)
        else:
            outline.title = chapter.title
            outline.content = chapter.beat_sheet
        toc = await db.scalar(
            select(NovelToc).where(
                NovelToc.project_id == project_id,
                NovelToc.level == "chapter",
                NovelToc.sequence == item.chapter_sequence,
            )
        )
        if toc is None:
            volume_toc = await db.scalar(
                select(NovelToc).where(
                    NovelToc.project_id == project_id,
                    NovelToc.level == "volume",
                    NovelToc.sequence == chapter.volume_sequence,
                )
            )
            toc = NovelToc(
                project_id=project_id,
                parent_id=volume_toc.id if volume_toc else None,
                level="chapter",
                sequence=item.chapter_sequence,
                title=chapter.title,
                summary=chapter.summary,
                characters=item.plan.get("characters", []),
                key_events=[beat.get("event", "") for beat in item.plan.get("beats", [])],
                chapter_range_start=item.chapter_sequence,
                chapter_range_end=item.chapter_sequence,
            )
            db.add(toc)
        else:
            toc.title = chapter.title
            toc.summary = chapter.summary
            toc.characters = item.plan.get("characters", [])
            toc.key_events = [beat.get("event", "") for beat in item.plan.get("beats", [])]
        await sync_chapter_blueprint(db, chapter)
        saved.append(chapter)
    await db.commit()
    for chapter in saved:
        await db.refresh(chapter)
    return [ChapterRead.model_validate(chapter) for chapter in saved]


@router.get("/chapters/{chapter_sequence}", response_model=ChapterRead)
async def get_chapter(
    project_id: uuid.UUID,
    chapter_sequence: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChapterRead:
    await ensure_project(db, project_id, current_user.id)
    chapter = await db.scalar(
        select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_sequence == chapter_sequence)
    )
    if not chapter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")
    return ChapterRead.model_validate(chapter)


@router.put("/chapters/{chapter_sequence}", response_model=ChapterRead)
async def update_chapter(
    project_id: uuid.UUID,
    chapter_sequence: int,
    payload: ChapterUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChapterRead:
    await ensure_project(db, project_id, current_user.id)
    chapter = await db.scalar(
        select(Chapter)
        .where(Chapter.project_id == project_id, Chapter.chapter_sequence == chapter_sequence)
        .with_for_update()
    )
    if not chapter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")
    previous_content = chapter.content
    changes = payload.model_dump(exclude_none=True)
    content_was_supplied = "content" in changes
    for field, value in changes.items():
        setattr(chapter, field, value)
    if content_was_supplied and not chapter.content.strip():
        chapter.content = ""
    if not content_was_supplied or not chapter.content.strip():
        if chapter.beat_sheet and chapter.status == "unplanned":
            chapter.status = "planned"
        if "beat_sheet" in changes and chapter.beat_sheet:
            volume_outline = await db.scalar(
                select(Outline).where(
                    Outline.project_id == project_id,
                    Outline.level == "volume",
                    Outline.sequence == chapter.volume_sequence,
                )
            )
            outline = await db.scalar(
                select(Outline).where(
                    Outline.project_id == project_id,
                    Outline.level == "chapter",
                    Outline.sequence == chapter_sequence,
                )
            )
            if outline is None:
                outline = Outline(
                    project_id=project_id,
                    parent_id=volume_outline.id if volume_outline else None,
                    level="chapter",
                    sequence=chapter_sequence,
                    title=chapter.title,
                    content=chapter.beat_sheet,
                    is_sealed=False,
                )
                db.add(outline)
            else:
                outline.title = chapter.title
                outline.content = chapter.beat_sheet

            volume_toc = await db.scalar(
                select(NovelToc).where(
                    NovelToc.project_id == project_id,
                    NovelToc.level == "volume",
                    NovelToc.sequence == chapter.volume_sequence,
                )
            )
            toc = await db.scalar(
                select(NovelToc).where(
                    NovelToc.project_id == project_id,
                    NovelToc.level == "chapter",
                    NovelToc.sequence == chapter_sequence,
                )
            )
            if toc is None:
                db.add(
                    NovelToc(
                        project_id=project_id,
                        parent_id=volume_toc.id if volume_toc else None,
                        level="chapter",
                        sequence=chapter_sequence,
                        title=chapter.title,
                        summary=chapter.summary,
                        characters=chapter.beat_sheet.get("characters", []),
                        key_events=[item.get("event", "") for item in chapter.beat_sheet.get("beats", [])],
                        chapter_range_start=chapter_sequence,
                        chapter_range_end=chapter_sequence,
                    )
                )
            else:
                toc.title = chapter.title
                toc.summary = chapter.summary
            await sync_chapter_blueprint(db, chapter)
        chapter.word_count = len(chapter.content.replace("\n", "").replace(" ", ""))
        await db.commit()
        await db.refresh(chapter)
        return ChapterRead.model_validate(chapter)
    current_revision = await db.scalar(
        select(ChapterRevision)
        .where(ChapterRevision.project_id == project_id, ChapterRevision.chapter_sequence == chapter_sequence)
        .order_by(ChapterRevision.revision.desc())
        .limit(1)
    )
    body_sha = sha256_text(chapter.content)
    existing = await db.scalar(
        select(ChapterRevision).where(
            ChapterRevision.project_id == project_id,
            ChapterRevision.chapter_sequence == chapter_sequence,
            ChapterRevision.body_sha256 == body_sha,
        )
    )
    if existing is None:
        revision = ChapterRevision(
                project_id=project_id,
                chapter_sequence=chapter_sequence,
                revision=(current_revision.revision + 1) if current_revision else 1,
                supersedes_id=current_revision.id if current_revision else None,
                status="review_required",
                title=chapter.title,
                content=chapter.content,
                summary=chapter.summary,
                beat_sheet=chapter.beat_sheet,
                changes={},
                quality_scores={},
                body_sha256=body_sha,
                word_count=len(chapter.content.replace("\n", "").replace(" ", "")),
            )
        db.add(revision)
    await db.execute(
        delete(ReaderFeedback).where(
            ReaderFeedback.project_id == project_id,
            ReaderFeedback.chapter_sequence == chapter_sequence,
        )
    )
    chapter.status = "draft"
    chapter.generation_log = {
        **(chapter.generation_log or {}),
        "analysis_status": "manual_review_required",
        "analysis_message": "人工修改已保存为新版本；重新执行校验发布前，既有 Canon 与检索索引保持不变。",
    }
    chapter.word_count = len(chapter.content)
    await capture_manuscript_feedback(
        db,
        project_id=project_id,
        chapter_sequence=chapter_sequence,
        before=previous_content,
        after=chapter.content,
    )
    await db.commit()
    await db.refresh(chapter)
    return ChapterRead.model_validate(chapter)


@router.post("/chapters/{chapter_sequence}/plan")
async def plan_chapter(
    project_id: uuid.UUID,
    chapter_sequence: int,
    payload: ChapterPlanGenerateRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await ensure_project(db, project_id, current_user.id)
    chapter = await db.scalar(
        select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_sequence == chapter_sequence)
    )
    if not chapter:
        from app.services.project_bootstrap import ensure_blank_chapter

        if chapter_sequence > project.total_chapters:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已经到达全书计划的最后一章")
        chapter = await ensure_blank_chapter(db, project, chapter_sequence)
        await db.commit()
    context_pack = await build_context_pack(db, project, chapter_sequence)
    brief = summarize_creation_brief(context_pack)
    volume_outline = await db.scalar(
        select(Outline).where(
            Outline.project_id == project_id,
            Outline.level == "volume",
            Outline.sequence == chapter.volume_sequence,
        )
    )
    from app.services.ai_assist import generate_chapter_plan

    try:
        return await generate_chapter_plan(
            book_title=project.title,
            premise=project.one_sentence,
            chapter_sequence=chapter_sequence,
            previous_summary="\n".join(
                f"第{item['sequence']}章：{item['summary']}" for item in brief["recent_chapters"]
            ),
            story_context=str({
                "scene_entities": brief["scene_entities"],
                "character_states": brief["character_states"],
                "due_foreshadowing": brief["due_foreshadowing"],
                "why_this_chapter": brief["why_this_chapter"],
            }),
            volume_context=str(_chapter_planning_context(
                volume_outline.content if volume_outline else {},
                brief["position"].get("arc_plan", {}),
                chapter_sequence,
            )),
            style_profile={
                **(project.style_profile if isinstance(project.style_profile, dict) else {}),
                "writing_contract": (
                    project.style_profile.get("writing_contract")
                    if isinstance(project.style_profile, dict) and project.style_profile.get("writing_contract")
                    else get_genre_writing_contract(project.genre)
                ),
            },
            author_instruction=(payload.instruction if payload else ""),
            current_plan=chapter.beat_sheet if chapter.beat_sheet else None,
            target_words=project.target_words,
        ) | {"creation_brief": brief}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def _chapter_planning_context(
    volume_plan: dict[str, Any],
    arc_plan: dict[str, Any],
    chapter_sequence: int,
) -> dict[str, Any]:
    chapter_range = volume_plan.get("chapter_range", []) if isinstance(volume_plan, dict) else []
    volume_progress = None
    if len(chapter_range) == 2 and chapter_range[0] <= chapter_sequence <= chapter_range[1]:
        volume_progress = round(
            (chapter_sequence - chapter_range[0] + 1) / max(chapter_range[1] - chapter_range[0] + 1, 1),
            3,
        )
    return {
        "volume_title": volume_plan.get("title", "") if isinstance(volume_plan, dict) else "",
        "volume_goal": volume_plan.get("goal", "") if isinstance(volume_plan, dict) else "",
        "volume_chapter_range": chapter_range,
        "volume_progress": volume_progress,
        "planning_rule": "本章在工作台滚动规划；建书时的逐章方向只是已失效草案，不构成本章约束。",
        "protected_reveals": volume_plan.get("protected_reveals", []) if isinstance(volume_plan, dict) else [],
        "turning_points": (volume_plan.get("turning_points", []) if isinstance(volume_plan, dict) else [])[:5],
        "ending_hook": volume_plan.get("ending_hook", "") if isinstance(volume_plan, dict) else "",
        "arc_goal": arc_plan.get("goal", "") if isinstance(arc_plan, dict) else "",
        "arc_stage": arc_plan.get("stage", "") if isinstance(arc_plan, dict) else "",
    }


@router.get("/chapters/{chapter_sequence}/creation-brief")
async def get_creation_brief(
    project_id: uuid.UUID,
    chapter_sequence: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """给作者看的本章创作简报：为什么写、人物当前状态、临期伏笔。"""
    project = await ensure_project(db, project_id, current_user.id)
    chapter = await db.scalar(
        select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_sequence == chapter_sequence)
    )
    if not chapter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")
    return summarize_creation_brief(await build_context_pack(db, project, chapter_sequence))


@router.post("/chapters/{chapter_sequence}/confirm", response_model=ChapterRead)
async def confirm_chapter(
    project_id: uuid.UUID,
    chapter_sequence: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChapterRead:
    await ensure_project(db, project_id, current_user.id)
    chapter = await db.scalar(
        select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_sequence == chapter_sequence)
    )
    if not chapter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")
    if chapter.status == "review_required":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="手工修改稿必须重新执行连续性检查与 CHANGES ingest 后才能确认",
        )
    published_revision = await db.scalar(
        select(ChapterRevision).where(
            ChapterRevision.project_id == project_id,
            ChapterRevision.chapter_sequence == chapter_sequence,
            ChapterRevision.status == "published",
        )
    )
    if published_revision is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="章节尚无通过质量门的发布 revision")
    chapter.status = "confirmed"
    await db.commit()
    await db.refresh(chapter)
    return ChapterRead.model_validate(chapter)


@router.post("/chapters/{chapter_sequence}/rewrite", response_model=ChapterRead)
async def rewrite_chapter(
    project_id: uuid.UUID,
    chapter_sequence: int,
    payload: ChapterRewriteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChapterRead:
    await ensure_project(db, project_id, current_user.id)
    chapter = await db.scalar(
        select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_sequence == chapter_sequence)
    )
    if not chapter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")
    if not chapter.content.strip():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="这一章还没有正文，请先生成初稿")
    rewrite_brief = {
        "focus": payload.focus,
        "preserve": payload.preserve,
        "instruction": payload.instruction.strip(),
        "source_content": chapter.content,
        "operation": payload.operation,
    }
    chapter.status = "pending"
    chapter.generation_log = {**chapter.generation_log, "rewrite_requested": True, "rewrite_brief": rewrite_brief}
    await db.commit()
    await db.refresh(chapter)
    from app.services.generation import generation_coordinator

    request_id = payload.request_key or f"rewrite-{uuid.uuid4()}"
    await generation_coordinator.enqueue(
        project_id,
        chapter_sequence,
        client_request_id=request_id,
        request_hash=payload_hash(
            {"project_id": str(project_id), "chapter_sequence": chapter_sequence, "rewrite": rewrite_brief}
        ),
    )
    return ChapterRead.model_validate(chapter)


@router.post("/chapters/{chapter_sequence}/optimize-light")
async def optimize_chapter_light(
    project_id: uuid.UUID,
    chapter_sequence: int,
    payload: ChapterLightOptimizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_project(db, project_id, current_user.id)
    chapter = await db.scalar(
        select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_sequence == chapter_sequence)
    )
    if not chapter or not chapter.content.strip():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="这一章还没有正文")
    source_content = chapter.content

    from app.services.ai_assist import generate_light_chapter_edits

    try:
        edits = await generate_light_chapter_edits(
            source_content,
            payload.instruction,
            focus=payload.focus,
            preserve=payload.preserve,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    if not edits:
        return {"chapter": ChapterRead.model_validate(chapter), "edits": [], "message": "没有发现需要修改的文字"}

    optimized_content = source_content
    for edit in edits:
        optimized_content = optimized_content.replace(edit["find"], edit["replace"], 1)
    if optimized_content == source_content:
        return {"chapter": ChapterRead.model_validate(chapter), "edits": [], "message": "正文没有变化"}

    chapter = await db.scalar(
        select(Chapter)
        .where(Chapter.project_id == project_id, Chapter.chapter_sequence == chapter_sequence)
        .with_for_update()
    )
    if chapter is None or chapter.content != source_content:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="优化期间正文已被修改，本次结果没有覆盖新内容，请重新执行",
        )

    latest = await db.scalar(
        select(ChapterRevision)
        .where(ChapterRevision.project_id == project_id, ChapterRevision.chapter_sequence == chapter_sequence)
        .order_by(ChapterRevision.revision.desc())
        .limit(1)
    )
    source_sha = sha256_text(source_content)
    source_revision = await db.scalar(
        select(ChapterRevision).where(
            ChapterRevision.project_id == project_id,
            ChapterRevision.chapter_sequence == chapter_sequence,
            ChapterRevision.body_sha256 == source_sha,
        )
    )
    next_revision = (latest.revision + 1) if latest else 1
    if source_revision is None:
        source_revision = ChapterRevision(
            project_id=project_id,
            chapter_sequence=chapter_sequence,
            revision=next_revision,
            supersedes_id=latest.id if latest else None,
            status="superseded",
            title=chapter.title,
            content=source_content,
            summary=chapter.summary,
            beat_sheet=chapter.beat_sheet,
            changes={},
            quality_scores=chapter.quality_scores,
            body_sha256=source_sha,
            word_count=len(source_content.replace("\n", "").replace(" ", "")),
        )
        db.add(source_revision)
        await db.flush()
        next_revision += 1

    optimized_sha = sha256_text(optimized_content)
    optimized_revision = await db.scalar(
        select(ChapterRevision).where(
            ChapterRevision.project_id == project_id,
            ChapterRevision.chapter_sequence == chapter_sequence,
            ChapterRevision.body_sha256 == optimized_sha,
        )
    )
    if optimized_revision is None:
        optimized_revision = ChapterRevision(
            project_id=project_id,
            chapter_sequence=chapter_sequence,
            revision=next_revision,
            supersedes_id=source_revision.id,
            status="candidate",
            title=chapter.title,
            content=optimized_content,
            summary=chapter.summary,
            beat_sheet=chapter.beat_sheet,
            changes={"light_edits": edits},
            quality_scores={},
            body_sha256=optimized_sha,
            word_count=len(optimized_content.replace("\n", "").replace(" ", "")),
        )
        db.add(optimized_revision)
        await db.flush()

    chapter.content = optimized_content
    chapter.word_count = len(optimized_content.replace("\n", "").replace(" ", ""))
    chapter.status = "completed"
    chapter.generation_log = {
        **(chapter.generation_log or {}),
        "analysis_status": "completed",
        "analysis_message": f"已完成 {len(edits)} 处局部修改；新正文已成为后续写作与检索的当前版本。",
        "light_edits": edits,
    }
    await promote_optimized_revision(db, chapter, optimized_revision, edits)
    await db.commit()
    await db.refresh(chapter)
    return {
        "chapter": ChapterRead.model_validate(chapter),
        "edits": edits,
        "message": f"已完成 {len(edits)} 处局部修改",
    }


@router.delete("/chapters/{chapter_sequence}/content", response_model=ChapterRead)
async def delete_chapter_content(
    project_id: uuid.UUID,
    chapter_sequence: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChapterRead:
    """Remove prose while retaining the confirmed chapter plan and revision history."""
    project = await ensure_project(db, project_id, current_user.id)
    chapter = await db.scalar(
        select(Chapter)
        .where(Chapter.project_id == project_id, Chapter.chapter_sequence == chapter_sequence)
        .with_for_update()
    )
    if not chapter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")
    if not chapter.content.strip():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="这一章没有可删除的正文")
    later = await db.scalar(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_sequence > chapter_sequence,
            Chapter.content != "",
        ).order_by(Chapter.chapter_sequence.desc()).limit(1)
    )
    if later:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"第{later.chapter_sequence}章已有正文，请从最后一章开始向前删除",
        )

    revisions = list(
        (
            await db.scalars(
                select(ChapterRevision).where(
                    ChapterRevision.project_id == project_id,
                    ChapterRevision.chapter_sequence == chapter_sequence,
                    ChapterRevision.status == "published",
                )
            )
        ).all()
    )
    for revision in revisions:
        revision.status = "deleted"
    await db.execute(
        delete(ChapterChunk).where(
            ChapterChunk.project_id == project_id,
            ChapterChunk.chapter_sequence == chapter_sequence,
        )
    )
    await db.execute(
        delete(ReaderFeedback).where(
            ReaderFeedback.project_id == project_id,
            ReaderFeedback.chapter_sequence == chapter_sequence,
        )
    )
    await db.execute(
        delete(Foreshadowing).where(
            Foreshadowing.project_id == project_id,
            Foreshadowing.planted_chapter == chapter_sequence,
        )
    )
    await db.execute(
        delete(PlotLedger).where(
            PlotLedger.project_id == project_id,
            PlotLedger.planted_chapter == chapter_sequence,
        )
    )
    resolved_items = list(
        (
            await db.scalars(
                select(Foreshadowing).where(
                    Foreshadowing.project_id == project_id,
                    Foreshadowing.resolved_chapter == chapter_sequence,
                )
            )
        ).all()
    )
    for item in resolved_items:
        item.resolved_chapter = None
        item.status = "active"
    resolved_ledger = list(
        (
            await db.scalars(
                select(PlotLedger).where(
                    PlotLedger.project_id == project_id,
                    PlotLedger.resolved_chapter == chapter_sequence,
                )
            )
        ).all()
    )
    for item in resolved_ledger:
        item.resolved_chapter = None
        item.status = "open"

    chapter.content = ""
    chapter.summary = str(chapter.beat_sheet.get("goal") or "") if isinstance(chapter.beat_sheet, dict) else ""
    chapter.word_count = 0
    chapter.quality_scores = {}
    chapter.generation_log = {}
    chapter.status = "planned" if chapter.beat_sheet else "unplanned"
    project.current_chapter = chapter_sequence

    from app.engine.changes import rebuild_current_states
    from app.engine.wiki import refresh_wiki_after_chapter_deletion

    await db.flush()
    await rebuild_current_states(db, project_id)
    await refresh_wiki_after_chapter_deletion(db, project_id, chapter_sequence)
    await db.commit()
    await db.refresh(chapter)
    return ChapterRead.model_validate(chapter)
