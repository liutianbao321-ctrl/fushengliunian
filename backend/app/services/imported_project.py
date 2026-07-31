from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ChapterChunk,
    Foreshadowing,
    ImportedChapter,
    ImportedWork,
    IndexRun,
    NarrativeDna,
    NovelToc,
    PlotLedger,
    Project,
    ProjectSeed,
    StoryWiki,
    StyleExemplar,
    StyleReference,
    WorkCodexEntry,
)


def _chunks(content: str, target: int = 900) -> list[str]:
    paragraphs = [item.strip() for item in content.splitlines() if item.strip()]
    result: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in paragraphs:
        if current and size + len(paragraph) > target:
            result.append("\n\n".join(current))
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph)
    if current:
        result.append("\n\n".join(current))
    return result or ([content.strip()] if content.strip() else [])


async def materialize_imported_assets(
    db: AsyncSession,
    project: Project,
    work: ImportedWork,
    *,
    inherit_facts: bool,
    inherit_narrative: bool,
) -> None:
    """Attach selected Work Codex layers to the normal project writing pipeline."""
    extracted = work.extracted_data or {}
    codex_rows = list(
        (
            await db.scalars(
                select(WorkCodexEntry).where(WorkCodexEntry.imported_work_id == work.id)
            )
        ).all()
    )

    def codex_content(kind: str, fallback: list[dict]) -> list[dict]:
        rows = [row.content for row in codex_rows if row.layer == "fact" and row.kind == kind]
        return rows if rows else fallback

    characters = codex_content("character", extracted.get("characters", [])) if inherit_facts else []
    world_rules = codex_content("world_rule", extracted.get("world_rules", [])) if inherit_facts else []
    for item in [*characters, *world_rules]:
        if not isinstance(item, dict):
            continue
        base_slug = str(item.get("slug") or item.get("title") or "imported").lower().replace(" ", "-")[:180]
        slug = f"imported-{base_slug}"
        exists = await db.scalar(
            select(StoryWiki.id).where(StoryWiki.project_id == project.id, StoryWiki.slug == slug)
        )
        if exists is None:
            db.add(
                StoryWiki(
                    project_id=project.id,
                    slug=slug,
                    category=item.get("category", "character"),
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    source="imported",
                )
            )

    style_entry = next(
        (row for row in codex_rows if row.layer == "style" and row.kind == "style_profile"),
        None,
    )
    source_style = style_entry.content if style_entry else (work.style_profile or {})
    dna = await db.scalar(select(NarrativeDna).where(NarrativeDna.imported_work_id == work.id))
    project.style_profile = {
        **(project.style_profile or {}),
        "source_work": {"id": str(work.id), "title": work.title, "mode": project.creation_mode},
        "source_style_profile": source_style,
        "narrative_dna": {
            "hook_patterns": dna.hook_patterns,
            "pacing_stats": dna.pacing_stats,
            "pov_habits": dna.pov_habits,
            "escalation_curve": dna.escalation_curve,
            "summary": dna.summary,
        } if dna else {},
    }
    db.add(StyleReference(project_id=project.id, source_name=work.title, style_profile=source_style))
    for index, passage in enumerate(source_style.get("sample_passages", [])[:12], start=1):
        if str(passage).strip():
            db.add(
                StyleExemplar(
                    project_id=project.id,
                    chapter_sequence=-index,
                    category="imported_reference",
                    content=str(passage)[:8000],
                    source="imported_work",
                )
            )

    if inherit_facts:
        foreshadowing = codex_content("foreshadowing", extracted.get("foreshadowing", []))
        for item in foreshadowing:
            if not isinstance(item, dict) or not str(item.get("content") or "").strip():
                continue
            original_seq = int(item.get("planted_chapter") or 1)
            planted = original_seq - max(1, work.total_chapters) - 1
            active = item.get("status") not in {"resolved", "closed", "abandoned"}
            legacy = Foreshadowing(
                project_id=project.id,
                content=str(item["content"]),
                planted_chapter=planted,
                target_chapter=None,
                importance=str(item.get("importance") or "B")[:1],
                status="active" if active else "resolved",
            )
            db.add(legacy)
            await db.flush()
            db.add(
                PlotLedger(
                    project_id=project.id,
                    type=str(item.get("type") or "dialog")[:20],
                    description=str(item["content"]),
                    planted_chapter=planted,
                    mentioned_chapters=[planted],
                    status="open" if active else "closed",
                    is_yy=bool(item.get("is_yy", False)),
                    origin_foreshadowing_id=legacy.id,
                )
            )

    if inherit_narrative:
        chapters = list(
            (
                await db.scalars(
                    select(ImportedChapter)
                    .where(ImportedChapter.work_id == work.id)
                    .order_by(ImportedChapter.chapter_sequence.asc())
                )
            ).all()
        )
        prehistory = NovelToc(
            project_id=project.id,
            level="source_work",
            sequence=0,
            title=f"前史：《{work.title}》",
            summary="导入原作前史，仅供续写检索",
            chapter_range_start=-len(chapters),
            chapter_range_end=-1,
        )
        db.add(prehistory)
        await db.flush()
        names = [str(item.get("title")) for item in characters if item.get("title")]
        for chapter in chapters:
            mapped_sequence = chapter.chapter_sequence - len(chapters) - 1
            entities = [name for name in names if name in chapter.content][:20]
            for index, content in enumerate(_chunks(chapter.content)):
                db.add(
                    ChapterChunk(
                        project_id=project.id,
                        imported_chapter_id=chapter.id,
                        source="imported",
                        chapter_sequence=mapped_sequence,
                        chunk_index=index,
                        content=content,
                        entities=entities,
                        arc_id=f"imported:{work.id}",
                    )
                )
            db.add(
                NovelToc(
                    project_id=project.id,
                    parent_id=prehistory.id,
                    level="source_chapter",
                    sequence=chapter.chapter_sequence,
                    title=chapter.title or f"第{chapter.chapter_sequence}章",
                    summary=chapter.summary[:500],
                    characters=entities,
                    chapter_range_start=mapped_sequence,
                    chapter_range_end=mapped_sequence,
                )
            )
        for kind in ("hybrid", "pageindex"):
            db.add(IndexRun(project_id=project.id, index_kind=kind, target_revision=-1, status="queued"))

    seed = await db.scalar(
        select(ProjectSeed)
        .where(ProjectSeed.project_id == project.id)
        .order_by(ProjectSeed.version.desc())
        .limit(1)
    )
    if seed:
        seed.snapshot = {
            **seed.snapshot,
            "source_work": {
                "id": str(work.id),
                "title": work.title,
                "inherit_facts": inherit_facts,
                "inherit_narrative": inherit_narrative,
                "style_profile": source_style,
                "narrative_dna": project.style_profile.get("narrative_dna", {}),
            },
        }
