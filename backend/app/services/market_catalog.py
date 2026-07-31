from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MarketTrack, TropeLibrary

SEED_DIR = Path(__file__).resolve().parent.parent / "seed_data"


async def ensure_market_catalog(db: AsyncSession) -> dict[str, int]:
    """Idempotently install the bundled market taxonomy for a fresh database."""
    counts = {"tracks": 0, "tropes": 0}
    track_data = json.loads((SEED_DIR / "market_tracks.json").read_text("utf-8"))
    existing_track_names = set((await db.scalars(select(MarketTrack.track_name))).all())
    for item in track_data:
        if item["track_name"] not in existing_track_names:
            db.add(MarketTrack(**item))
            counts["tracks"] += 1

    trope_data = json.loads((SEED_DIR / "trope_library.json").read_text("utf-8"))
    existing_trope_names = set((await db.scalars(select(TropeLibrary.trope_name))).all())
    for item in trope_data:
        if item["trope_name"] not in existing_trope_names:
            db.add(TropeLibrary(**item))
            counts["tropes"] += 1

    if any(counts.values()):
        await db.commit()
    return counts
