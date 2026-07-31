from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chapter, SummaryChain

ROLLING_WINDOW = 10
CHAPTER_SUMMARY_MAX = 300
ROLLING_SUMMARY_MAX = 1600
CURRENT_VOLUME_SUMMARY_MAX = 2600
LONG_RANGE_SUMMARY_MAX = 5200


async def append_chapter_summary(
    db: AsyncSession,
    project_id,
    chapter_sequence: int,
    chapter_title: str,
    chapter_summary: str,
    volume_sequence: int | None = None,
) -> SummaryChain:
    """Maintain recent and long-range deterministic summaries without another LLM call."""
    title = chapter_title.strip() or f"第{chapter_sequence}章"
    truncated = f"[第{chapter_sequence}章 {title}] {chapter_summary.strip()}"[:CHAPTER_SUMMARY_MAX]
    entry = await db.scalar(
        select(SummaryChain).where(
            SummaryChain.project_id == project_id,
            SummaryChain.chapter_sequence == chapter_sequence,
        )
    )
    if entry is None:
        entry = SummaryChain(
            project_id=project_id,
            chapter_sequence=chapter_sequence,
            chapter_summary=truncated,
            rolling_summary=truncated,
        )
        db.add(entry)
    else:
        entry.chapter_summary = truncated
    await db.flush()

    recent = list(
        reversed(
            list(
                (
                    await db.scalars(
                        select(SummaryChain)
                        .where(
                            SummaryChain.project_id == project_id,
                            SummaryChain.chapter_sequence <= chapter_sequence,
                        )
                        .order_by(SummaryChain.chapter_sequence.desc())
                        .limit(ROLLING_WINDOW)
                    )
                ).all()
            )
        )
    )
    entry.rolling_summary = _join_recent([item.chapter_summary for item in recent], ROLLING_SUMMARY_MAX)

    rows = list(
        (
            await db.execute(
                select(SummaryChain, Chapter.volume_sequence)
                .join(
                    Chapter,
                    (Chapter.project_id == SummaryChain.project_id)
                    & (Chapter.chapter_sequence == SummaryChain.chapter_sequence),
                )
                .where(
                    SummaryChain.project_id == project_id,
                    SummaryChain.chapter_sequence <= chapter_sequence,
                )
                .order_by(SummaryChain.chapter_sequence.asc())
            )
        ).all()
    )
    current_volume = volume_sequence or (rows[-1][1] if rows else 1)
    grouped: dict[int, list[SummaryChain]] = {}
    for summary, volume in rows:
        grouped.setdefault(int(volume or 1), []).append(summary)
    prior_milestones = [
        f"[第{volume}卷里程碑] " + " / ".join(item.chapter_summary for item in _milestones(items))
        for volume, items in sorted(grouped.items())
        if volume < current_volume
    ]
    current_items = grouped.get(current_volume, [])
    current_progress = _join_recent(
        [item.chapter_summary for item in current_items], CURRENT_VOLUME_SUMMARY_MAX
    )
    sections = []
    if prior_milestones:
        sections.append("[跨卷长期脉络]\n" + _join_milestones(prior_milestones, LONG_RANGE_SUMMARY_MAX // 2))
    if current_progress:
        sections.append(f"[第{current_volume}卷当前进展]\n{current_progress}")
    entry.volume_summary = _trim_preserving_ends("\n".join(sections), LONG_RANGE_SUMMARY_MAX)
    await db.flush()
    return entry


async def get_latest_summary(db: AsyncSession, project_id) -> SummaryChain | None:
    """获取最新一条摘要链条目，用于构建 LLM 上下文。"""
    return await db.scalar(
        select(SummaryChain)
        .where(SummaryChain.project_id == project_id)
        .order_by(SummaryChain.chapter_sequence.desc())
        .limit(1)
    )


async def get_recent_summaries(db: AsyncSession, project_id, limit: int = 5) -> list[SummaryChain]:
    """获取最近 N 条摘要链条目。"""
    return (
        await db.scalars(
            select(SummaryChain)
            .where(SummaryChain.project_id == project_id)
            .order_by(SummaryChain.chapter_sequence.desc())
            .limit(limit)
        )
    ).all()


def _join_recent(summaries: list[str], max_chars: int) -> str:
    result: list[str] = []
    length = 0
    for summary in reversed(summaries):
        addition = len(summary) + (1 if result else 0)
        if length + addition > max_chars:
            break
        result.append(summary)
        length += addition
    return "\n".join(reversed(result))


def _milestones(items: list[SummaryChain]) -> list[SummaryChain]:
    if len(items) <= 5:
        return items
    indexes = sorted({0, len(items) // 4, len(items) // 2, (len(items) * 3) // 4, len(items) - 1})
    return [items[index] for index in indexes]


def _join_milestones(summaries: list[str], max_chars: int) -> str:
    if not summaries:
        return ""
    if len("\n".join(summaries)) <= max_chars:
        return "\n".join(summaries)
    keep = [summaries[0]]
    for summary in reversed(summaries[1:]):
        if len("\n".join([*keep, summary])) > max_chars:
            break
        keep.insert(1, summary)
    return "\n".join(keep)


def _trim_preserving_ends(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    head = max_chars // 3
    marker = "\n...[长期摘要按预算省略中段，细节可由检索召回]...\n"
    return value[:head] + marker + value[-(max_chars - head - len(marker)):]
