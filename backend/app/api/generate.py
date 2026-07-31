import asyncio
import json
import secrets
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.projects import get_owned_project
from app.config import get_settings
from app.database import get_db
from app.models import BeatCard, Chapter, ProjectEvent
from app.schemas import ExportRead, GenerateStartRead, GenerateStatusRead
from app.services.auth import get_current_user
from app.services.generation import generation_coordinator
from app.services.sse import event_bus
from app.utils.canonical import payload_hash

router = APIRouter(prefix="/projects/{project_id}", tags=["generate"])
settings = get_settings()


@router.post("/generate/start", response_model=GenerateStartRead)
async def start_generation(
    project_id: uuid.UUID,
    chapter_sequence: int | None = Query(default=None, ge=1),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateStartRead:
    project = await get_owned_project(db, project_id, current_user.id)
    from app.services.project_bootstrap import ensure_blank_chapter

    target_sequence = chapter_sequence or project.current_chapter
    if target_sequence > project.total_chapters:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已经到达全书计划的最后一章")
    await ensure_blank_chapter(db, project, target_sequence)
    await db.commit()
    chapter = await db.scalar(
        select(Chapter).where(
            Chapter.project_id == project.id,
            Chapter.chapter_sequence == target_sequence,
        )
    )
    if chapter is None or not chapter.beat_sheet.get("beats"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先为本章生成或填写章纲，确认后再开始自动写",
        )
    scene_contract = await db.scalar(select(BeatCard).where(BeatCard.chapter_id == chapter.id))
    if scene_contract is None or scene_contract.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先确认本章场景契约，明确人物目的、阻力、转折与章末余波",
        )
    if (chapter.generation_log or {}).get("analysis_status") == "manual_review_required":
        chapter.generation_log = {
            **chapter.generation_log,
            "rewrite_requested": True,
            "rewrite_brief": {
                "source_content": chapter.content,
                "instruction": "校验作者人工修改稿；只修复有正文证据的硬冲突，不改变作者表达与情节选择。",
                "focus": ["连续性", "人物知识边界", "因果", "作者宪章"],
                "preserve": ["作者修改", "情节选择", "叙事声音"],
                "reextract_state": True,
            },
        }
        await db.commit()
    request_id = (idempotency_key or f"auto-{secrets.token_hex(16)}")[:100]
    fingerprint = payload_hash({"project_id": str(project.id), "chapter_sequence": target_sequence})
    run = await generation_coordinator.enqueue(
        project.id,
        target_sequence,
        client_request_id=request_id,
        request_hash=fingerprint,
    )
    return GenerateStartRead(
        run_id=run.id,
        status=run.status,
        chapter_sequence=run.chapter_sequence,
        reused=run.client_request_id != request_id,
    )


