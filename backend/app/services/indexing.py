from __future__ import annotations

import asyncio
import json
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update

from app.config import get_settings
from app.database import SessionLocal
from app.engine.retrieval import embed_text, embedding_configured
from app.models import ChapterChunk, IndexRun, NovelToc
from app.utils.canonical import sha256_text


def utcnow() -> datetime:
    return datetime.now(UTC)


class IndexWorker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        await self._recover_stale()
        self._task = asyncio.create_task(self._run(), name="index-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _recover_stale(self) -> None:
        cutoff = utcnow() - timedelta(seconds=self.settings.index_lease_seconds)
        async with SessionLocal() as db:
            jobs = list(
                (
                    await db.scalars(
                        select(IndexRun).where(
                            IndexRun.status == "running",
                            or_(IndexRun.heartbeat_at < cutoff, IndexRun.heartbeat_at.is_(None)),
                        )
                    )
                ).all()
            )
            for job in jobs:
                job.status = "queued" if job.attempt < self.settings.index_max_attempts else "failed"
                job.claim_token = None
                job.error_message = "索引 Worker 租约过期，任务已恢复"
            await db.commit()

    async def _claim(self) -> tuple[object, str] | None:
        async with SessionLocal() as db:
            job = await db.scalar(
                select(IndexRun)
                .where(IndexRun.status == "queued")
                .order_by(IndexRun.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not job:
                return None
            token = secrets.token_hex(32)
            job.status = "running"
            job.claim_token = token
            job.attempt += 1
            job.started_at = job.started_at or utcnow()
            job.heartbeat_at = utcnow()
            await db.commit()
            return job.id, token

    async def _heartbeat(self, job_id, token: str) -> None:
        interval = max(1.0, self.settings.index_lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            async with SessionLocal() as db:
                result = await db.execute(
                    update(IndexRun)
                    .where(
                        IndexRun.id == job_id,
                        IndexRun.claim_token == token,
                        IndexRun.status == "running",
                    )
                    .values(heartbeat_at=utcnow())
                )
                await db.commit()
                if result.rowcount == 0:
                    return

    async def _run(self) -> None:
        while not self._stop.is_set():
            claimed = await self._claim()
            if claimed is None:
                await asyncio.sleep(self.settings.index_poll_seconds)
                continue
            job_id, token = claimed
            await self._execute(job_id, token)

    async def _execute(self, job_id, token: str) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(job_id, token), name=f"index-heartbeat-{job_id}")
        try:
            async with SessionLocal() as db:
                job = await db.scalar(
                    select(IndexRun).where(
                        IndexRun.id == job_id,
                        IndexRun.claim_token == token,
                        IndexRun.status == "running",
                    )
                )
                if not job:
                    return
                try:
                    if job.index_kind == "hybrid":
                        metrics = await self._build_hybrid(db, job)
                        job.artifact = None
                    elif job.index_kind == "pageindex":
                        artifact, metrics = await self._build_pageindex(db, job)
                        job.artifact = artifact
                        job.artifact_sha256 = sha256_text(artifact.decode("utf-8"))
                    else:
                        raise ValueError(f"未知索引类型: {job.index_kind}")
                    job.metrics = metrics
                    job.built_revision = job.target_revision
                    job.status = "fresh"
                    job.claim_token = None
                    job.completed_at = utcnow()
                    await db.commit()
                except asyncio.CancelledError:
                    await db.rollback()
                    await db.execute(
                        update(IndexRun)
                        .where(IndexRun.id == job_id, IndexRun.claim_token == token)
                        .values(status="queued", claim_token=None, error_message="index_worker_shutdown")
                    )
                    await db.commit()
                    raise
                except Exception as exc:
                    await db.rollback()
                    job = await db.scalar(select(IndexRun).where(IndexRun.id == job_id, IndexRun.claim_token == token))
                    if job:
                        job.status = "queued" if job.attempt < self.settings.index_max_attempts else "failed"
                        job.claim_token = None
                        job.error_message = str(exc)[:4000]
                        if job.status == "failed":
                            job.completed_at = utcnow()
                        await db.commit()
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _build_hybrid(self, db, job: IndexRun) -> dict:
        chunks = list(
            (
                await db.scalars(
                    select(ChapterChunk).where(
                        ChapterChunk.project_id == job.project_id,
                        ChapterChunk.embedding.is_(None),
                    )
                )
            ).all()
        )
        embedded = 0
        embedding_enabled = embedding_configured(self.settings)
        if embedding_enabled:
            for chunk in chunks:
                vector = await embed_text(chunk.content)
                if vector is not None:
                    chunk.embedding = vector
                    chunk.embedding_model = self.settings.embedding_model
                    chunk.embedding_dimensions = len(vector)
                    embedded += 1
        return {"chunks_seen": len(chunks), "embedded": embedded, "vector_enabled": embedding_enabled}

    async def _build_pageindex(self, db, job: IndexRun) -> tuple[bytes, dict]:
        rows = list(
            (
                await db.scalars(
                    select(NovelToc)
                    .where(NovelToc.project_id == job.project_id)
                    .order_by(NovelToc.level.asc(), NovelToc.sequence.asc())
                )
            ).all()
        )
        children: dict[object, list[NovelToc]] = {}
        for row in rows:
            children.setdefault(row.parent_id, []).append(row)

        def node(row: NovelToc) -> dict:
            return {
                "node_id": str(row.id),
                "title": row.title,
                "level": row.level,
                "summary": row.summary or "",
                "start_index": row.chapter_range_start,
                "end_index": row.chapter_range_end,
                "characters": row.characters,
                "key_events": row.key_events,
                "nodes": [node(child) for child in children.get(row.id, [])],
            }

        tree = [node(row) for row in children.get(None, [])]
        artifact = json.dumps(
            {"version": 1, "project_id": str(job.project_id), "nodes": tree},
            ensure_ascii=False,
        ).encode("utf-8")
        return artifact, {"node_count": len(rows), "bytes": len(artifact)}


index_worker = IndexWorker()
