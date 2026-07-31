from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import SessionLocal
from app.engine.pipeline import GenerationPaused, run_chapter_pipeline
from app.models import Chapter, ChapterRevision, GenerationRun, Project
from app.services.events import append_project_event, publish_committed_event
from app.utils.canonical import sha256_text


def utcnow() -> datetime:
    return datetime.now(UTC)


class GenerationConflictError(ValueError):
    pass


class GenerationCoordinator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._poller: asyncio.Task[None] | None = None
        self._active: set[asyncio.Task[None]] = set()
        self._stop = asyncio.Event()
        self._semaphore = asyncio.Semaphore(self.settings.max_parallel_generations)

    async def start_worker(self) -> None:
        if self._poller and not self._poller.done():
            return
        self._stop.clear()
        await self._recover_stale_runs()
        self._poller = asyncio.create_task(self._poll(), name="generation-worker")

    async def stop_worker(self) -> None:
        self._stop.set()
        if self._poller:
            self._poller.cancel()
            await asyncio.gather(self._poller, return_exceptions=True)
            self._poller = None
        if self._active:
            done, pending = await asyncio.wait(self._active, timeout=10)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            self._active.difference_update(done | pending)

    async def enqueue(
        self,
        project_id: uuid.UUID,
        chapter_sequence: int,
        *,
        client_request_id: str,
        request_hash: str,
    ) -> GenerationRun:
        async with SessionLocal() as db:
            existing = await db.scalar(
                select(GenerationRun).where(
                    GenerationRun.project_id == project_id,
                    GenerationRun.client_request_id == client_request_id,
                )
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise GenerationConflictError("同一请求 ID 被用于不同生成参数")
                return existing
            active = await db.scalar(
                select(GenerationRun).where(
                    GenerationRun.project_id == project_id,
                    GenerationRun.status.in_(["queued", "running", "pausing"]),
                )
            )
            if active:
                return active
            run_id = uuid.uuid4()
            run = GenerationRun(
                id=run_id,
                project_id=project_id,
                chapter_sequence=chapter_sequence,
                client_request_id=client_request_id,
                request_hash=request_hash,
                semantic_key="project-generation",
                status="queued",
            )
            db.add(run)
            project = await db.get(Project, project_id)
            if project:
                project.status = "writing"
                project.generation_state = {
                    "active": True,
                    "auto_write": bool((project.generation_state or {}).get("auto_write")),
                    "run_id": str(run.id),
                    "last_event": {"type": "generation_queued"},
                }
            try:
                event = await append_project_event(
                    db,
                    project_id,
                    "generation_queued",
                    {"run_id": str(run.id), "chapter_sequence": chapter_sequence},
                    run.id,
                )
                await db.commit()
            except IntegrityError:
                await db.rollback()
                active = await db.scalar(
                    select(GenerationRun).where(
                        GenerationRun.project_id == project_id,
                        GenerationRun.status.in_(["queued", "running", "pausing"]),
                    )
                )
                if active:
                    return active
                raise
            await publish_committed_event(event)
            return run

    async def pause(self, project_id: uuid.UUID) -> bool:
        async with SessionLocal() as db:
            run = await db.scalar(
                select(GenerationRun).where(
                    GenerationRun.project_id == project_id,
                    GenerationRun.status.in_(["queued", "running"]),
                )
            )
            if not run:
                project = await db.get(Project, project_id)
                if project and (project.generation_state or {}).get("active"):
                    project.generation_state = {
                        **project.generation_state,
                        "active": False,
                        "last_event": {"type": "generation_idle"},
                    }
                    await db.commit()
                return False
            run.status = "paused" if run.status == "queued" else "pausing"
            if run.status == "paused":
                run.claim_token = None
            project = await db.get(Project, project_id)
            if project:
                project.generation_state = {
                    "active": run.status == "pausing",
                    "auto_write": bool((project.generation_state or {}).get("auto_write")),
                    "run_id": str(run.id),
                    "last_event": {"type": "generation_pausing"},
                }
            await db.commit()
            return True

    async def resume(self, project_id: uuid.UUID) -> bool:
        async with SessionLocal() as db:
            run = await db.scalar(
                select(GenerationRun)
                .where(
                    GenerationRun.project_id == project_id,
                    GenerationRun.status == "paused",
                )
                .order_by(GenerationRun.created_at.desc())
                .with_for_update()
                .limit(1)
            )
            if not run:
                return False
            run.status = "queued"
            run.claim_token = None
            run.error_code = None
            run.error_message = None
            project = await db.get(Project, project_id)
            if project:
                project.status = "writing"
                project.generation_state = {
                    "active": True,
                    "run_id": str(run.id),
                    "last_event": {"type": "generation_resumed"},
                }
            event = await append_project_event(
                db,
                project_id,
                "generation_resumed",
                {"run_id": str(run.id), "chapter_sequence": run.chapter_sequence},
                run.id,
            )
            await db.commit()
            await publish_committed_event(event)
            return True

    async def latest_run(self, project_id: uuid.UUID) -> GenerationRun | None:
        async with SessionLocal() as db:
            return await db.scalar(
                select(GenerationRun)
                .where(GenerationRun.project_id == project_id)
                .order_by(GenerationRun.created_at.desc())
                .limit(1)
            )

    async def _recover_stale_runs(self) -> None:
        async with SessionLocal() as db:
            stale = list(
                (
                    await db.scalars(
                        select(GenerationRun).where(
                            GenerationRun.status.in_(["running", "pausing"]),
                        )
                    )
                ).all()
            )
            for run in stale:
                run.status = "queued" if run.attempt < self.settings.generation_max_attempts else "failed"
                run.claim_token = None
                run.error_code = "worker_lease_expired"
                run.error_message = (
                    "服务重启后任务已从最近节点恢复" if run.status == "queued" else "任务在服务重启前已超过重试上限"
                )
                project = await db.get(Project, run.project_id)
                if project:
                    project.status = "writing" if run.status == "queued" else "paused"
                    project.generation_state = {
                        **(project.generation_state or {}),
                        "active": run.status == "queued",
                        "run_id": str(run.id),
                        "last_event": {"type": "generation_recovered" if run.status == "queued" else "generation_error"},
                    }
            await db.commit()

    async def _claim_one(self) -> tuple[uuid.UUID, str] | None:
        async with SessionLocal() as db:
            run = await db.scalar(
                select(GenerationRun)
                .where(GenerationRun.status == "queued")
                .order_by(GenerationRun.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not run:
                return None
            run.status = "running"
            claim_token = secrets.token_hex(32)
            run.claim_token = claim_token
            run.attempt += 1
            run.started_at = run.started_at or utcnow()
            run.heartbeat_at = utcnow()
            await db.commit()
            return run.id, claim_token

    async def _heartbeat(self, run_id: uuid.UUID, claim_token: str) -> None:
        interval = min(30.0, max(1.0, self.settings.generation_lease_seconds / 3))
        while True:
            await asyncio.sleep(interval)
            async with SessionLocal() as db:
                result = await db.execute(
                    update(GenerationRun)
                    .where(
                        GenerationRun.id == run_id,
                        GenerationRun.claim_token == claim_token,
                        GenerationRun.status.in_(["running", "pausing"]),
                    )
                    .values(heartbeat_at=utcnow())
                )
                await db.commit()
                if result.rowcount == 0:
                    return

    async def _poll(self) -> None:
        while not self._stop.is_set():
            await self._semaphore.acquire()
            try:
                claimed = await self._claim_one()
            except Exception:
                self._semaphore.release()
                await asyncio.sleep(self.settings.generation_poll_seconds)
                continue
            if claimed is None:
                self._semaphore.release()
                await asyncio.sleep(self.settings.generation_poll_seconds)
                continue
            run_id, claim_token = claimed
            task = asyncio.create_task(self._execute(run_id, claim_token), name=f"generation-{run_id}")
            self._active.add(task)
            task.add_done_callback(self._active.discard)

    async def _execute(self, run_id: uuid.UUID, claim_token: str) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(run_id, claim_token), name=f"heartbeat-{run_id}")
        try:
            async with SessionLocal() as db:
                run = await db.scalar(
                    select(GenerationRun).where(
                        GenerationRun.id == run_id,
                        GenerationRun.claim_token == claim_token,
                        GenerationRun.status == "running",
                    )
                )
                if run is None:
                    return
                try:
                    completed = await asyncio.wait_for(
                        run_chapter_pipeline(db, run),
                        timeout=float(self.settings.generation_pipeline_timeout_seconds),
                    )
                    if completed:
                        await self._continue_auto_write(run.project_id, run.chapter_sequence)
                except GenerationPaused:
                    run.status = "paused"
                    run.claim_token = None
                    run.heartbeat_at = utcnow()
                    project = await db.get(Project, run.project_id)
                    if project:
                        project.status = "paused"
                        project.generation_state = {
                            "active": False,
                            "auto_write": bool((project.generation_state or {}).get("auto_write")),
                            "run_id": str(run.id),
                            "last_event": {"type": "generation_paused"},
                        }
                    await db.commit()
                except asyncio.CancelledError:
                    await db.rollback()
                    await db.execute(
                        update(GenerationRun)
                        .where(
                            GenerationRun.id == run_id,
                            GenerationRun.claim_token == claim_token,
                            GenerationRun.status.in_(["running", "pausing"]),
                        )
                        .values(status="queued", claim_token=None, error_code="worker_shutdown")
                    )
                    await db.commit()
                    raise
                except Exception as exc:
                    await db.rollback()
                    run = await db.scalar(
                        select(GenerationRun).where(
                            GenerationRun.id == run_id,
                            GenerationRun.claim_token == claim_token,
                        )
                    )
                    if run is None:
                        return
                    upstream_unavailable = _is_upstream_unavailable(exc)
                    retry = run.attempt < self.settings.generation_max_attempts and not upstream_unavailable
                    run.status = "queued" if retry else "failed"
                    run.claim_token = None
                    run.error_code = "pipeline_error"
                    run.error_message = str(exc)[:4000]
                    run.heartbeat_at = utcnow()
                    if not retry:
                        run.completed_at = utcnow()
                    project = await db.get(Project, run.project_id)
                    if project:
                        project.status = "writing" if retry else "paused"
                        project.generation_state = {
                            "active": retry,
                            "auto_write": bool((project.generation_state or {}).get("auto_write")),
                            "run_id": str(run.id),
                            "last_event": {
                                "type": "generation_retry" if retry else "generation_error",
                                "error": str(exc),
                            },
                        }
                    chapter = await db.scalar(
                        select(Chapter).where(
                            Chapter.project_id == run.project_id,
                            Chapter.chapter_sequence == run.chapter_sequence,
                        )
                    )
                    if chapter and chapter.content:
                        published = await db.scalar(
                            select(ChapterRevision).where(
                                ChapterRevision.project_id == run.project_id,
                                ChapterRevision.chapter_sequence == run.chapter_sequence,
                                ChapterRevision.status == "published",
                            )
                        )
                        content_is_published = bool(
                            published and published.body_sha256 == sha256_text(chapter.content)
                        )
                        chapter.generation_log = {
                            **(chapter.generation_log or {}),
                            "analysis_status": "retrying" if retry else "failed",
                            "analysis_message": (
                                "正文处理暂时失败，正在自动重试"
                                if retry
                                else "正文已保留，可以重新执行未完成的处理"
                            ),
                            "rewrite_requested": retry,
                        }
                        chapter.status = "pending" if retry else "completed" if content_is_published else "draft"
                    event = await append_project_event(
                        db,
                        run.project_id,
                        "generation_retry" if retry else "generation_error",
                        {
                            "run_id": str(run.id),
                            "error": _public_generation_error(exc, bool(chapter and chapter.content)),
                            "attempt": run.attempt,
                            "retry": retry,
                        },
                        run.id,
                    )
                    await db.commit()
                    await publish_committed_event(event)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            self._semaphore.release()

    async def _continue_auto_write(self, project_id: uuid.UUID, completed_sequence: int) -> None:
        async with SessionLocal() as db:
            project = await db.get(Project, project_id)
            if not project or not (project.generation_state or {}).get("auto_write"):
                return
            next_sequence = completed_sequence + 1
            if next_sequence > project.total_chapters:
                project.generation_state = {**project.generation_state, "auto_write": False}
                await db.commit()
                return
            from app.engine.context import build_context_pack, summarize_creation_brief
            from app.engine.worldbuilder import get_genre_writing_contract
            from app.models import Outline
            from app.services.ai_assist import generate_chapter_plan
            from app.services.project_bootstrap import ensure_blank_chapter

            chapter = await ensure_blank_chapter(db, project, next_sequence)
            if not chapter.beat_sheet.get("beats"):
                context_pack = await build_context_pack(db, project, next_sequence)
                brief = summarize_creation_brief(context_pack)
                volume_outline = await db.scalar(
                    select(Outline).where(
                        Outline.project_id == project_id,
                        Outline.level == "volume",
                        Outline.sequence == chapter.volume_sequence,
                    )
                )
                plan = await generate_chapter_plan(
                    book_title=project.title,
                    premise=project.one_sentence,
                    chapter_sequence=next_sequence,
                    previous_summary="\n".join(
                        f"第{item['sequence']}章：{item['summary']}" for item in brief["recent_chapters"]
                    ),
                    story_context=str({
                        "scene_entities": brief["scene_entities"],
                        "character_states": brief["character_states"],
                        "due_foreshadowing": brief["due_foreshadowing"],
                    }),
                    volume_context=str({
                        "volume": volume_outline.content if volume_outline else {},
                        "arc": brief["position"].get("arc_plan", {}),
                    }),
                    style_profile={
                        **(project.style_profile or {}),
                        "writing_contract": (project.style_profile or {}).get("writing_contract")
                        or get_genre_writing_contract(project.genre),
                    },
                    target_words=project.target_words,
                )
                chapter.title = (plan.get("title_candidates") or [f"第 {next_sequence} 章"])[0]
                chapter.summary = str(plan.get("goal") or "")
                chapter.beat_sheet = plan
                chapter.status = "planned"
            await db.commit()
        request_id = f"auto-write-{project_id}-{next_sequence}"
        await self.enqueue(
            project_id,
            next_sequence,
            client_request_id=request_id,
            request_hash=f"auto-write:{project_id}:{next_sequence}",
        )


generation_coordinator = GenerationCoordinator()


def _public_generation_error(exc: Exception, content_was_saved: bool) -> str:
    if content_was_saved:
        return "正文已保存，但后续分析暂时未完成，可以稍后重新处理"
    message = str(exc)
    if _is_upstream_unavailable(exc):
        return "Gemini、DeepSeek 与阿里云 Qwen 当前均不可用，本次任务已结束，请稍后重新生成"
    if "HTTP 429" in message:
        return "正文模型当前请求过多（HTTP 429），请稍后重试"
    if "timeout" in message.lower() or "超时" in message:
        return "正文模型响应超时，自动重试仍未成功，请稍后重试"
    return "正文生成未通过内容解析或连续性校验，可以重新生成"


def _is_upstream_unavailable(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(token in message for token in ("http 502", "http 503", "http 504", "temporarily unavailable", "模型服务暂时不可用"))
