import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Project, StoryWiki, User
from app.schemas import StoryWikiCreate, StoryWikiRead, StoryWikiUpdate
from app.services.auth import get_current_user

router = APIRouter(prefix="/projects/{project_id}/bible", tags=["bible"])


@router.post("", response_model=StoryWikiRead, status_code=status.HTTP_201_CREATED)
async def create_bible_page(
    project_id: uuid.UUID,
    payload: StoryWikiCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StoryWikiRead:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    page = StoryWiki(
        project_id=project_id,
        slug=f"manual-{payload.category}-{uuid.uuid4().hex[:12]}",
        category=payload.category,
        title=payload.title,
        content=payload.content,
        aliases=payload.aliases,
        source="manual",
    )
    db.add(page)
    await db.commit()
    await db.refresh(page)
    return StoryWikiRead.model_validate(page)


@router.put("/{page_id}", response_model=StoryWikiRead)
async def update_bible_page(
    project_id: uuid.UUID,
    page_id: uuid.UUID,
    payload: StoryWikiUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StoryWikiRead:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    page = await db.scalar(select(StoryWiki).where(StoryWiki.id == page_id, StoryWiki.project_id == project_id))
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设定页不存在")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(page, field, value)

    await db.commit()
    await db.refresh(page)
    return StoryWikiRead.model_validate(page)


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bible_page(
    project_id: uuid.UUID,
    page_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    page = await db.scalar(select(StoryWiki).where(StoryWiki.id == page_id, StoryWiki.project_id == project_id))
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设定页不存在")
    await db.delete(page)
    await db.commit()
