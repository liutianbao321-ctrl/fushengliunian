from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProjectEvent
from app.services.sse import event_bus


async def append_project_event(
    db: AsyncSession, project_id, event_type: str, payload: dict, run_id=None
) -> ProjectEvent:
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(project_id)))))
    latest = await db.scalar(select(func.max(ProjectEvent.sequence)).where(ProjectEvent.project_id == project_id))
    event = ProjectEvent(
        project_id=project_id,
        run_id=run_id,
        sequence=int(latest or 0) + 1,
        event_type=event_type,
        payload=payload,
    )
    db.add(event)
    await db.flush()
    return event


async def publish_committed_event(event: ProjectEvent) -> None:
    await event_bus.publish(
        str(event.project_id),
        {"id": event.sequence, "event": event.event_type, "data": event.payload},
    )
