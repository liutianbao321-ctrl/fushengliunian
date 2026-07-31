from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import SessionLocal, get_db
from app.models import CreationArtifact, CreationDecision, CreationSession, User, ViabilityReview
from app.schemas import (
    BookBlueprintRequest,
    CharacterCastRequest,
    CreationDirectionSelectRequest,
    CreationFoundationRequest,
    CreationFoundationResponse,
    CreationStudioConfirmRequest,
    CreationStudioRead,
    CreationStudioStartRequest,
    FoundationSectionRequest,
    FoundationSectionResponse,
    OpeningPilotRequest,
    OpeningPilotResponse,
    StoryRefineRequest,
    StorySeed,
    StorySeedRequest,
    StorySeedResponse,
    StyleAnalyzeRequest,
    StylePolishRequest,
    StylePolishResponse,
    TasteMatchRequest,
    TasteMatchResponse,
    WorldEngineRequest,
    WorldEngineResponse,
)
from app.services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai-assist"])

FoundationJob = dict[str, Any]
_foundation_jobs: OrderedDict[str, FoundationJob] = OrderedDict()
_foundation_tasks: dict[str, asyncio.Task[None]] = {}
_FOUNDATION_JOB_LIMIT = 30
PilotJob = dict[str, Any]
_pilot_jobs: OrderedDict[str, PilotJob] = OrderedDict()
_pilot_tasks: dict[str, asyncio.Task[None]] = {}
_PILOT_JOB_LIMIT = 30
_creation_tasks: dict[str, asyncio.Task[None]] = {}


