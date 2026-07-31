"""蓝图域长任务 durable worker。

蓝图的「大纲生成」「Beat 卡生成」是长任务，复用 durable worker 模式：
入队时写一条 BlueprintJob 记录并返回 job_id；轮询器在后台把 queued 任务取出来执行，
执行结果写回 BlueprintJob.result / status。API 通过 GET /api/jobs/{job_id} 查询进度。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.engine.blueprint import run_blueprint_job
from app.models import BlueprintJob


def utcnow() -> datetime:
    return datetime.now(UTC)


class BlueprintJobRunner:
    def __init__(self) -> None:
        self._poller: asyncio.Task[None] | None = None
        self._active: set[asyncio.Task[None]] = set()
        self._stop = asyncio.Event()

    async def start_worker(self) -> None:
        if self._poller is not None and not self._poller.done():
            return
        self._stop.clear()
        self._poller = asyncio.create_task(self._poll(), name="blueprint-worker")

    async def stop_worker(self) -> None:
        self._stop.set()
        if self._poller is not None:
            self._poller.cancel()
            await asyncio.gather(self._poller, return_exceptions=True)
            self._poller = None
        if self._active:
            done, pending = await asyncio.wait(self._active, timeout=10)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            self._active.difference_update(done | pending)

    def ensure_started(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._poller is None or self._poller.done():
            self._stop.clear()
            self._poller = loop.create_task(self._poll(), name="blueprint-worker")

    async def enqueue(
        self, project_id: uuid.UUID, job_type: str, payload: dict[str, Any]
    ) -> BlueprintJob:
        async with SessionLocal() as db:
            job = BlueprintJob(
                id=uuid.uuid4(),
                project_id=project_id,
                job_type=job_type,
                payload=payload,
                status="queued",
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            created = BlueprintJob(
                id=job.id,
                project_id=job.project_id,
                job_type=job.job_type,
                status=job.status,
                payload=job.payload,
                result=job.result,
                error_message=job.error_message,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
        self.ensure_started()
        return created

    async def _claim_one(self) -> uuid.UUID | None:
        async with SessionLocal() as db:
            job = await db.scalar(
                select(BlueprintJob)
                .where(BlueprintJob.status == "queued")
                .order_by(BlueprintJob.created_at.asc())
                .limit(1)
            )
            if job is None:
                return None
            job.status = "running"
            await db.commit()
            return job.id

    async def _poll(self) -> None:
        settings = get_settings()
        while not self._stop.is_set():
            try:
                claimed = await self._claim_one()
            except Exception:
                await asyncio.sleep(settings.generation_poll_seconds)
                continue
            if claimed is None:
                await asyncio.sleep(settings.generation_poll_seconds)
                continue
            task = asyncio.create_task(self._execute(claimed), name=f"blueprint-{claimed}")
            self._active.add(task)
            task.add_done_callback(self._active.discard)

    async def _execute(self, job_id: uuid.UUID) -> None:
        try:
            async with SessionLocal() as db:
                job = await db.get(BlueprintJob, job_id)
                if job is None:
                    return
                try:
                    result = await run_blueprint_job(db, job)
                    job.status = "succeeded"
                    job.result = result or {}
                except Exception as exc:  # noqa: BLE001
                    job.status = "failed"
                    job.error_message = str(exc)[:4000]
                job.updated_at = utcnow()
                await db.commit()
        except Exception:  # noqa: BLE001 - 会话级失败兜底
            try:
                async with SessionLocal() as db:
                    job = await db.get(BlueprintJob, job_id)
                    if job is not None:
                        job.status = "failed"
                        job.error_message = "worker session error"
                        job.updated_at = utcnow()
                        await db.commit()
            except Exception:
                pass


blueprint_job_runner = BlueprintJobRunner()
