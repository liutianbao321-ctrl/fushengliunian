"""蓝图域 REST API。

契约（与前端严格一致）：
- GET  /api/projects/{project_id}/blueprint                       -> {nodes:[OutlineNode]}
- PUT  /api/blueprint/nodes/{node_id}                             body {title?,body?,status?,seq?,meta?}
- POST /api/projects/{project_id}/blueprint/generate             body {layer,parent_id?,regenerate_node_id?} -> 202 {job_id}
- GET  /api/projects/{project_id}/plot-ledger                    -> {entries:[...]}
- GET  /api/projects/{project_id}/pacing-config                   (无则按默认持久化并返回)
- PUT  /api/projects/{project_id}/pacing-config                   body {...}
- GET  /api/chapters/{chapter_id}/beat-card                      (无卡 -> 404 {"detail":"no beat card"})
- PUT  /api/chapters/{chapter_id}/beat-card                      body {fields?,status?}
- POST /api/chapters/{chapter_id}/beat-card/regenerate           -> 202 {job_id}
- GET  /api/jobs/{job_id}                                        任务进度/结果
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import get_owned_project
from app.database import get_db
from app.models import (
    BeatCard,
    BlueprintJob,
    Chapter,
    OutlineNode,
    PacingConfig,
    PlotLedger,
)
from app.services.auth import get_current_user
from app.services.blueprint_worker import blueprint_job_runner

router = APIRouter(tags=["blueprint"])

LAYER_SET = {"L0", "L1", "L2", "L3", "L4", "L5"}


# --------------------------------------------------------------------------- #
# 请求体
# --------------------------------------------------------------------------- #
class OutlineNodeUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    status: str | None = None
    seq: int | None = None
    meta: dict | None = None


class BlueprintGenerateRequest(BaseModel):
    layer: str
    parent_id: str | None = None
    regenerate_node_id: str | None = None


class PacingConfigUpdate(BaseModel):
    minor_climax_cycle: int | None = None
    major_climax_cycle: int | None = None
    sweet_density: float | None = None
    mode: str | None = None
    opening_mode: bool | None = None


class BeatCardUpdate(BaseModel):
    fields: dict | None = None
    status: str | None = None


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
async def _get_owned_chapter(db: AsyncSession, chapter_ref: str, user_id: uuid.UUID) -> Chapter:
    """Beat 卡路由以章节 id（UUID）为主；纯数字则回退为 chapter_sequence 解析。"""
    chapter: Chapter | None = None
    try:
        chapter_id = uuid.UUID(chapter_ref)
        chapter = await db.get(Chapter, chapter_id)
    except ValueError:
        if chapter_ref.isdigit():
            chapter = await db.scalar(
                select(Chapter).where(Chapter.chapter_sequence == int(chapter_ref)).limit(1)
            )
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")
    await get_owned_project(db, chapter.project_id, user_id)
    return chapter


def _node_to_dict(node: OutlineNode) -> dict[str, Any]:
    return {
        "id": str(node.id),
        "project_id": str(node.project_id),
        "layer": node.layer,
        "parent_id": str(node.parent_id) if node.parent_id else None,
        "seq": node.seq,
        "title": node.title,
        "body": node.body,
        "status": node.status,
        "meta": node.meta,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
    }


def _pacing_to_dict(c: PacingConfig) -> dict[str, Any]:
    return {
        "project_id": str(c.project_id),
        "minor_climax_cycle": c.minor_climax_cycle,
        "major_climax_cycle": c.major_climax_cycle,
        "sweet_density": c.sweet_density,
        "mode": c.mode,
        "opening_mode": c.opening_mode,
    }


# --------------------------------------------------------------------------- #
# 大纲
# --------------------------------------------------------------------------- #
@router.get("/projects/{project_id}/blueprint")
async def get_blueprint(
    project_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await get_owned_project(db, project_id, current_user.id)
    nodes = list(
        (
            await db.scalars(
                select(OutlineNode)
                .where(OutlineNode.project_id == project_id)
                .order_by(OutlineNode.layer.asc(), OutlineNode.seq.asc())
            )
        ).all()
    )
    return {"nodes": [_node_to_dict(n) for n in nodes]}


@router.put("/blueprint/nodes/{node_id}")
async def update_node(
    node_id: uuid.UUID,
    body: OutlineNodeUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    node = await db.get(OutlineNode, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="节点不存在")
    await get_owned_project(db, node.project_id, current_user.id)
    if body.title is not None:
        node.title = body.title
    if body.body is not None:
        node.body = body.body
    if body.status is not None:
        node.status = body.status
    if body.seq is not None:
        node.seq = body.seq
    if body.meta is not None:
        node.meta = body.meta
    node.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(node)
    return _node_to_dict(node)


@router.post("/projects/{project_id}/blueprint/generate")
async def generate_blueprint(
    project_id: uuid.UUID,
    body: BlueprintGenerateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await get_owned_project(db, project_id, current_user.id)
    if body.layer not in LAYER_SET:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="layer 必须是 L0-L5 之一")
    payload: dict[str, Any] = {
        "layer": body.layer,
        "parent_id": body.parent_id,
        "regenerate_node_id": body.regenerate_node_id,
    }
    job = await blueprint_job_runner.enqueue(project_id=project_id, job_type="outline_generate", payload=payload)
    return JSONResponse(status_code=202, content={"job_id": str(job.id)})


# --------------------------------------------------------------------------- #
# 伏笔登记表
# --------------------------------------------------------------------------- #
@router.get("/projects/{project_id}/plot-ledger")
async def get_plot_ledger(
    project_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await get_owned_project(db, project_id, current_user.id)
    rows = list(
        (
            await db.scalars(
                select(PlotLedger)
                .where(PlotLedger.project_id == project_id)
                .order_by(PlotLedger.planted_chapter.asc())
            )
        ).all()
    )
    entries = [
        {
            "id": str(p.id),
            "project_id": str(p.project_id),
            "type": p.type,
            "description": p.description,
            "planted_chapter": p.planted_chapter,
            "mentioned_chapters": p.mentioned_chapters,
            "due_chapter": p.due_chapter,
            "resolved_chapter": p.resolved_chapter,
            "status": p.status,
            "is_yy": p.is_yy,
            "origin_foreshadowing_id": str(p.origin_foreshadowing_id) if p.origin_foreshadowing_id else None,
        }
        for p in rows
    ]
    return {"entries": entries}


# --------------------------------------------------------------------------- #
# 节奏参数
# --------------------------------------------------------------------------- #
@router.get("/projects/{project_id}/pacing-config")
async def get_pacing_config(
    project_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await get_owned_project(db, project_id, current_user.id)
    config = await db.get(PacingConfig, project.id)
    if config is None:
        config = PacingConfig(project_id=project.id)
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return _pacing_to_dict(config)


@router.put("/projects/{project_id}/pacing-config")
async def put_pacing_config(
    project_id: uuid.UUID,
    body: PacingConfigUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await get_owned_project(db, project_id, current_user.id)
    config = await db.get(PacingConfig, project.id)
    if config is None:
        config = PacingConfig(project_id=project.id)
        db.add(config)
    if body.minor_climax_cycle is not None:
        config.minor_climax_cycle = body.minor_climax_cycle
    if body.major_climax_cycle is not None:
        config.major_climax_cycle = body.major_climax_cycle
    if body.sweet_density is not None:
        config.sweet_density = body.sweet_density
    if body.mode is not None:
        config.mode = body.mode
    if body.opening_mode is not None:
        config.opening_mode = body.opening_mode
    config.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(config)
    return _pacing_to_dict(config)


# --------------------------------------------------------------------------- #
# Beat 卡
# --------------------------------------------------------------------------- #
@router.get("/chapters/{chapter_id}/beat-card")
async def get_beat_card(
    chapter_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    chapter = await _get_owned_chapter(db, chapter_id, current_user.id)
    card = await db.scalar(select(BeatCard).where(BeatCard.chapter_id == chapter.id))
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no beat card")
    return {
        "id": str(card.id),
        "chapter_id": str(card.chapter_id),
        "fields": card.fields,
        "status": card.status,
    }


@router.put("/chapters/{chapter_id}/beat-card")
async def put_beat_card(
    chapter_id: str,
    body: BeatCardUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    chapter = await _get_owned_chapter(db, chapter_id, current_user.id)
    card = await db.scalar(select(BeatCard).where(BeatCard.chapter_id == chapter.id))
    if card is None:
        card = BeatCard(
            id=uuid.uuid4(),
            chapter_id=chapter.id,
            fields=body.fields or {},
            status=body.status or "draft",
        )
        db.add(card)
    else:
        if body.fields is not None:
            card.fields = body.fields
        if body.status is not None:
            card.status = body.status
        card.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(card)
    return {
        "id": str(card.id),
        "chapter_id": str(card.chapter_id),
        "fields": card.fields,
        "status": card.status,
    }


@router.post("/chapters/{chapter_id}/beat-card/regenerate")
async def regenerate_beat_card(
    chapter_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    chapter = await _get_owned_chapter(db, chapter_id, current_user.id)
    job = await blueprint_job_runner.enqueue(
        project_id=chapter.project_id,
        job_type="beat_card_generate",
        payload={"chapter_id": str(chapter.id)},
    )
    return JSONResponse(status_code=202, content={"job_id": str(job.id)})


# --------------------------------------------------------------------------- #
# 任务查询（durable worker 薄别名）
# --------------------------------------------------------------------------- #
@router.get("/jobs/{job_id}")
async def get_job(
    job_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    job = await db.get(BlueprintJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    await get_owned_project(db, job.project_id, current_user.id)
    return {
        "job_id": str(job.id),
        "project_id": str(job.project_id),
        "job_type": job.job_type,
        "status": job.status,
        "result": job.result,
        "error": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }
