from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ImmersiveSession, ImportedWork, User
from app.schemas import (
    ImmersiveChoiceRequest,
    ImmersiveSegment,
    ImmersiveSessionCreate,
    ImmersiveSessionRead,
    ProjectCreate,
    ProjectRead,
)
from app.services.auth import get_current_user

router = APIRouter(prefix="/immersive", tags=["immersive"])


@router.get("", response_model=list[ImmersiveSessionRead])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ImmersiveSessionRead]:
    sessions = list(
        (
            await db.scalars(
                select(ImmersiveSession)
                .where(ImmersiveSession.user_id == current_user.id)
                .order_by(ImmersiveSession.updated_at.desc())
            )
        ).all()
    )
    return [ImmersiveSessionRead.model_validate(s) for s in sessions]


@router.post("", response_model=ImmersiveSessionRead, status_code=status.HTTP_201_CREATED)
async def create_immersive_session(
    payload: ImmersiveSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImmersiveSessionRead:
    work = await db.scalar(
        select(ImportedWork).where(
            ImportedWork.id == payload.work_id, ImportedWork.user_id == current_user.id
        )
    )
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入作品不存在")
    if work.analysis_status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="作品分析尚未完成")

    from app.services.immersive_engine import create_session

    session = await create_session(
        db,
        user_id=current_user.id,
        work_id=payload.work_id,
        character_name=payload.character_name,
        experience_style=payload.experience_style,
    )
    return ImmersiveSessionRead.model_validate(session)


@router.get("/{session_id}", response_model=ImmersiveSessionRead)
async def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImmersiveSessionRead:
    session = await db.scalar(
        select(ImmersiveSession).where(
            ImmersiveSession.id == session_id, ImmersiveSession.user_id == current_user.id
        )
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="体验会话不存在")
    return ImmersiveSessionRead.model_validate(session)


@router.post("/{session_id}/choose", response_model=ImmersiveSegment)
async def make_choice(
    session_id: uuid.UUID,
    payload: ImmersiveChoiceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImmersiveSegment:
    session = await db.scalar(
        select(ImmersiveSession).where(
            ImmersiveSession.id == session_id, ImmersiveSession.user_id == current_user.id
        )
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="体验会话不存在")

    from app.services.immersive_engine import make_choice as engine_make_choice

    segment = await engine_make_choice(db, session, payload.choice_index)
    return ImmersiveSegment(
        narrative=segment.get("narrative", ""),
        choices=segment.get("choices", []),
        character_state=segment.get("character_state", {}),
    )


@router.post("/{session_id}/solidify", response_model=ProjectRead)
async def solidify_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    session = await db.scalar(
        select(ImmersiveSession).where(
            ImmersiveSession.id == session_id, ImmersiveSession.user_id == current_user.id
        )
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="体验会话不存在")

    from app.models import Project
    from app.services.immersive_engine import solidify_to_novel
    from app.services.project_bootstrap import seed_new_project

    project_data = await solidify_to_novel(db, session)
    source_work_id = project_data.pop("source_work_id", None)
    if source_work_id and isinstance(source_work_id, str):
        source_work_id = uuid.UUID(source_work_id)

    default_summary = "从代入体验中诞生的故事，延续角色的冒险旅程"
    one_sentence = project_data.get("one_sentence", default_summary)[:2000]
    payload = ProjectCreate(
        title=project_data.get("title", "体验固化作品"),
        genre=project_data.get("genre", "玄幻"),
        one_sentence=one_sentence if len(one_sentence) >= 10 else default_summary,
        protagonist_name=project_data.get("protagonist_name", session.character_name),
        protagonist_gender=project_data.get("protagonist_gender", "男"),
        protagonist_personality=project_data.get("protagonist_personality", "坚毅果敢"),
        target_words=project_data.get("target_words", 300_000),
        creation_mode="immersive",
        source_work_id=source_work_id,
    )

    project = Project(
        user_id=current_user.id,
        title=payload.title,
        genre=payload.genre,
        one_sentence=payload.one_sentence,
        protagonist_name=payload.protagonist_name,
        protagonist_gender=payload.protagonist_gender,
        protagonist_personality=payload.protagonist_personality,
        target_words=payload.target_words,
        creation_mode="immersive",
        source_work_id=source_work_id,
    )
    db.add(project)
    await db.flush()
    await seed_new_project(db, project, payload)

    session.project_id = project.id
    await db.commit()
    await db.refresh(project)
    return ProjectRead.model_validate(project)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    session = await db.scalar(
        select(ImmersiveSession).where(
            ImmersiveSession.id == session_id, ImmersiveSession.user_id == current_user.id
        )
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="体验会话不存在")
    await db.delete(session)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
