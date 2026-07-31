from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import HotNovel, MarketTrack, TropeLibrary, User
from app.schemas import HotNovelRead, MarketTrackRead, TropeRead
from app.services.auth import get_current_user
from app.services.market_catalog import ensure_market_catalog

router = APIRouter(prefix="/market", tags=["market"])

@router.get("/tracks", response_model=list[MarketTrackRead])
async def list_tracks(
    channel: str | None = Query(None),
    genre: str | None = Query(None),
    taste_tag: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MarketTrackRead]:
    await ensure_market_catalog(db)
    query = select(MarketTrack).order_by(MarketTrack.heat.desc())
    if channel:
        query = query.where(MarketTrack.channel == channel)
    if genre:
        query = query.where(MarketTrack.genre == genre)
    if taste_tag:
        query = query.where(MarketTrack.taste_tags.contains([taste_tag]))
    tracks = list((await db.scalars(query)).all())
    return [MarketTrackRead.model_validate(t) for t in tracks]


@router.get("/tracks/{track_id}", response_model=MarketTrackRead)
async def get_track(
    track_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarketTrackRead:
    track = await db.get(MarketTrack, track_id)
    if not track:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="赛道不存在")
    return MarketTrackRead.model_validate(track)


@router.get("/tropes", response_model=list[TropeRead])
async def list_tropes(
    channel: str | None = Query(None),
    genre: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TropeRead]:
    await ensure_market_catalog(db)
    query = select(TropeLibrary)
    if channel:
        query = query.where(TropeLibrary.channel == channel)
    if genre:
        query = query.where(TropeLibrary.genre == genre)
    tropes = list((await db.scalars(query)).all())
    return [TropeRead.model_validate(t) for t in tropes]


@router.get("/hot-novels", response_model=list[HotNovelRead])
async def list_hot_novels(
    genre: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HotNovelRead]:
    query = select(HotNovel).order_by(HotNovel.rank_position.asc().nullslast()).limit(limit)
    if genre:
        query = query.where(HotNovel.genre == genre)
    novels = list((await db.scalars(query)).all())
    return [HotNovelRead.model_validate(n) for n in novels]


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_market_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    counts = await ensure_market_catalog(db)
    return {"seeded": counts}
