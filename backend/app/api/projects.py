import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CreationArtifact, CreationSession, ImportedWork, Project, StoryWiki, User, ViabilityReview
from app.schemas import ForeshadowingRead, ProjectCreate, ProjectRead, ProjectUpdate, StateLogRead, StoryWikiRead
from app.services.auth import get_current_user
from app.services.project_bootstrap import seed_new_project

router = APIRouter(prefix="/projects", tags=["projects"])


def _source_inheritance(payload: ProjectCreate) -> tuple[bool, bool]:
    """Return whether an imported source should enter facts and narrative memory."""
    if not payload.source_work_id:
        return False, False
    derivative = (payload.intent_brief or {}).get("source_derivative")
    derivative = derivative if isinstance(derivative, dict) else {}
    fanfic_type = str(derivative.get("fanfic_type") or "")
    mode = str(derivative.get("mode") or payload.creation_mode)
    inherit_facts = payload.creation_mode in {"continuation", "fanfic"} or mode in {"continuation", "fanfic"}
    inherit_narrative = (
        payload.creation_mode == "continuation"
        or mode == "continuation"
        or fanfic_type == "fanfic_continuation"
    )
    return inherit_facts, inherit_narrative


async def get_owned_project(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> Project:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user_id))
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectRead]:
    projects = list(
        (
            await db.scalars(
                select(Project).where(Project.user_id == current_user.id).order_by(Project.updated_at.desc())
            )
        ).all()
    )
    return [ProjectRead.model_validate(item) for item in projects]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    creation_session = None
    if payload.creation_session_id:
        creation_session = await db.scalar(
            select(CreationSession).where(
                CreationSession.id == payload.creation_session_id,
                CreationSession.user_id == current_user.id,
            )
        )
        if creation_session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="建书会话不存在")
        review = await db.scalar(
            select(ViabilityReview).where(
                ViabilityReview.session_id == creation_session.id,
                ViabilityReview.foundation_version == creation_session.foundation_version,
                ViabilityReview.author_confirmed.is_(True),
            )
        )
        foundation = (payload.planning_profile or {}).get("creation_v2")
        if (
            creation_session.state != "PILOT_GENERATED"
            or review is None
            or review.verdict != "pass"
            or foundation != creation_session.foundation
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="建书会话尚未通过评审、确认和首章试写")
        research_artifact = await db.scalar(
            select(CreationArtifact)
            .where(
                CreationArtifact.session_id == creation_session.id,
                CreationArtifact.artifact_type == "web_research",
            )
            .order_by(CreationArtifact.version.desc())
            .limit(1)
        )
        if research_artifact is not None:
            payload.planning_profile["web_research"] = research_artifact.payload
    source_work = None
    if payload.source_work_id:
        source_work = await db.scalar(
            select(ImportedWork).where(
                ImportedWork.id == payload.source_work_id,
                ImportedWork.user_id == current_user.id,
                ImportedWork.analysis_status == "completed",
            )
        )
        if source_work is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="来源作品不存在或尚未分析完成")
    project = Project(
        user_id=current_user.id,
        title=payload.title,
        genre=payload.genre,
        one_sentence=payload.one_sentence,
        protagonist_name=payload.protagonist_name,
        protagonist_gender=payload.protagonist_gender,
        protagonist_personality=payload.protagonist_personality,
        target_words=payload.target_words,
        creation_mode=payload.creation_mode,
        channel=payload.channel,
        track=payload.track,
        source_work_id=payload.source_work_id,
        golden_finger=payload.golden_finger or "",
        intent_brief=payload.intent_brief or {},
    )
    db.add(project)
    await db.flush()
    await seed_new_project(db, project, payload)
    if creation_session is not None:
        creation_session.project_id = project.id
        creation_session.state = "BOOK_ESTABLISHED"
    if source_work:
        from app.services.imported_project import materialize_imported_assets

        inherit_facts, inherit_narrative = _source_inheritance(payload)
        await materialize_imported_assets(
            db,
            project,
            source_work,
            inherit_facts=inherit_facts,
            inherit_narrative=inherit_narrative,
        )
    await db.commit()
    await db.refresh(project)
    return ProjectRead.model_validate(project)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    project = await get_owned_project(db, project_id, current_user.id)
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    project = await get_owned_project(db, project_id, current_user.id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    if payload.style_profile is not None:
        constitution = payload.style_profile.get("author_constitution", {})
        if isinstance(constitution, dict):
            page = await db.scalar(
                select(StoryWiki).where(
                    StoryWiki.project_id == project_id,
                    StoryWiki.slug == "author-constitution",
                )
            )
            if page:
                page.content = (
                    "# 作者与读者约定\n\n"
                    f"- 为什么写：{constitution.get('why_write') or '未填写'}\n"
                    f"- 读者持续获得：{constitution.get('reader_promise') or '随当前故事蓝图执行'}\n"
                    f"- 想留下的感受：{constitution.get('lasting_feeling') or '未填写'}\n"
                    f"- 不可妥协：{constitution.get('non_negotiables') or '无额外约束'}\n"
                    f"- AI 协作边界：{constitution.get('ai_mandate') or '方向变化先由作者确认'}\n"
                    f"- 每章验收：{constitution.get('chapter_test') or '本章是否兑现读者期待，并由人物选择改变局面'}\n"
                )
    await db.commit()
    await db.refresh(project)
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    project = await get_owned_project(db, project_id, current_user.id)
    await db.delete(project)
    await db.commit()


@router.get("/{project_id}/bible", response_model=list[StoryWikiRead])
async def get_bible(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StoryWikiRead]:
    await get_owned_project(db, project_id, current_user.id)
    pages = list((await db.scalars(select(StoryWiki).where(StoryWiki.project_id == project_id))).all())
    return [StoryWikiRead.model_validate(page) for page in pages]


@router.get("/{project_id}/snapshot", response_model=list[StateLogRead])
async def get_snapshot(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StateLogRead]:
    from app.models import StateLog

    await get_owned_project(db, project_id, current_user.id)
    rows = list(
        (
            await db.scalars(
                select(StateLog)
                .where(StateLog.project_id == project_id)
                .order_by(StateLog.chapter_sequence.desc(), StateLog.created_at.desc())
                .limit(100)
            )
        ).all()
    )
    return [StateLogRead.model_validate(row) for row in rows]


@router.get("/{project_id}/foreshadowing", response_model=list[ForeshadowingRead])
async def get_foreshadowing(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ForeshadowingRead]:
    from app.models import Foreshadowing

    await get_owned_project(db, project_id, current_user.id)
    items = list((await db.scalars(select(Foreshadowing).where(Foreshadowing.project_id == project_id))).all())
    return [ForeshadowingRead.model_validate(item) for item in items]


@router.get("/{project_id}/timeline")
async def get_timeline(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await get_owned_project(db, project_id, current_user.id)
    pages = list(
        (
            await db.scalars(
                select(StoryWiki)
                .where(StoryWiki.project_id == project_id, StoryWiki.category == "timeline")
                .order_by(StoryWiki.updated_at.desc())
            )
        ).all()
    )
    return {"items": [StoryWikiRead.model_validate(page).model_dump() for page in pages]}
