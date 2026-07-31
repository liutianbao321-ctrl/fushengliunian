from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.engine.retrieval import embed_text, embedding_configured
from app.models import CurrentState, StateLog


@dataclass(slots=True)
class EntityMemoryHit:
    entity_key: str
    entity_type: str
    field: str
    value: str
    chapter_sequence: int
    temperature: str
    confidence: float
    score: float


async def search_entity_memory(
    db: AsyncSession,
    project_id,
    query: str,
    *,
    entities: list[str] | None = None,
    chapter_before: int | None = None,
    limit: int = 20,
) -> list[EntityMemoryHit]:
    """语义检索实体记忆 — 从 CurrentState 中找与 query 最相关的过去状态。"""

    base_filters = [CurrentState.project_id == project_id]
    if chapter_before is not None:
        base_filters.append(CurrentState.last_chapter_sequence < chapter_before)

    hot_warm = list(
        (
            await db.scalars(
                select(CurrentState)
                .where(
                    *base_filters,
                    or_(
                        CurrentState.temperature.in_(["hot", "warm"]),
                        CurrentState.entity_key.in_(entities or []),
                    ),
                )
                .order_by(CurrentState.last_chapter_sequence.desc(), CurrentState.confidence.desc())
                .limit(limit * 2)
            )
        ).all()
    )
    results: dict[str, EntityMemoryHit] = {}
    for s in hot_warm:
        key = f"{s.entity_key}:{s.field}"
        score = 1.0 if s.temperature == "hot" else 0.7
        if entities and s.entity_key in entities:
            score += 0.3
        results[key] = EntityMemoryHit(
            entity_key=s.entity_key,
            entity_type=s.entity_type,
            field=s.field,
            value=s.value,
            chapter_sequence=s.last_chapter_sequence,
            temperature=s.temperature,
            confidence=s.confidence,
            score=score,
        )

    embedding = await _embed_safe(query)
    if embedding is not None:
        distance = CurrentState.embedding.cosine_distance(embedding)
        settings = get_settings()
        vector_rows = (
            await db.execute(
                select(CurrentState, distance.label("distance"))
                .where(
                    *base_filters,
                    CurrentState.embedding.is_not(None),
                    CurrentState.embedding_model == settings.embedding_model,
                    CurrentState.embedding_dimensions == settings.embedding_dimensions,
                    CurrentState.temperature == "cold",
                    ~CurrentState.entity_key.in_(entities or []),
                )
                .order_by(distance.asc())
                .limit(limit)
            )
        ).all()
        for state, dist in vector_rows:
            key = f"{state.entity_key}:{state.field}"
            if key not in results:
                results[key] = EntityMemoryHit(
                    entity_key=state.entity_key,
                    entity_type=state.entity_type,
                    field=state.field,
                    value=state.value,
                    chapter_sequence=state.last_chapter_sequence,
                    temperature=state.temperature,
                    confidence=state.confidence,
                    score=max(0.0, 1.0 - dist),
                )

    sorted_hits = sorted(results.values(), key=lambda h: h.score, reverse=True)
    return sorted_hits[:limit]


async def search_state_log(
    db: AsyncSession,
    project_id,
    entity_key: str,
    *,
    limit: int = 10,
) -> list[dict]:
    """检索实体的状态变化历史（StateLog）。"""
    rows = (
        await db.scalars(
            select(StateLog)
            .where(
                StateLog.project_id == project_id,
                StateLog.entity_name == entity_key,
            )
            .order_by(StateLog.chapter_sequence.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "chapter": r.chapter_sequence,
            "field": r.field,
            "old": r.old_value,
            "new": r.new_value,
            "confidence": r.confidence,
        }
        for r in rows
    ]


async def _embed_safe(text: str) -> list[float] | None:
    """带 fallback 的 embedding 调用。"""
    if not text or not embedding_configured():
        return None
    try:
        return await embed_text(text)
    except (httpx.HTTPError, ValueError, KeyError):
        return None
