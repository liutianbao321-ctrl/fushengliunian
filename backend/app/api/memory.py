from __future__ import annotations

import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import get_owned_project
from app.database import get_db
from app.engine.retrieval import hybrid_search, pageindex_navigate
from app.engine.wiki import structural_lint
from app.models import ChapterRevision, User
from app.schemas import (
    ChapterRevisionRead,
    MemorySearchRequest,
    MemorySearchResponse,
    WikiLintResponse,
)
from app.services.auth import get_current_user

router = APIRouter(prefix="/projects/{project_id}", tags=["memory"])


@router.post("/memory/search", response_model=MemorySearchResponse)
async def search_memory(
    project_id: uuid.UUID,
    payload: MemorySearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemorySearchResponse:
    project = await get_owned_project(db, project_id, current_user.id)
    hybrid = []
    tree = []
    if payload.mode in {"hybrid", "both"}:
        hits = await hybrid_search(
            db,
            project_id,
            payload.query,
            entities=payload.entities,
            chapter_before=project.current_chapter + 1,
            limit=payload.limit,
        )
        hybrid = [asdict(hit) for hit in hits]
    if payload.mode in {"pageindex", "both"}:
        tree = await pageindex_navigate(
            db,
            project_id,
            payload.query,
            thread_id=f"novel-{project_id}-search-{uuid.uuid4()}",
            max_nodes=payload.limit,
        )
    return MemorySearchResponse(hybrid=hybrid, pageindex=tree)


@router.get("/wiki/lint", response_model=WikiLintResponse)
async def lint_wiki(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WikiLintResponse:
    project = await get_owned_project(db, project_id, current_user.id)
    issues = await structural_lint(db, project_id, project.current_chapter)
    return WikiLintResponse(issues=issues, issue_count=len(issues))


@router.get("/chapters/{chapter_sequence}/revisions", response_model=list[ChapterRevisionRead])
async def list_chapter_revisions(
    project_id: uuid.UUID,
    chapter_sequence: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChapterRevisionRead]:
    await get_owned_project(db, project_id, current_user.id)
    revisions = list(
        (
            await db.scalars(
                select(ChapterRevision)
                .where(
                    ChapterRevision.project_id == project_id,
                    ChapterRevision.chapter_sequence == chapter_sequence,
                )
                .order_by(ChapterRevision.revision.desc())
            )
        ).all()
    )
    return [ChapterRevisionRead.model_validate(item) for item in revisions]
