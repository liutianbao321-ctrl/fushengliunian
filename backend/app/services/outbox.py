from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import OutboxEvent


def utcnow() -> datetime:
    return datetime.now(UTC)


class OutboxDispatcher:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="outbox-dispatcher")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _claim(self):
        async with SessionLocal() as db:
            event = await db.scalar(
                select(OutboxEvent)
                .where(
                    OutboxEvent.published_at.is_(None),
                    OutboxEvent.available_at <= utcnow(),
                    OutboxEvent.attempts < self.settings.outbox_max_attempts,
                )
                .order_by(OutboxEvent.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not event:
                return None
            event.attempts += 1
            event.available_at = utcnow() + timedelta(seconds=min(300, 2**event.attempts))
            await db.commit()
            return event.id

    async def _deliver(self, event: OutboxEvent) -> None:
        if not self.settings.outbox_webhook_url:
            return
        body = json.dumps(
            {
                "id": str(event.id),
                "event_key": event.event_key,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": str(event.aggregate_id),
                "event_type": event.event_type,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        headers = {"Content-Type": "application/json", "Idempotency-Key": event.event_key}
        if self.settings.outbox_webhook_secret:
            digest = hmac.new(self.settings.outbox_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-Fusheng-Signature"] = f"sha256={digest}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.settings.outbox_webhook_url, content=body, headers=headers)
            response.raise_for_status()

    async def _run(self) -> None:
        while not self._stop.is_set():
            event_id = await self._claim()
            if event_id is None:
                await asyncio.sleep(self.settings.outbox_poll_seconds)
                continue
            async with SessionLocal() as db:
                event = await db.get(OutboxEvent, event_id)
                if not event or event.published_at is not None:
                    continue
                try:
                    await self._deliver(event)
                    event.published_at = utcnow()
                    event.last_error = None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    event.last_error = str(exc)[:4000]
                await db.commit()


outbox_dispatcher = OutboxDispatcher()