async def _owned_creation_session(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> CreationSession:
    session = await db.scalar(
        select(CreationSession).where(CreationSession.id == session_id, CreationSession.user_id == user_id)
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="建书会话不存在")
    return session


async def _latest_creation_artifact(
    db: AsyncSession, session_id: uuid.UUID, artifact_type: str
) -> CreationArtifact | None:
    return await db.scalar(
        select(CreationArtifact)
        .where(CreationArtifact.session_id == session_id, CreationArtifact.artifact_type == artifact_type)
        .order_by(CreationArtifact.version.desc())
        .limit(1)
    )


async def _creation_session_read(db: AsyncSession, session: CreationSession) -> CreationStudioRead:
    directions_artifact = await _latest_creation_artifact(db, session.id, "story_directions")
    research_artifact = await _latest_creation_artifact(db, session.id, "web_research")
    review = await db.scalar(
        select(ViabilityReview)
        .where(ViabilityReview.session_id == session.id)
        .order_by(ViabilityReview.foundation_version.desc())
        .limit(1)
    )
    viability = None
    author_confirmed = False
    error_artifact = await _latest_creation_artifact(db, session.id, "error")
    if review is not None and review.foundation_version == session.foundation_version:
        viability = {
            "verdict": review.verdict,
            "evidence": review.evidence,
            "blocking_issues": review.blocking_issues,
            "warnings": review.warnings,
        }
        author_confirmed = review.author_confirmed
    return CreationStudioRead(
        session_id=session.id,
        state=session.state,
        directions=(directions_artifact.payload.get("directions", []) if directions_artifact else []),
        selected_direction=session.selected_direction or None,
        foundation=session.foundation or None,
        foundation_version=session.foundation_version,
        viability=viability,
        research=research_artifact.payload if research_artifact else None,
        author_confirmed=author_confirmed,
        error=(
            str(error_artifact.payload.get("message") or "")
            if (session.state.startswith("FAILED_") or session.state == "REVIEW_RETRY_REQUIRED")
            and error_artifact
            else None
        ),
    )


async def _record_creation_error(db: AsyncSession, session: CreationSession, phase: str, exc: Exception) -> None:
    existing = await _latest_creation_artifact(db, session.id, "error")
    db.add(CreationArtifact(
        session_id=session.id,
        artifact_type="error",
        version=(existing.version + 1 if existing else 1),
        role=phase,
        payload={"phase": phase, "message": str(exc) or "建书任务失败"},
    ))
    session.state = f"FAILED_{phase.upper()}"
    await db.commit()


async def _record_review_retry_error(
    db: AsyncSession, session: CreationSession, exc: Exception
) -> None:
    existing = await _latest_creation_artifact(db, session.id, "error")
    db.add(CreationArtifact(
        session_id=session.id,
        artifact_type="error",
        version=(existing.version + 1 if existing else 1),
        role="review",
        payload={
            "phase": "review",
            "message": f"故事根基已经保存，仅长篇压力测试暂时未完成：{str(exc) or '模型服务暂时不可用'}",
        },
    ))
    session.state = "REVIEW_RETRY_REQUIRED"
    await db.commit()


async def _run_creation_directions(session_id: uuid.UUID) -> None:
    from app.services.ai_assist import generate_story_directions

    async with SessionLocal() as db:
        session = await db.get(CreationSession, session_id)
        if session is None:
            return
        try:
            directions = await generate_story_directions(session.input_payload)
            db.add(CreationArtifact(
                session_id=session.id,
                artifact_type="story_directions",
                version=1,
                role="story_director",
                payload={"directions": directions},
            ))
            db.add(CreationDecision(
                session_id=session.id,
                decision_type="story_direction",
                options=directions,
            ))
            session.state = "DIRECTIONS_PROPOSED"
            await db.commit()
        except Exception as exc:
            logger.exception("[creation-studio] direction session=%s failed", session_id)
            await db.rollback()
            session = await db.get(CreationSession, session_id)
            if session is not None:
                await _record_creation_error(db, session, "directions", exc)


async def _run_creation_foundation(session_id: uuid.UUID, cards: list[dict[str, Any]]) -> None:
    from app.services.ai_assist import generate_story_foundation, review_story_viability
    from app.services.web_search import WebSearchUnavailable, research_story_material

    async with SessionLocal() as db:
        session = await db.get(CreationSession, session_id)
        if session is None:
            return
        try:
            payload = dict(session.input_payload)
            synthesis = dict(session.selected_direction)
            research_artifact = await _latest_creation_artifact(db, session.id, "web_research")
            research = research_artifact.payload if research_artifact is not None else None
            if research is None:
                session.state = "STORY_RESEARCHING"
                await db.commit()
                try:
                    research = await research_story_material(session.input_payload, synthesis)
                except WebSearchUnavailable as exc:
                    research = {
                        "status": "unavailable",
                        "query": "",
                        "memo": "",
                        "sources": [],
                        "warning": str(exc),
                    }
                db.add(CreationArtifact(
                    session_id=session.id,
                    artifact_type="web_research",
                    version=1,
                    role="research_editor",
                    payload=research,
                ))
                await db.commit()
            pillars = synthesis.get("pillars") if synthesis.get("kind") == "pillar_synthesis" else [synthesis]
            pillar_text = "\n".join(
                f"- {item.get('title', '')}：{item.get('logline', '')}；"
                f"连载发动机：{item.get('serial_engine', '')}；情感线：{item.get('emotional_throughline', '')}；"
                f"代价：{item.get('cost_and_risk', '')}"
                for item in pillars
                if isinstance(item, dict)
            )
            payload["idea"] = (
                f"{payload.get('idea', '')}\n\n作者已经确认以下支柱必须融合为同一本书，不能拆成平行方案，"
                f"必须明确它们之间的因果关系、主次节奏与冲突化解：\n{pillar_text}\n"
                f"作者补充：{synthesis.get('synthesis_note') or '无'}"
            )
            if research.get("status") == "completed":
                source_lines = "\n".join(
                    f"- {item.get('title') or '资料来源'}：{item.get('url') or ''}"
                    for item in research.get("sources", [])[:8]
                    if isinstance(item, dict)
                )
                payload["idea"] += (
                    "\n\n联网题材研究（仅作现实事实参考，不得覆盖作者设定或虚构世界 Canon）：\n"
                    f"{research.get('memo') or ''}\n来源：\n{source_lines}"
                )
            foundation = await generate_story_foundation(payload, cards, scope="full")
            next_version = session.foundation_version + 1
            db.add(CreationArtifact(
                session_id=session.id,
                artifact_type="foundation",
                version=next_version,
                role="longform_architect",
                payload=foundation,
            ))
            session.foundation = foundation
            session.foundation_version = next_version
            session.state = "SERIALIZATION_SIMULATING"
            await db.commit()
            try:
                review_data = await review_story_viability(session.input_payload, synthesis, foundation)
            except Exception as exc:
                logger.exception("[creation-studio] review session=%s failed after foundation saved", session_id)
                await db.rollback()
                session = await db.get(CreationSession, session_id)
                if session is not None:
                    await _record_review_retry_error(db, session, exc)
                return
            db.add(ViabilityReview(
                session_id=session.id,
                foundation_version=next_version,
                verdict=review_data["verdict"],
                evidence=review_data["evidence"],
                blocking_issues=review_data["blocking_issues"],
                warnings=review_data["warnings"],
            ))
            db.add(CreationArtifact(
                session_id=session.id,
                artifact_type="viability_review",
                version=next_version,
                role="reader_editor_and_longform_architect",
                payload=review_data,
            ))
            session.state = "STORY_ENGINE_PROVEN" if review_data["verdict"] == "pass" else "REVIEW_REQUIRED"
            await db.commit()
        except Exception as exc:
            logger.exception("[creation-studio] foundation session=%s failed", session_id)
            await db.rollback()
            session = await db.get(CreationSession, session_id)
            if session is not None:
                await _record_creation_error(db, session, "foundation", exc)


async def _run_creation_review(
    session_id: uuid.UUID, foundation: dict[str, Any], author_note: str = ""
) -> None:
    from app.services.ai_assist import review_story_viability

    async with SessionLocal() as db:
        session = await db.get(CreationSession, session_id)
        if session is None:
            return
        try:
            review_payload = dict(session.input_payload)
            if author_note.strip():
                review_payload["idea"] = (
                    f"{review_payload.get('idea', '')}\n\n作者针对本轮修订的说明：{author_note.strip()}"
                )
            review_data = await review_story_viability(review_payload, session.selected_direction, foundation)
            db.add(ViabilityReview(
                session_id=session.id,
                foundation_version=session.foundation_version,
                verdict=review_data["verdict"],
                evidence=review_data["evidence"],
                blocking_issues=review_data["blocking_issues"],
                warnings=review_data["warnings"],
            ))
            session.state = "STORY_ENGINE_PROVEN" if review_data["verdict"] == "pass" else "REVIEW_REQUIRED"
            await db.commit()
        except Exception as exc:
            logger.exception("[creation-studio] review session=%s failed", session_id)
            await db.rollback()
            session = await db.get(CreationSession, session_id)
            if session is not None:
                await _record_review_retry_error(db, session, exc)


def _track_creation_task(session_id: uuid.UUID, task: asyncio.Task[None]) -> None:
    key = str(session_id)
    _creation_tasks[key] = task
    task.add_done_callback(lambda _done: _creation_tasks.pop(key, None))


@router.post(
    "/creation-studio/sessions",
    response_model=CreationStudioRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_creation_studio(
    payload: CreationStudioStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreationStudioRead:
    session = CreationSession(
        user_id=current_user.id,
        state="RAW_IDEA",
        input_payload=payload.model_dump(mode="json"),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    _track_creation_task(session.id, asyncio.create_task(_run_creation_directions(session.id)))
    return await _creation_session_read(db, session)


@router.get("/creation-studio/sessions/{session_id}", response_model=CreationStudioRead)
async def get_creation_studio(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreationStudioRead:
    session = await _owned_creation_session(db, session_id, current_user.id)
    if str(session.id) not in _creation_tasks:
        if session.state == "RAW_IDEA":
            _track_creation_task(session.id, asyncio.create_task(_run_creation_directions(session.id)))
        elif session.state in {"DIRECTION_SELECTED", "STORY_RESEARCHING"}:
            cards = await _foundation_cards(db, CreationFoundationRequest.model_validate(session.input_payload))
            _track_creation_task(session.id, asyncio.create_task(_run_creation_foundation(session.id, cards)))
        elif session.state == "SERIALIZATION_SIMULATING":
            candidate = await _latest_creation_artifact(db, session.id, "foundation_candidate")
            candidate_foundation = (
                candidate.payload.get("foundation", candidate.payload)
                if candidate is not None
                else session.foundation
            )
            if candidate_foundation:
                _track_creation_task(
                    session.id,
                    asyncio.create_task(_run_creation_review(
                        session.id,
                        candidate_foundation,
                        str(candidate.payload.get("author_note") or "") if candidate is not None else "",
                    )),
                )
    return await _creation_session_read(db, session)


@router.post(
    "/creation-studio/sessions/{session_id}/directions",
    response_model=CreationStudioRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_creation_directions(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreationStudioRead:
    session = await _owned_creation_session(db, session_id, current_user.id)
    if str(session.id) in _creation_tasks:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="建书方向仍在生成")
    session.state = "RAW_IDEA"
    await db.commit()
    _track_creation_task(session.id, asyncio.create_task(_run_creation_directions(session.id)))
    return await _creation_session_read(db, session)


@router.post(
    "/creation-studio/sessions/{session_id}/direction",
    response_model=CreationStudioRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def select_creation_direction(
    session_id: uuid.UUID,
    payload: CreationDirectionSelectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreationStudioRead:
    session = await _owned_creation_session(db, session_id, current_user.id)
    directions_artifact = await _latest_creation_artifact(db, session.id, "story_directions")
    directions = directions_artifact.payload.get("directions", []) if directions_artifact else []
    selected_indices = payload.selected_indices
    if (
        session.state != "DIRECTIONS_PROPOSED"
        or any(index >= len(directions) for index in selected_indices)
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先生成并选择有效的创作支柱")
    decision = await db.scalar(
        select(CreationDecision)
        .where(CreationDecision.session_id == session.id, CreationDecision.decision_type == "story_direction")
        .order_by(CreationDecision.created_at.desc())
        .limit(1)
    )
    primary_index = payload.primary_index if payload.primary_index is not None else selected_indices[0]
    chosen_pillars = [directions[index] for index in selected_indices]
    synthesis = {
        "kind": "pillar_synthesis",
        "pillars": chosen_pillars,
        "primary_keys": [directions[primary_index]["key"]],
        "synthesis_note": payload.user_note or "",
    }
    if decision is not None:
        decision.chosen_index = primary_index
        decision.chosen_payload = synthesis
        decision.user_note = payload.user_note
        decision.confirmed_at = datetime.now(UTC)
    session.selected_direction = synthesis
    session.state = "DIRECTION_SELECTED"
    await db.commit()
    cards = await _foundation_cards(db, CreationFoundationRequest.model_validate(session.input_payload))
    _track_creation_task(session.id, asyncio.create_task(_run_creation_foundation(session.id, cards)))
    return await _creation_session_read(db, session)


@router.post(
    "/creation-studio/sessions/{session_id}/review",
    response_model=CreationStudioRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rerun_creation_review(
    session_id: uuid.UUID,
    payload: CreationStudioConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreationStudioRead:
    session = await _owned_creation_session(db, session_id, current_user.id)
    if not session.selected_direction:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="尚未选择建书方向")
    if str(session.id) in _creation_tasks:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="建书任务仍在运行")
    candidate = await _latest_creation_artifact(db, session.id, "foundation_candidate")
    next_version = session.foundation_version + 1
    db.add(CreationArtifact(
        session_id=session.id,
        artifact_type="foundation_candidate",
        version=(candidate.version + 1 if candidate else 1),
        role="author",
        payload={"foundation": payload.foundation.model_dump(), "author_note": payload.author_note or ""},
    ))
    db.add(CreationArtifact(
        session_id=session.id,
        artifact_type="foundation",
        version=next_version,
        role="author_and_longform_architect",
        payload=payload.foundation.model_dump(),
    ))
    session.foundation = payload.foundation.model_dump()
    session.foundation_version = next_version
    session.state = "SERIALIZATION_SIMULATING"
    await db.commit()
    _track_creation_task(
        session.id,
        asyncio.create_task(_run_creation_review(
            session.id, payload.foundation.model_dump(), payload.author_note or ""
        )),
    )
    return await _creation_session_read(db, session)


@router.post("/creation-studio/sessions/{session_id}/confirm", response_model=CreationStudioRead)
async def confirm_creation_studio(
    session_id: uuid.UUID,
    payload: CreationStudioConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreationStudioRead:
    session = await _owned_creation_session(db, session_id, current_user.id)
    if payload.foundation.model_dump() != session.foundation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="故事根基已修改，请先重新进行长篇压力测试")
    review = await db.scalar(
        select(ViabilityReview).where(
            ViabilityReview.session_id == session.id,
            ViabilityReview.foundation_version == session.foundation_version,
        )
    )
    if review is None or review.verdict != "pass" or review.blocking_issues:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="长篇可行性尚未通过，不能生成第一章")
    review.author_confirmed = True
    session.state = "OPENING_STRATEGY_CONFIRMED"
    await db.commit()
    return await _creation_session_read(db, session)


def _trim_foundation_jobs() -> None:
    completed = [
        job_id for job_id, job in _foundation_jobs.items() if job.get("status") in {"completed", "failed"}
    ]
    while len(_foundation_jobs) > _FOUNDATION_JOB_LIMIT and completed:
        _foundation_jobs.pop(completed.pop(0), None)


def _trim_pilot_jobs() -> None:
    completed = [
        job_id for job_id, job in _pilot_jobs.items() if job.get("status") in {"completed", "failed"}
    ]
    while len(_pilot_jobs) > _PILOT_JOB_LIMIT and completed:
        _pilot_jobs.pop(completed.pop(0), None)


async def _run_pilot_job(
    job_id: str,
    payload: dict[str, Any],
    cards: list[dict[str, Any]],
) -> None:
    from app.services.ai_assist import generate_opening_pilot

    job = _pilot_jobs[job_id]
    job.update({"status": "running", "phase": "正在规划第一章的连续场景"})
    try:
        pilot = await asyncio.wait_for(
            generate_opening_pilot(
                payload["foundation"],
                cards,
                author_note=payload.get("author_note") or "",
                style_reference=payload.get("style_reference") or "",
            ),
            timeout=330,
        )
    except TimeoutError:
        job.update({"status": "failed", "error": "第一章生成超过5分钟，已停止本次任务，请重试"})
    except Exception as exc:
        logger.exception("[pilot-job] job=%s 失败", job_id)
        job.update({"status": "failed", "error": str(exc) or "第一章生成失败"})
    else:
        job.update({
            "status": "completed",
            "pilot": {
                **pilot,
                "method_cards": [str(card.get("title") or "写作方法") for card in cards],
            },
            "phase": "第一章已完成",
        })
        session_value = payload.get("creation_session_id")
        if session_value:
            async with SessionLocal() as db:
                session = await db.get(CreationSession, uuid.UUID(str(session_value)))
                if session is not None:
                    previous = await _latest_creation_artifact(db, session.id, "opening_pilot")
                    db.add(CreationArtifact(
                        session_id=session.id,
                        artifact_type="opening_pilot",
                        version=(previous.version + 1 if previous else 1),
                        role="lead_writer",
                        payload=job["pilot"],
                    ))
                    session.state = "PILOT_GENERATED"
                    await db.commit()
    finally:
        _pilot_jobs.move_to_end(job_id)
        _trim_pilot_jobs()


async def _run_foundation_job(
    job_id: str,
    payload: dict[str, Any],
    cards: list[dict[str, Any]],
    scope: str = "core",
) -> None:
    from app.services.ai_assist import generate_story_foundation

    job = _foundation_jobs[job_id]
    job["status"] = "running"
    try:
        foundation = await generate_story_foundation(payload, cards, scope=scope)
    except Exception as exc:  # The polling endpoint must preserve the real generation failure.
        import traceback
        tb = traceback.format_exc()
        logger.error("[foundation-job] job=%s 失败: %s\n%s", job_id, exc, tb)
        job.update({"status": "failed", "error": str(exc) or "故事根基生成失败"})
    else:
        job.update(
            {
                "status": "completed",
                "foundation": foundation,
                "scope": scope,
                "method_cards": [str(card.get("title") or "写作方法") for card in cards],
            }
        )
    finally:
        _foundation_jobs.move_to_end(job_id)
        _trim_foundation_jobs()


async def _foundation_cards(db: AsyncSession, payload: CreationFoundationRequest) -> list[dict[str, Any]]:
    from app.engine.retrieval import writing_method_card_search

    genre = " ".join(payload.genres) or payload.genre or "小说"
    query = f"{genre} 百万字 长篇 分卷 开篇三万字 读者代入 期待感 小剧情 节奏"
    tags = ["长篇", "人物", "情节", "大纲", "开篇", "节奏", "代入感"]
    tags.extend(item for item in ("男频", "女频", "玄幻", "言情", "悬疑") if item in f"{payload.channel}{genre}")
    return await writing_method_card_search(db, query, tags=tags, limit=4)


@router.post("/creation-v2/foundation", response_model=CreationFoundationResponse)
async def creation_foundation(
    payload: CreationFoundationRequest,
    scope: str = "core",  # "core" 表示渐进式初次建模；"full" 表示一次性完整建模
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreationFoundationResponse:
    del current_user
    from app.services.ai_assist import generate_story_foundation

    if scope not in {"core", "full"}:
        scope = "core"
    cards = await _foundation_cards(db, payload)
    try:
        foundation = await generate_story_foundation(payload.model_dump(), cards, scope=scope)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return CreationFoundationResponse(
        foundation=foundation,
        method_cards=[str(card.get("title") or "写作方法") for card in cards],
    )


@router.post("/creation-v2/foundation/start", status_code=status.HTTP_202_ACCEPTED)
async def start_creation_foundation(
    payload: CreationFoundationRequest,
    scope: str = "core",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    cards = await _foundation_cards(db, payload)
    job_id = str(uuid.uuid4())
    final_scope = scope if scope in {"core", "full"} else "core"
    _foundation_jobs[job_id] = {
        "status": "queued",
        "user_id": str(current_user.id),
        "scope": final_scope,
    }
    task = asyncio.create_task(_run_foundation_job(job_id, payload.model_dump(), cards, final_scope))
    _foundation_tasks[job_id] = task
    task.add_done_callback(lambda _completed: _foundation_tasks.pop(job_id, None))
    return {"task_id": job_id, "status": "queued"}


@router.get("/creation-v2/foundation/{job_id}")
async def creation_foundation_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    job = _foundation_jobs.get(job_id)
    if job is None or job.get("user_id") != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="创建任务不存在或已经过期")
    _foundation_jobs.move_to_end(job_id)
    return {key: value for key, value in job.items() if key != "user_id"}


@router.post("/creation-v2/foundation/section", response_model=FoundationSectionResponse)
async def create_foundation_section(
    payload: FoundationSectionRequest,
    current_user: User = Depends(get_current_user),
) -> FoundationSectionResponse:
    """基于现有 foundation，补全指定的那一节。每节独立重试与失败感知。"""
    del current_user
    from app.services.ai_assist import generate_foundation_section

    try:
        result = await generate_foundation_section(payload.model_dump(), payload.section)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return FoundationSectionResponse(**result)


@router.post("/creation-v2/pilot", response_model=OpeningPilotResponse)
async def creation_pilot(
    payload: OpeningPilotRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OpeningPilotResponse:
    from app.engine.retrieval import writing_method_card_search
    from app.services.ai_assist import generate_opening_pilot

    if payload.creation_session_id:
        session = await _owned_creation_session(db, payload.creation_session_id, current_user.id)
        if session.state not in {"OPENING_STRATEGY_CONFIRMED", "PILOT_GENERATED", "PILOT_FAILED"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="建书尚未通过长篇可行性门槛")

    genre = payload.foundation.engine.primary_genre
    cards = await writing_method_card_search(
        db,
        f"{genre} 开篇 代入感 场景因果 对话 人物刻画 文笔",
        tags=["开篇", "代入感", "场景", "对话", "人物"],
        limit=4,
    )
    try:
        pilot = await generate_opening_pilot(
            payload.foundation.model_dump(),
            cards,
            author_note=payload.author_note or "",
            style_reference=payload.style_reference or "",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return OpeningPilotResponse(
        **pilot,
        method_cards=[str(card.get("title") or "写作方法") for card in cards],
    )


@router.post("/creation-v2/pilot/start", status_code=status.HTTP_202_ACCEPTED)
async def start_creation_pilot(
    payload: OpeningPilotRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    from app.engine.retrieval import writing_method_card_search

    if payload.creation_session_id:
        session = await _owned_creation_session(db, payload.creation_session_id, current_user.id)
        if session.state not in {"OPENING_STRATEGY_CONFIRMED", "PILOT_GENERATED", "PILOT_FAILED"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="建书尚未通过长篇可行性门槛")
        if payload.foundation.model_dump() != session.foundation:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="故事根基版本不一致，请重新确认")

    genre = payload.foundation.engine.primary_genre
    cards = await writing_method_card_search(
        db,
        f"{genre} 开篇 代入感 场景因果 对话 人物刻画 文笔",
        tags=["开篇", "代入感", "场景", "对话", "人物"],
        limit=4,
    )
    job_id = str(uuid.uuid4())
    _pilot_jobs[job_id] = {
        "status": "queued",
        "phase": "等待生成第一章",
        "user_id": str(current_user.id),
    }
    task = asyncio.create_task(_run_pilot_job(job_id, payload.model_dump(), cards))
    _pilot_tasks[job_id] = task
    task.add_done_callback(lambda _completed: _pilot_tasks.pop(job_id, None))
    return {"task_id": job_id, "status": "queued"}


@router.get("/creation-v2/pilot/task/{job_id}")
async def creation_pilot_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    job = _pilot_jobs.get(job_id)
    if job is None or job.get("user_id") != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="第一章任务不存在或已经过期")
    _pilot_jobs.move_to_end(job_id)
    return {key: value for key, value in job.items() if key != "user_id"}


@router.post("/world-engine", response_model=WorldEngineResponse)
async def world_engine(
    payload: WorldEngineRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorldEngineResponse:
    """用写作指导 RAG 建立项目专属世界包，并执行阻断级压力测试。"""
    del current_user
    from app.engine.retrieval import writing_guide_search, writing_method_card_search
    from app.engine.worldbuilder import validate_world_engine
    from app.services.ai_assist import generate_world_engine

    tags = ["世界观", "人物", "情节"]
    tags.extend(value for value in ("玄幻", "言情", "悬疑") if value in payload.genre)
    query = f"{payload.genre} 世界观 世界规则 升级 人物主动行为 冲突 代价"
    cards = await writing_method_card_search(db, query, tags=tags, limit=4)
    excerpts = await writing_guide_search(db, query, tags=tags, limit=4)
    context = [*cards, *excerpts]
    try:
        world = await generate_world_engine(payload.model_dump(), context)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    issues = validate_world_engine(world, payload.genre, strict=True)
    sources = [
        {
            "title": str(item.get("title") or item.get("source_title") or "写作指导"),
            "kind": "method_card" if item.get("card_id") else "source_excerpt",
        }
        for item in context
    ]
    return WorldEngineResponse(
        world_engine=world,
        validation={"status": "pass" if not issues else "review_required", "blocking_issues": issues},
        research_sources=sources,
    )

StorySeedData = list[dict[str, str]]
StorySeedTaskKey = tuple[str, str]
_story_seed_tasks: dict[StorySeedTaskKey, asyncio.Task[StorySeedData]] = {}
_story_seed_results: OrderedDict[StorySeedTaskKey, StorySeedData] = OrderedDict()
_STORY_SEED_RESULT_LIMIT = 50


async def _run_story_seed_task(
    key: StorySeedTaskKey | None,
    factory: Callable[[], Awaitable[StorySeedData]],
) -> StorySeedData:
    if key is None:
        return await factory()
    cached = _story_seed_results.get(key)
    if cached is not None:
        _story_seed_results.move_to_end(key)
        return cached

    task = _story_seed_tasks.get(key)
    if task is None:
        task = asyncio.create_task(factory())
        _story_seed_tasks[key] = task

        def remember_result(completed: asyncio.Task[StorySeedData]) -> None:
            _story_seed_tasks.pop(key, None)
            if completed.cancelled() or completed.exception() is not None:
                return
            _story_seed_results[key] = completed.result()
            _story_seed_results.move_to_end(key)
            while len(_story_seed_results) > _STORY_SEED_RESULT_LIMIT:
                _story_seed_results.popitem(last=False)

        task.add_done_callback(remember_result)
    return await asyncio.shield(task)


@router.post("/taste-match", response_model=TasteMatchResponse)
async def taste_match(
    payload: TasteMatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TasteMatchResponse:
    from app.services.ai_assist import match_taste_to_tracks

    tracks, commentary = await match_taste_to_tracks(
        db,
        taste_tags=payload.taste_tags,
        channel=payload.channel,
        feeling=payload.feeling,
        reader_wish=payload.reader_wish,
        primary_category=payload.primary_category,
        primary_categories=payload.primary_categories,
        favorite_works=payload.favorite_works,
        avoid_elements=payload.avoid_elements,
        target_words=payload.target_words,
    )
    from app.schemas import MarketTrackRead

    return TasteMatchResponse(
        tracks=[MarketTrackRead.model_validate(t) for t in tracks],
        ai_commentary=commentary,
    )


@router.post("/story-seeds", response_model=StorySeedResponse)
async def story_seeds(
    payload: StorySeedRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StorySeedResponse:
    from app.services.ai_assist import generate_story_seeds

    async def generate() -> StorySeedData:
        return await generate_story_seeds(
                taste_tags=payload.taste_tags,
                channel=payload.channel,
                reader_wish=payload.reader_wish,
                primary_category=payload.primary_category,
                primary_categories=payload.primary_categories,
                favorite_works=payload.favorite_works,
                avoid_elements=payload.avoid_elements,
                style_description=payload.style_description,
                author_intent=payload.author_intent,
                world_engine=payload.world_engine,
                target_words=payload.target_words,
                count=payload.count,
            )

    task_key = (str(current_user.id), str(payload.request_id)) if payload.request_id else None
    try:
        seeds = await _run_story_seed_task(task_key, generate)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return StorySeedResponse(seeds=[StorySeed(**s) for s in seeds])


@router.post("/style-polish", response_model=StylePolishResponse)
async def style_polish(
    payload: StylePolishRequest,
    current_user: User = Depends(get_current_user),
) -> StylePolishResponse:
    from app.services.ai_assist import polish_style_description

    return StylePolishResponse(description=await polish_style_description(payload.description, payload.genre))


@router.post("/style-analyze")
async def style_analyze(
    payload: StyleAnalyzeRequest,
    current_user: User = Depends(get_current_user),
) -> EventSourceResponse:
    """流式拆解用户上传的参考小说，逐段输出文笔/世界观分析。"""
    import json as json_module

    from app.services.ai_assist import (
        STYLE_ANALYZE_SYSTEM_PROMPT,
        build_style_analyze_prompt,
    )
    from app.services.llm_client import llm_client

    prompt = build_style_analyze_prompt(payload.title, payload.text, payload.genre, payload.focus)

    async def event_generator():
        try:
            async for chunk in llm_client.stream(STYLE_ANALYZE_SYSTEM_PROMPT, prompt):
                yield {"event": "chunk", "data": json_module.dumps({"text": chunk}, ensure_ascii=False)}
            yield {"event": "done", "data": "{}"}
        except Exception as exc:  # noqa: BLE001 - 需要把错误实时推给前端
            yield {"event": "error", "data": json_module.dumps({"message": str(exc) or "分析失败"}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@router.post("/story-refine", response_model=StorySeed)
async def story_refine(
    payload: StoryRefineRequest,
    current_user: User = Depends(get_current_user),
) -> StorySeed:
    from app.services.ai_assist import refine_story_seed

    try:
        refined = await refine_story_seed(seed=payload.seed.model_dump(), adjustments=payload.adjustments)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return StorySeed(**refined)


@router.post("/lazy-generate")
async def lazy_generate(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.ai_assist import generate_lazy_project

    try:
        return await generate_lazy_project(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/chapter-directions")
async def chapter_directions(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sqlalchemy import select

    from app.models import Chapter, Project
    from app.services.ai_assist import generate_chapter_directions

    project_id = payload.get("project_id")
    chapter_sequence = payload.get("chapter_sequence", 1)
    if not project_id:
        raise HTTPException(status_code=422, detail="project_id is required")

    project = await db.scalar(
        select(Project).where(Project.id == uuid.UUID(str(project_id)), Project.user_id == current_user.id)
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    prev_chapter = await db.scalar(
        select(Chapter).where(
            Chapter.project_id == project.id,
            Chapter.chapter_sequence == chapter_sequence - 1,
            Chapter.status.in_(["draft", "confirmed"]),
        )
    )
    content = prev_chapter.content if prev_chapter else ""
    summary = prev_chapter.summary if prev_chapter else project.one_sentence

    directions = await generate_chapter_directions(content, summary, project.genre)
    return {"directions": directions}


@router.post("/volume-plan")
async def volume_plan(
    payload: dict,
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.services.ai_assist import generate_volume_plan

    try:
        return await generate_volume_plan(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/book-blueprint")
async def book_blueprint(
    payload: BookBlueprintRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.services.ai_assist import generate_book_blueprint

    try:
        return await generate_book_blueprint(payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/character-cast")
async def character_cast(
    payload: CharacterCastRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.services.ai_assist import generate_character_cast

    try:
        return await generate_character_cast(payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/stuck-help")
async def stuck_help(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sqlalchemy import select

    from app.models import Chapter, Project
    from app.services.ai_assist import generate_stuck_help

    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    latest = await db.scalar(
        select(Chapter)
        .where(Chapter.project_id == project_id, Chapter.status.in_(["draft", "confirmed"]))
        .order_by(Chapter.chapter_sequence.desc())
        .limit(1)
    )
    content = latest.content if latest else ""
    summary = latest.summary if latest else project.one_sentence

    return await generate_stuck_help(content, summary, project.genre)
