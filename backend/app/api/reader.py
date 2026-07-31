from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.context import build_context_pack
from app.models import Chapter, Project, ReaderFeedback, User
from app.schemas import HealthCheckResponse, ReaderFeedbackRead
from app.services.auth import get_current_user

router = APIRouter(tags=["reader-feedback"])
logger = logging.getLogger(__name__)


@router.get("/projects/{project_id}/reader-feedback", response_model=list[ReaderFeedbackRead])
async def get_reader_feedback(
    project_id: uuid.UUID,
    chapter_sequence: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReaderFeedbackRead]:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    query = select(ReaderFeedback).where(ReaderFeedback.project_id == project_id)
    if chapter_sequence is not None:
        query = query.where(ReaderFeedback.chapter_sequence == chapter_sequence)
    query = query.order_by(ReaderFeedback.chapter_sequence.desc(), ReaderFeedback.created_at.desc()).limit(50)

    rows = list((await db.scalars(query)).all())
    return [ReaderFeedbackRead.model_validate(r) for r in rows]


@router.post("/projects/{project_id}/reader-feedback/{chapter_sequence}", response_model=ReaderFeedbackRead)
async def generate_feedback(
    project_id: uuid.UUID,
    chapter_sequence: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReaderFeedbackRead:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    chapter = await db.scalar(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_sequence == chapter_sequence,
        )
    )
    if not chapter or not chapter.content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在或尚未生成")

    from app.services.ai_assist import generate_reader_feedback

    context_pack = await build_context_pack(db, project, chapter_sequence)
    canon_context = str({
        "current_state": context_pack.get("current_state", {}),
        "story_wiki": context_pack.get("story_wiki", []),
        "recent_chapters": context_pack.get("recent_chapters", []),
    })
    try:
        feedback_data = await generate_reader_feedback(
            chapter_content=chapter.content,
            preceding_summary=chapter.summary,
            chapter_plan=chapter.beat_sheet,
            canon_context=canon_context,
            track_info=project.track,
        )
    except Exception as exc:
        logger.exception(
            "章节检查失败 project_id=%s chapter_sequence=%s error_type=%s",
            project_id,
            chapter_sequence,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="章节检查暂时没有返回可核验结果，请稍后重试",
        ) from exc

    feedback = ReaderFeedback(
        project_id=project_id,
        chapter_sequence=chapter_sequence,
        source="ai",
        chase_score=None,
        summary=feedback_data.get("summary"),
        readers=[],
        thrill_analysis={
            "verdict": feedback_data.get("verdict", "pass"),
            "checks": feedback_data.get("checks", []),
        },
        risk_points=[
            item for item in feedback_data.get("checks", [])
            if item.get("status") in {"warning", "fail"}
        ],
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return ReaderFeedbackRead.model_validate(feedback)


@router.get("/projects/{project_id}/health-check", response_model=HealthCheckResponse)
async def health_check(
    project_id: uuid.UUID,
    start: int = Query(1, ge=1),
    end: int = Query(10, ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HealthCheckResponse:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    from app.services.ai_assist import generate_health_check

    result = await generate_health_check(db, project_id, start, end)
    return HealthCheckResponse(**result)
