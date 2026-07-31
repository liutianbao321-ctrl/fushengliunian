from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update

from app.config import get_settings
from app.database import SessionLocal
from app.engine.analyzer import run_full_analysis
from app.models import ImportedWork


def utcnow() -> datetime:
    return datetime.now(UTC)


class ImportAnalysisWorker:
    """Database-backed import analyzer with leases, retries and restart recovery."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        await self._recover_stale()
        self._task = asyncio.create_task(self._run(), name="import-analysis-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _recover_stale(self) -> None:
        cutoff = utcnow() - timedelta(seconds=self.settings.import_lease_seconds)
        async with SessionLocal() as db:
            works = list(
                (
                    await db.scalars(
                        select(ImportedWork).where(
                            ImportedWork.analysis_status == "analyzing",
                            or_(
                                ImportedWork.analysis_heartbeat_at < cutoff,
                                ImportedWork.analysis_heartbeat_at.is_(None),
                            ),
                        )
                    )
                ).all()
            )
            for work in works:
                work.analysis_status = (
                    "pending" if work.analysis_attempt < self.settings.import_max_attempts else "failed"
                )
                work.analysis_claim_token = None
                work.analysis_error = "分析任务租约过期，已恢复" if work.analysis_status == "pending" else "分析任务重试耗尽"
            await db.commit()

    async def _claim(self) -> tuple[object, str] | None:
        async with SessionLocal() as db:
            work = await db.scalar(
                select(ImportedWork)
                .where(ImportedWork.analysis_status == "pending")
                .order_by(ImportedWork.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if work is None:
                return None
            token = secrets.token_hex(32)
            work.analysis_status = "analyzing"
            work.analysis_attempt += 1
            work.analysis_claim_token = token
            work.analysis_heartbeat_at = utcnow()
            work.analysis_error = None
            await db.commit()
            return work.id, token

    async def _heartbeat(self, work_id, token: str) -> None:
        interval = max(1.0, self.settings.import_lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            async with SessionLocal() as db:
                result = await db.execute(
                    update(ImportedWork)
                    .where(
                        ImportedWork.id == work_id,
                        ImportedWork.analysis_claim_token == token,
                        ImportedWork.analysis_status == "analyzing",
                    )
                    .values(analysis_heartbeat_at=utcnow())
                )
                await db.commit()
                if result.rowcount == 0:
                    return

    async def _run(self) -> None:
        while not self._stop.is_set():
            claimed = await self._claim()
            if claimed is None:
                await asyncio.sleep(self.settings.import_poll_seconds)
                continue
            await self._execute(*claimed)

    async def _execute(self, work_id, token: str) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(work_id, token), name=f"import-heartbeat-{work_id}")
        try:
            async with SessionLocal() as db:
                work = await db.scalar(
                    select(ImportedWork).where(
                        ImportedWork.id == work_id,
                        ImportedWork.analysis_claim_token == token,
                    )
                )
                if work is None:
                    return
                try:
                    await run_full_analysis(db, work)
                    work.analysis_claim_token = None
                    work.analysis_heartbeat_at = utcnow()
                    await db.commit()
                except asyncio.CancelledError:
                    await db.rollback()
                    await db.execute(
                        update(ImportedWork)
                        .where(ImportedWork.id == work_id, ImportedWork.analysis_claim_token == token)
                        .values(analysis_status="pending", analysis_claim_token=None, analysis_error="worker_shutdown")
                    )
                    await db.commit()
                    raise
                except Exception as exc:
                    await db.rollback()
                    work = await db.scalar(
                        select(ImportedWork).where(
                            ImportedWork.id == work_id,
                            ImportedWork.analysis_claim_token == token,
                        )
                    )
                    if work:
                        work.analysis_status = (
                            "pending" if work.analysis_attempt < self.settings.import_max_attempts else "failed"
                        )
                        work.analysis_claim_token = None
                        work.analysis_error = str(exc)[:4000]
                        await db.commit()
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)


import_analysis_worker = ImportAnalysisWorker()
