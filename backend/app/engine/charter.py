from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WritingCharter


async def get_charter(db: AsyncSession, project_id) -> WritingCharter | None:
    return await db.scalar(
        select(WritingCharter).where(WritingCharter.project_id == project_id)
    )


async def save_charter(
    db: AsyncSession,
    project_id,
    *,
    narrative_focus: str = "",
    red_lines: list[str] | None = None,
    mandates: list[str] | None = None,
    target_readers: str = "",
    tone_reference: str = "",
) -> WritingCharter:
    existing = await get_charter(db, project_id)
    if existing:
        existing.narrative_focus = narrative_focus
        existing.red_lines = red_lines or []
        existing.mandates = mandates or []
        existing.target_readers = target_readers
        existing.tone_reference = tone_reference
        existing.updated_at = datetime.now(UTC)
    else:
        existing = WritingCharter(
            project_id=project_id,
            narrative_focus=narrative_focus,
            red_lines=red_lines or [],
            mandates=mandates or [],
            target_readers=target_readers,
            tone_reference=tone_reference,
        )
        db.add(existing)
    await db.flush()
    return existing


def render_charter_prompt(charter: WritingCharter | None) -> str:
    """把宪章渲染成 LLM prompt 片段。"""
    if charter is None:
        return ""
    lines = ["## 创作宪章（作者确立的约束规则）"]
    if charter.narrative_focus:
        lines.append(f"叙事焦点：{charter.narrative_focus}")
    if charter.red_lines:
        lines.append("红线（绝对禁止）：")
        for r in charter.red_lines:
            lines.append(f"  - {r}")
    if charter.mandates:
        lines.append("强制要求：")
        for m in charter.mandates:
            lines.append(f"  - {m}")
    if charter.target_readers:
        lines.append(f"目标读者：{charter.target_readers}")
    if charter.tone_reference:
        lines.append(f"风格参考：{charter.tone_reference}")
    return "\n".join(lines)
