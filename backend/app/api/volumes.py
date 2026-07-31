"""卷末再规划 API：预览简报、生成下一卷卷纲、采纳落库。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import NovelToc, Outline, Project, User
from app.schemas import OutlineRead
from app.services.auth import get_current_user
from app.services.project_bootstrap import upgrade_project_to_volume_tree
from app.services.replan import build_replan_brief, generate_next_volume_plan

router = APIRouter(prefix="/projects/{project_id}/volumes", tags=["volumes"])


async def ensure_project(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> Project:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user_id))
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


@router.post("/upgrade-tree", response_model=list[OutlineRead])
async def upgrade_volume_tree(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OutlineRead]:
    """把旧单卷项目安全升级为多卷树，不触碰正文。"""
    project = await ensure_project(db, project_id, current_user.id)
    volumes = await upgrade_project_to_volume_tree(db, project)
    await db.commit()
    return [OutlineRead.model_validate(item) for item in volumes]


@router.get("/{volume_sequence}/replan-brief")
async def get_replan_brief(
    project_id: uuid.UUID,
    volume_sequence: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """预览"再规划简报"：系统在规划下一卷前知道的全部事实。"""
    project = await ensure_project(db, project_id, current_user.id)
    return await build_replan_brief(db, project, volume_sequence)


@router.post("/{volume_sequence}/generate-plan")
async def generate_volume_plan_endpoint(
    project_id: uuid.UUID,
    volume_sequence: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """基于简报生成下一卷卷纲（不落库，供用户审阅/换一版）。"""
    project = await ensure_project(db, project_id, current_user.id)
    brief = await build_replan_brief(db, project, volume_sequence)
    try:
        plan = await generate_next_volume_plan(brief)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"卷纲生成失败：{exc}") from exc
    return {"brief_summary": {
        "current_chapter": brief["current_chapter"],
        "active_foreshadowing_count": len(brief["active_foreshadowing"]),
        "overdue_count": sum(1 for f in brief["active_foreshadowing"] if f["overdue"]),
    }, "plan": plan}


class AdoptVolumePlanRequest(BaseModel):
    title: str
    goal: str
    opening: str = ""
    new_elements: dict = Field(default_factory=dict)
    turning_points: list[str] = Field(default_factory=list)
    climax: str = ""
    ending_hook: str = ""
    suggested_chapters: int = 0
    foreshadowing_to_resolve: list[str] = Field(default_factory=list)
    arcs: list[dict] = Field(default_factory=list)


@router.post("/{volume_sequence}/adopt-plan", response_model=list[OutlineRead])
async def adopt_volume_plan(
    project_id: uuid.UUID,
    volume_sequence: int,
    payload: AdoptVolumePlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OutlineRead]:
    """采纳卷纲：更新卷锚点为详细卷纲，并把弧列表落库为 arc 级大纲。"""
    await ensure_project(db, project_id, current_user.id)
    volume = await db.scalar(
        select(Outline).where(
            Outline.project_id == project_id,
            Outline.level == "volume",
            Outline.sequence == volume_sequence,
        )
    )
    if not volume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该卷不存在")

    volume.title = payload.title or volume.title
    chapter_range = volume.content.get("chapter_range", [1, 1])
    volume.content = {
        "goal": payload.goal,
        "opening": payload.opening,
        "new_elements": payload.new_elements,
        "turning_points": payload.turning_points,
        "climax": payload.climax,
        "ending_hook": payload.ending_hook,
        "suggested_chapters": payload.suggested_chapters,
        "foreshadowing_to_resolve": payload.foreshadowing_to_resolve,
        "chapter_range": chapter_range,
        "status": "detailed",
    }
    existing_arcs = list(
        (
            await db.scalars(
                select(Outline).where(
                    Outline.project_id == project_id,
                    Outline.level == "arc",
                    Outline.parent_id == volume.id,
                )
            )
        ).all()
    )
    for existing in existing_arcs:
        await db.delete(existing)
    # 弧级大纲作为该卷子节点
    created: list[Outline] = [volume]
    total_range = max(chapter_range[1] - chapter_range[0] + 1, 1)
    arc_start = chapter_range[0]
    total_est = sum(max(int(a.get("estimated_chapters") or 0), 1) for a in payload.arcs) or len(payload.arcs) or 1
    for arc in payload.arcs:
        est = max(int(arc.get("estimated_chapters") or 0), 1)
        span = max(round(total_range * est / total_est), 1)
        arc_end = min(arc_start + span - 1, chapter_range[1])
        arc_outline = Outline(
            project_id=project_id,
            parent_id=volume.id,
            level="arc",
            sequence=int(arc.get("sequence") or (len(created))),
            title=str(arc.get("title") or f"弧{arc.get('sequence', '')}"),
            content={
                "goal": arc.get("goal", ""),
                "conflict": arc.get("conflict", ""),
                "climax": arc.get("climax", ""),
                "resolution": arc.get("resolution", ""),
                "estimated_chapters": est,
                "chapter_range": [arc_start, arc_end],
                "involved_characters": arc.get("involved_characters", []),
            },
            is_sealed=False,
        )
        db.add(arc_outline)
        created.append(arc_outline)
        arc_start = arc_end + 1

    # 同步 NovelToc 卷节点
    volume_toc = await db.scalar(
        select(NovelToc).where(
            NovelToc.project_id == project_id,
            NovelToc.level == "volume",
            NovelToc.sequence == volume_sequence,
        )
    )
    if volume_toc:
        volume_toc.title = volume.title
        volume_toc.summary = payload.goal
        volume_toc.key_events = payload.turning_points[:6]

    await db.commit()
    for item in created:
        await db.refresh(item)
    return [OutlineRead.model_validate(item) for item in created]
