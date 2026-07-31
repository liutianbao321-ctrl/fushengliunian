import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.retrieval import writing_guide_search, writing_method_card_search
from app.models import PlotDevice, SceneTemplate, User, WritingMethodCard
from app.services.auth import get_current_user

router = APIRouter(prefix="/knowledge", tags=["writing-knowledge"])


class MethodCardReview(BaseModel):
    status: Literal["draft", "published", "rejected"]


@router.get("/search")
async def search_writing_knowledge(
    query: str = Query(min_length=2, max_length=500),
    tags: list[str] = Query(default=[]),
    limit: int = Query(default=6, ge=1, le=20),
    card_status: Literal["published", "draft", "rejected"] = "published",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    del current_user
    cards = await writing_method_card_search(
        db,
        query,
        tags=tags or None,
        limit=min(limit, 8),
        status=card_status,
    )
    excerpts = await writing_guide_search(db, query, tags=tags or None, limit=limit)
    return {"query": query, "method_cards": cards, "source_excerpts": excerpts}


@router.patch("/method-cards/{card_id}")
async def review_method_card(
    card_id: uuid.UUID,
    payload: MethodCardReview,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    del current_user
    card = await db.get(WritingMethodCard, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="方法卡不存在")
    card.status = payload.status
    card.revision += 1
    await db.commit()
    return {"card_id": str(card.id), "status": card.status, "revision": card.revision}


# ─── Genre packs ─────────────────────────────────────────────

GENRE_LIST = ["玄幻", "仙侠", "都市", "言情", "悬疑", "科幻", "历史", "游戏"]


@router.get("/genre-packs")
async def list_genre_packs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    del current_user
    cards = list(
        (await db.scalars(
            select(WritingMethodCard)
            .where(WritingMethodCard.status == "published")
            .order_by(WritingMethodCard.genre.nullslast(), WritingMethodCard.revision.desc())
        )).all()
    )
    scenes = list(
        (await db.scalars(
            select(SceneTemplate).order_by(SceneTemplate.priority.desc())
        )).all()
    )
    devices = list(
        (await db.scalars(
            select(PlotDevice).order_by(PlotDevice.priority.desc())
        )).all()
    )

    genre_map: dict[str, dict] = {}
    for g in GENRE_LIST:
        genre_map[g] = {"genre": g, "method_cards": [], "scene_templates": [], "plot_devices": []}

    for c in cards:
        g = c.genre or "通用"
        genre_map.setdefault(g, {"genre": g, "method_cards": [], "scene_templates": [], "plot_devices": []})
        genre_map[g]["method_cards"].append({
            "id": str(c.id), "slug": c.slug, "title": c.title, "principle": c.principle,
            "when_to_use": c.when_to_use, "procedure": c.procedure,
            "checks": c.checks, "anti_patterns": c.anti_patterns, "tags": c.tags,
        })
    for s in scenes:
        g = s.genre or "通用"
        genre_map.setdefault(g, {"genre": g, "method_cards": [], "scene_templates": [], "plot_devices": []})
        genre_map[g]["scene_templates"].append({
            "id": str(s.id), "slug": s.slug, "title": s.title, "scene_type": s.scene_type,
            "tension_arc": s.tension_arc, "beats": s.beats,
            "entry_condition": s.entry_condition, "exit_condition": s.exit_condition,
            "emotional_shift": s.emotional_shift, "anti_patterns": s.anti_patterns,
        })
    for d in devices:
        g = d.genre or "通用"
        genre_map.setdefault(g, {"genre": g, "method_cards": [], "scene_templates": [], "plot_devices": []})
        genre_map[g]["plot_devices"].append({
            "id": str(d.id), "slug": d.slug, "title": d.title, "device_type": d.device_type,
            "description": d.description, "setup": d.setup, "escalation": d.escalation,
            "payoff": d.payoff, "common_mistakes": d.common_mistakes,
        })
    return {"packs": list(genre_map.values())}


# ─── Scene templates ────────────────────────────────────────


class SceneTemplateUpdate(BaseModel):
    title: str | None = None
    scene_type: str | None = None
    genre: str | None = None
    tension_arc: str | None = None
    beats: list[str] | None = None
    pov_suggestion: str | None = None
    entry_condition: str | None = None
    exit_condition: str | None = None
    emotional_shift: str | None = None
    anti_patterns: list[str] | None = None
    tags: list[str] | None = None
    priority: int | None = None


@router.get("/scene-templates")
async def list_scene_templates(
    scene_type: str | None = None,
    genre: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    del current_user
    filters = []
    if scene_type:
        filters.append(SceneTemplate.scene_type == scene_type)
    if genre:
        filters.append(SceneTemplate.genre.in_([genre, None]))
    rows = list(
        (await db.scalars(
            select(SceneTemplate).where(*filters).order_by(SceneTemplate.priority.desc())
        )).all()
    )
    return {
        "scene_templates": [
            {
                "id": str(r.id), "slug": r.slug, "title": r.title, "scene_type": r.scene_type,
                "genre": r.genre, "tension_arc": r.tension_arc, "beats": r.beats,
                "pov_suggestion": r.pov_suggestion, "entry_condition": r.entry_condition,
                "exit_condition": r.exit_condition, "emotional_shift": r.emotional_shift,
                "anti_patterns": r.anti_patterns, "tags": r.tags, "priority": r.priority,
            }
            for r in rows
        ]
    }


@router.put("/scene-templates/{slug}")
async def update_scene_template(
    slug: str,
    payload: SceneTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    del current_user
    template = await db.scalar(select(SceneTemplate).where(SceneTemplate.slug == slug))
    if not template:
        raise HTTPException(404, "场景模板不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(template, field, value)
    await db.commit()
    return {"slug": slug, "status": "updated"}


# ─── Plot devices ────────────────────────────────────────────


class PlotDeviceUpdate(BaseModel):
    title: str | None = None
    device_type: str | None = None
    genre: str | None = None
    description: str | None = None
    setup: list[str] | None = None
    escalation: list[str] | None = None
    payoff: list[str] | None = None
    common_mistakes: list[str] | None = None
    tags: list[str] | None = None
    priority: int | None = None


@router.get("/plot-devices")
async def list_plot_devices(
    device_type: str | None = None,
    genre: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    del current_user
    filters = []
    if device_type:
        filters.append(PlotDevice.device_type == device_type)
    if genre:
        filters.append(PlotDevice.genre.in_([genre, None]))
    rows = list(
        (await db.scalars(
            select(PlotDevice).where(*filters).order_by(PlotDevice.priority.desc())
        )).all()
    )
    return {
        "plot_devices": [
            {
                "id": str(r.id), "slug": r.slug, "title": r.title, "device_type": r.device_type,
                "genre": r.genre, "description": r.description,
                "setup": r.setup, "escalation": r.escalation, "payoff": r.payoff,
                "common_mistakes": r.common_mistakes, "tags": r.tags, "priority": r.priority,
            }
            for r in rows
        ]
    }


@router.put("/plot-devices/{slug}")
async def update_plot_device(
    slug: str,
    payload: PlotDeviceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    del current_user
    device = await db.scalar(select(PlotDevice).where(PlotDevice.slug == slug))
    if not device:
        raise HTTPException(404, "桥段不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(device, field, value)
    await db.commit()
    return {"slug": slug, "status": "updated"}