@router.post("/generate/pause")
async def pause_generation(
    project_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_owned_project(db, project_id, current_user.id)
    paused = await generation_coordinator.pause(project.id)
    return {"ok": paused}


@router.put("/generate/auto-write")
async def set_auto_write(
    project_id: uuid.UUID,
    enabled: bool,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_owned_project(db, project_id, current_user.id)
    project.generation_state = {**(project.generation_state or {}), "auto_write": enabled}
    await db.commit()
    return {"enabled": enabled}


@router.post("/generate/resume")
async def resume_generation(
    project_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_owned_project(db, project_id, current_user.id)
    resumed = await generation_coordinator.resume(project.id)
    return {"ok": resumed}


@router.get("/generate/status", response_model=GenerateStatusRead)
async def get_generation_status(
    project_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateStatusRead:
    project = await get_owned_project(db, project_id, current_user.id)
    state = project.generation_state or {}
    run = await generation_coordinator.latest_run(project.id)
    active = bool(run and run.status in {"queued", "running", "pausing"})
    last_event = state.get("last_event") if isinstance(state.get("last_event"), dict) else None
    error = None
    if run and run.status == "failed":
        error = str((last_event or {}).get("error") or run.error_message or "生成失败，可以重新生成")
    operation = None
    if active and run is not None:
        run_chapter = await db.scalar(
            select(Chapter).where(
                Chapter.project_id == project.id,
                Chapter.chapter_sequence == run.chapter_sequence,
            )
        )
        generation_log = (run_chapter.generation_log or {}) if run_chapter else {}
        rewrite_brief = generation_log.get("rewrite_brief") if generation_log.get("rewrite_requested") else None
        operation = (
            str(rewrite_brief.get("operation") or "rewrite")
            if isinstance(rewrite_brief, dict)
            else "write"
        )
    return GenerateStatusRead(
        status=project.status,
        current_chapter=run.chapter_sequence if active and run is not None else project.current_chapter,
        total_chapters=project.total_chapters,
        active=active,
        last_event=last_event,
        run_id=run.id if run else None,
        run_status=run.status if run else None,
        current_node=run.current_node if run else None,
        attempt=run.attempt if run else 0,
        error=error,
        auto_write=bool(state.get("auto_write")),
        operation=operation,
    )


@router.get("/stream")
async def stream_project(
    project_id: uuid.UUID,
    last_event_id: int = Query(default=0, ge=0),
    last_event_header: str | None = Header(default=None, alias="Last-Event-ID"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    await get_owned_project(db, project_id, current_user.id)
    queue = await event_bus.subscribe(str(project_id))
    try:
        cursor = max(last_event_id, int(last_event_header or 0))
    except ValueError:
        cursor = last_event_id
    backlog = list(
        (
            await db.scalars(
                select(ProjectEvent)
                .where(ProjectEvent.project_id == project_id, ProjectEvent.sequence > cursor)
                .order_by(ProjectEvent.sequence.asc())
                .limit(1000)
            )
        ).all()
    )
    await db.close()

    async def event_generator():
        try:
            current_cursor = cursor
            for item in backlog:
                current_cursor = item.sequence
                yield {
                    "id": str(item.sequence),
                    "event": item.event_type,
                    "data": json.dumps(item.payload, ensure_ascii=False),
                }
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=settings.sse_heartbeat_seconds)
                    event_id = event.get("id")
                    if event_id and int(event_id) <= current_cursor:
                        continue
                    if event_id:
                        current_cursor = int(event_id)
                    yield {
                        **({"id": str(event_id)} if event_id else {}),
                        "event": event["event"],
                        "data": json.dumps(event["data"], ensure_ascii=False),
                    }
                except TimeoutError:
                    yield {"event": "heartbeat", "data": "{}"}
        finally:
            event_bus.unsubscribe(str(project_id), queue)

    return EventSourceResponse(event_generator())


@router.get("/export/txt", response_model=ExportRead)
async def export_txt(
    project_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExportRead:
    from app.models import Chapter

    project = await get_owned_project(db, project_id, current_user.id)
    if (project.generation_state or {}).get("publication_policy") == "disabled_derivative":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(project.generation_state or {}).get("publication_reason") or "衍生项目默认禁止导出发布",
        )
    chapters = list(
        (
            await db.scalars(
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .where(Chapter.content != "")
                .order_by(Chapter.chapter_sequence.asc())
            )
        ).all()
    )
    total_words = sum(item.word_count for item in chapters)
    header = f"《{project.title}》\n\n已导出 {len(chapters)} 章 · {total_words} 字"
    chapter_text = "\n\n\n".join(
        f"第 {item.chapter_sequence} 章  {item.title}\n\n{item.content}"
        for item in chapters
    )
    content = f"{header}\n\n\n{chapter_text}" if chapter_text else header
    return ExportRead(filename=f"{project.title}.txt", content=content)


@router.get("/export/epub", response_model=ExportRead)
async def export_epub(
    project_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExportRead:
    export = await export_txt(project_id, current_user, db)
    return ExportRead(filename=export.filename.replace(".txt", ".epub.html"), content=export.content)
