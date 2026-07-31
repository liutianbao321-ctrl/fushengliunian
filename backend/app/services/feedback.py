from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FeedbackEvent, StyleExemplar


def manuscript_diff(before: str, after: str, *, max_items: int = 12) -> dict[str, Any]:
    """Build a bounded, reviewable edit trace without storing another full manuscript."""
    matcher = SequenceMatcher(None, before, after, autojunk=False)
    edits: list[dict[str, Any]] = []
    inserted = deleted = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old = before[i1:i2]
        new = after[j1:j2]
        inserted += len(new)
        deleted += len(old)
        if len(edits) < max_items:
            edits.append(
                {
                    "operation": tag,
                    "before": old[:500],
                    "after": new[:500],
                    "before_span": [i1, i2],
                    "after_span": [j1, j2],
                }
            )
    changed = inserted + deleted
    return {
        "before_length": len(before),
        "after_length": len(after),
        "inserted_characters": inserted,
        "deleted_characters": deleted,
        "change_ratio": round(changed / max(len(before), 1), 4),
        "edits": edits,
        "truncated": len(edits) >= max_items,
    }


async def capture_manuscript_feedback(
    db: AsyncSession,
    *,
    project_id,
    chapter_sequence: int,
    before: str,
    after: str,
) -> FeedbackEvent | None:
    if before == after:
        return None
    diff = manuscript_diff(before, after)
    event = FeedbackEvent(
        project_id=project_id,
        chapter_sequence=chapter_sequence,
        event_type="author_draft" if not before.strip() else "manuscript_edit",
        payload=diff,
    )
    db.add(event)

    # Inserted/replaced passages are the strongest positive style evidence we have:
    # they are words the author deliberately chose over the generated draft.
    for item in diff["edits"]:
        candidate = str(item.get("after") or "").strip()
        if not 80 <= len(candidate) <= 500:
            continue
        exists = await db.scalar(
            select(StyleExemplar.id).where(
                StyleExemplar.project_id == project_id,
                StyleExemplar.content == candidate,
            )
        )
        if exists is None:
            db.add(
                StyleExemplar(
                    project_id=project_id,
                    chapter_sequence=chapter_sequence,
                    category="author_revision",
                    content=candidate,
                    source="manuscript_edit",
                )
            )
    return event
