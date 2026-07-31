from __future__ import annotations

import re
from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChapterRevision, CurrentState, StateEvent, StoryWiki, WikiRevision
from app.utils.canonical import sha256_text
from app.utils.slug import slugify

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def extract_wikilinks(content: str) -> list[str]:
    return sorted({slugify(match.group(1)) for match in WIKILINK_RE.finditer(content)})


def render_fact(event: StateEvent, chapter_sequence: int) -> str:
    value = event.new_value or {}
    display = value.get("value") if isinstance(value, dict) else value
    evidence = event.evidence.get("quote", "") if isinstance(event.evidence, dict) else ""
    suffix = f"；证据：{evidence}" if evidence else ""
    return f"- {event.field}：{display}（来源：第{chapter_sequence}章{suffix}）"


def render_current_fact(state: CurrentState) -> str:
    display = state.value.get("value") if isinstance(state.value, dict) else state.value
    return f"- {state.field}：{display}（更新：第{state.last_chapter_sequence}章）"


async def _next_wiki_revision(db: AsyncSession, page_id) -> int:
    current = await db.scalar(select(func.max(WikiRevision.revision)).where(WikiRevision.page_id == page_id))
    return int(current or 0) + 1


async def ingest_revision(
    db: AsyncSession,
    project_id,
    revision: ChapterRevision,
    events: list[StateEvent],
) -> list[StoryWiki]:
    grouped: dict[tuple[str, str], list[StateEvent]] = {}
    for event in events:
        grouped.setdefault((event.entity_type, event.entity_key), []).append(event)

    updated: list[StoryWiki] = []
    for (entity_type, entity_key), entity_events in grouped.items():
        slug = slugify(entity_key)
        page = await db.scalar(select(StoryWiki).where(StoryWiki.project_id == project_id, StoryWiki.slug == slug))
        links = sorted(
            {
                slugify(str(link))
                for event in entity_events
                for link in (event.evidence.get("related_entities", []) if isinstance(event.evidence, dict) else [])
                if str(link).strip()
            }
        )
        current_states = list(
            (
                await db.scalars(
                    select(CurrentState)
                    .where(
                        CurrentState.project_id == project_id,
                        CurrentState.entity_type == entity_type,
                        CurrentState.entity_key == entity_key,
                    )
                    .order_by(CurrentState.field.asc())
                )
            ).all()
        )
        facts = "\n".join(render_current_fact(state) for state in current_states)
        if not facts:
            facts = "\n".join(render_fact(event, revision.chapter_sequence) for event in entity_events)
        compact_content = f"# {entity_key}\n\n## 当前事实\n\n{facts}\n"
        if page is None:
            page = StoryWiki(
                project_id=project_id,
                slug=slug,
                category=entity_type,
                title=entity_key,
                aliases=[entity_key],
                wikilinks=links,
                source_chapters=[revision.chapter_sequence],
                last_updated_chapter=revision.chapter_sequence,
                visibility="active",
                content=compact_content,
            )
            db.add(page)
            await db.flush()
        else:
            page.content = compact_content
            page.wikilinks = sorted(set(page.wikilinks).union(links))
            page.source_chapters = sorted(set(page.source_chapters).union({revision.chapter_sequence}))
            page.last_updated_chapter = revision.chapter_sequence

        page.wikilinks = sorted(set(page.wikilinks).union(extract_wikilinks(page.content)))
        wiki_revision = WikiRevision(
            project_id=project_id,
            page_id=page.id,
            revision=await _next_wiki_revision(db, page.id),
            chapter_revision_id=revision.id,
            chapter_sequence=revision.chapter_sequence,
            content=page.content,
            wikilinks=page.wikilinks,
            sources=[
                {
                    "chapter_sequence": revision.chapter_sequence,
                    "chapter_revision": revision.revision,
                    "chapter_revision_id": str(revision.id),
                    "body_sha256": revision.body_sha256,
                }
            ],
            content_sha256=sha256_text(page.content),
        )
        db.add(wiki_revision)
        updated.append(page)
    return updated


async def refresh_wiki_after_chapter_deletion(
    db: AsyncSession,
    project_id,
    chapter_sequence: int,
) -> int:
    """Refresh only generated wiki pages that cited the removed chapter."""
    pages = list(
        (
            await db.scalars(
                select(StoryWiki).where(
                    StoryWiki.project_id == project_id,
                    StoryWiki.source_chapters.any(chapter_sequence),
                )
            )
        ).all()
    )
    for page in pages:
        states = list(
            (
                await db.scalars(
                    select(CurrentState)
                    .where(
                        CurrentState.project_id == project_id,
                        CurrentState.entity_type == page.category,
                        CurrentState.entity_key == page.title,
                    )
                    .order_by(CurrentState.field.asc())
                )
            ).all()
        )
        page.source_chapters = [item for item in page.source_chapters if item != chapter_sequence]
        if states:
            page.content = f"# {page.title}\n\n## 当前事实\n\n" + "\n".join(render_current_fact(item) for item in states) + "\n"
            page.last_updated_chapter = max(item.last_chapter_sequence for item in states)
            page.visibility = "active"
        else:
            page.visibility = "archived"
            page.last_updated_chapter = max(page.source_chapters, default=0)
        page.wikilinks = extract_wikilinks(page.content)
    return len(pages)


async def structural_lint(db: AsyncSession, project_id, current_chapter: int) -> list[dict[str, Any]]:
    pages = list((await db.scalars(select(StoryWiki).where(StoryWiki.project_id == project_id))).all())
    by_slug = {page.slug: page for page in pages}
    inbound = Counter(link for page in pages for link in page.wikilinks)
    issues: list[dict[str, Any]] = []
    for page in pages:
        if inbound[page.slug] == 0 and page.category not in {"worldview", "canon_rule", "timeline"}:
            issues.append({"type": "orphan", "severity": "info", "page": page.slug})
        for link in page.wikilinks:
            if link not in by_slug:
                issues.append({"type": "broken_link", "severity": "warning", "page": page.slug, "target": link})
        if current_chapter - page.last_updated_chapter > 50 and page.visibility == "active":
            issues.append(
                {
                    "type": "stale",
                    "severity": "warning",
                    "page": page.slug,
                    "last_updated_chapter": page.last_updated_chapter,
                }
            )
    return issues
