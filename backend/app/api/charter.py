from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.charter import get_charter, save_charter
from app.models import Project, User
from app.services.auth import get_current_user

router = APIRouter(prefix="/projects/{project_id}/charter", tags=["charter"])


class CharterResponse(BaseModel):
    narrative_focus: str
    red_lines: list[str]
    mandates: list[str]
    target_readers: str
    tone_reference: str


class CharterUpdate(BaseModel):
    narrative_focus: str = ""
    red_lines: list[str] = []
    mandates: list[str] = []
    target_readers: str = ""
    tone_reference: str = ""


@router.get("")
async def read_charter(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CharterResponse | dict:
    owned = await db.scalar(select(Project.id).where(Project.id == project_id, Project.user_id == current_user.id))
    if owned is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    charter = await get_charter(db, project_id)
    if not charter:
        return {}
    return CharterResponse(
        narrative_focus=charter.narrative_focus,
        red_lines=charter.red_lines,
        mandates=charter.mandates,
        target_readers=charter.target_readers,
        tone_reference=charter.tone_reference,
    )


@router.put("")
async def update_charter(
    project_id: uuid.UUID,
    body: CharterUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CharterResponse:
    owned = await db.scalar(select(Project.id).where(Project.id == project_id, Project.user_id == current_user.id))
    if owned is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    charter = await save_charter(
        db,
        project_id,
        narrative_focus=body.narrative_focus,
        red_lines=body.red_lines,
        mandates=body.mandates,
        target_readers=body.target_readers,
        tone_reference=body.tone_reference,
    )
    await db.commit()
    return CharterResponse(
        narrative_focus=charter.narrative_focus,
        red_lines=charter.red_lines,
        mandates=charter.mandates,
        target_readers=charter.target_readers,
        tone_reference=charter.tone_reference,
    )
