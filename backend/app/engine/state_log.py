from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CurrentState, EntityTemperature, Foreshadowing, PlotLedger, StateLog, StoryWiki


async def persist_changes(db: AsyncSession, project_id, chapter_sequence: int, merged_changes: dict) -> None:
    for item in merged_changes.get("changes", {}).get("character_state", []):
        db.add(
            StateLog(
                project_id=project_id,
                chapter_sequence=chapter_sequence,
                dimension="character_state",
                entity_name=item["name"],
                field=item.get("field"),
                old_value=item.get("old"),
                new_value=item.get("new"),
                confidence=item.get("confidence", 0.9),
                source="observer",
            )
        )
        existing_temperature = await db.scalar(
            select(EntityTemperature).where(
                EntityTemperature.project_id == project_id,
                EntityTemperature.entity_name == item["name"],
            )
        )
        if existing_temperature:
            existing_temperature.temperature = "hot"
            existing_temperature.last_referenced_chapter = chapter_sequence
            existing_temperature.compressed_summary = item.get("new")
        else:
            db.add(
                EntityTemperature(
                    project_id=project_id,
                    entity_name=item["name"],
                    entity_type="character",
                    temperature="hot",
                    last_referenced_chapter=chapter_sequence,
                    compressed_summary=item.get("new"),
                )
            )

    for item in merged_changes.get("changes", {}).get("foreshadowing", []):
        if item.get("action") == "plant":
            legacy = Foreshadowing(
                    project_id=project_id,
                    content=item["content"],
                    planted_chapter=chapter_sequence,
                    target_chapter=item.get("target_chapter"),
                    importance="B",
                    related_characters=[],
                )
            db.add(legacy)
            await db.flush()
            db.add(
                PlotLedger(
                    project_id=project_id,
                    type="dialog",
                    description=item["content"],
                    planted_chapter=chapter_sequence,
                    mentioned_chapters=[chapter_sequence],
                    due_chapter=item.get("target_chapter"),
                    origin_foreshadowing_id=legacy.id,
                )
            )


async def decay_temperatures(db: AsyncSession, project_id, current_chapter: int) -> None:
    """每章发布后执行：衰减实体温度。

    - last_referenced_chapter ≤ current_chapter - 30 → warm
    - last_referenced_chapter ≤ current_chapter - 100 → cold
    - 不触发热区的实体：降温
    """
    await db.execute(
        update(EntityTemperature)
        .where(
            EntityTemperature.project_id == project_id,
            EntityTemperature.last_referenced_chapter <= current_chapter - 100,
        )
        .values(temperature="cold")
    )
    await db.execute(
        update(EntityTemperature)
        .where(
            EntityTemperature.project_id == project_id,
            EntityTemperature.last_referenced_chapter <= current_chapter - 30,
            EntityTemperature.temperature != "cold",
        )
        .values(temperature="warm")
    )


async def decay_current_states(db: AsyncSession, project_id, current_chapter: int) -> None:
    """CurrentState 表也同步做温度衰减。"""
    await db.execute(
        update(CurrentState)
        .where(
            CurrentState.project_id == project_id,
            CurrentState.last_chapter_sequence <= current_chapter - 100,
        )
        .values(temperature="cold")
    )
    await db.execute(
        update(CurrentState)
        .where(
            CurrentState.project_id == project_id,
            CurrentState.last_chapter_sequence <= current_chapter - 30,
            CurrentState.temperature != "cold",
        )
        .values(temperature="warm")
    )


async def ingest_wiki_updates(
    db: AsyncSession,
    project_id,
    protagonist: str,
    chapter_sequence: int,
    summary: str,
) -> None:
    page = await db.scalar(select(StoryWiki).where(StoryWiki.project_id == project_id, StoryWiki.slug == protagonist))
    if page is None:
        return
    page.last_updated_chapter = chapter_sequence
    page.source_chapters = sorted(set([*page.source_chapters, chapter_sequence]))
    page.content = page.content.rstrip() + f"\n- 第{chapter_sequence}章更新：{summary}\n"
