from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.analyzer import split_chapters
from app.models import ImportedChapter, ImportedWork


async def create_import(
    db: AsyncSession,
    user_id: Any,
    title: str,
    raw_content: str,
    author: str | None = None,
    source_platform: str | None = None,
) -> ImportedWork:
    """Create an imported work entry, split chapters, and return immediately.
    A durable worker claims the analysis after this transaction commits."""

    work = ImportedWork(
        user_id=user_id,
        title=title,
        author=author,
        source_platform=source_platform,
        analysis_status="pending",
    )
    db.add(work)
    await db.flush()

    # Split into chapters
    chapter_dicts = split_chapters(raw_content)

    for i, ch in enumerate(chapter_dicts, 1):
        content = ch["content"]
        imported_ch = ImportedChapter(
            work_id=work.id,
            chapter_sequence=i,
            title=ch["title"],
            content=content,
            word_count=len(content),
        )
        db.add(imported_ch)

    work.total_chapters = len(chapter_dicts)
    work.total_words = sum(len(ch["content"]) for ch in chapter_dicts)
    await db.commit()
    await db.refresh(work)

    return work
