from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    ImportedChapter,
    ImportedWork,
    Project,
    User,
    WorkCodexEntry,
)
from app.schemas import (
    ContinuationRequest,
    FanficRequest,
    ImportedWorkCreate,
    ImportedWorkRead,
    ImportedWorkReport,
    ProjectCreate,
    ProjectRead,
)
from app.services.auth import get_current_user
from app.utils.canonical import parse_json_object

router = APIRouter(prefix="/imported-works", tags=["imports"])

EXTERNAL_ANALYSIS_PROMPT = """你是长篇小说逆向工程师。请分析我上传的小说，最终只输出一个 JSON 对象，
不要 Markdown 代码块、不要分析过程。无法确认的内容用空字符串或空数组，不要编造章节号。

输出结构：
{
  "metadata":{"title":"书名","author":"作者","genre":"类型","total_chapters":0,"total_words":0},
  "book":{"premise":"一句话核心","main_goal":"终极目标","ending_state":"结局状态","main_arc_upgrades":["主线升级节点"]},
  "volumes":[{"sequence":1,"title":"卷名","chapter_range":[1,100],"goal":"阶段目标","conflict":"核心冲突","ending_hook":"卷末钩子"}],
  "arcs":[{"volume_sequence":1,"sequence":1,"title":"事件弧","chapter_range":[1,10],"goal":"目标","conflict":"冲突","climax":"高潮","resolution":"收束"}],
  "characters":[{"name":"姓名","role":"剧情功能","faction":"阵营","first_chapter":1,"last_chapter":null,"desire":"核心欲望","fear":"核心恐惧","personality":["标签"],"relationship_changes":["关系变化"],"secret":"隐藏秘密","ending_state":"最终状态"}],
  "world_rules":[{"title":"规则名","content":"规则及限制"}],
  "foreshadowing":[{"content":"伏笔","planted_chapter":1,"target_chapter":100,"importance":"A|B|C","disguise":"埋设时的伪装","status":"active|resolved"}],
  "style_profile":{"pov_style":"叙事视角","tone_keywords":["基调"],"rhythm":"节奏","dialogue_ratio":"对话占比","sentence_style":"句式","hook_mix":{"suspense":0.4,"danger":0.2,"reveal":0.2,"emotion":0.2}},
  "breakpoint_analysis":{"main_arc_stage":"原作终点所处主线阶段","unresolved_promises":["未兑现承诺"],"suggested_directions":[{"title":"方向","description":"续写方向"}]}
}

要求：卷→事件弧→章区间必须连续、人物关系变化要写触发事件、伏笔必须写伪装形态和状态；
若全文太长，请分卷分析，最后把各批结果合并成以上单一 JSON 再输出。"""


class ExternalAnalysisImport(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str | None = Field(default=None, max_length=200)
    analysis_text: str = Field(min_length=20)


class CodexEntryUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    content: dict[str, Any] | None = None
    user_verified: bool | None = None


@router.get("/external-analysis-prompt")
async def get_external_analysis_prompt(current_user: User = Depends(get_current_user)) -> dict[str, str]:
    """供用户复制到免费网页端 AI 的固定机器可读逆向提示词。"""
    return {"prompt": EXTERNAL_ANALYSIS_PROMPT}


@router.post("/external-analysis", response_model=ImportedWorkRead, status_code=status.HTTP_201_CREATED)
async def import_external_analysis(
    payload: ExternalAnalysisImport,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportedWorkRead:
    """接收免费网页端 AI 的 JSON 结果，校验并归一化为项目自己的拆书数据。"""
    try:
        data = parse_json_object(payload.analysis_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="没有识别到完整 JSON，请让网页端 AI 只输出一个 JSON 对象") from exc

    required = ["volumes", "characters", "style_profile"]
    missing = [key for key in required if not isinstance(data.get(key), list if key != "style_profile" else dict)]
    if missing:
        raise HTTPException(status_code=422, detail=f"逆向结果缺少字段：{', '.join(missing)}；请用提示词补充后重试")

    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    characters = [
        {
            "slug": f"character-{index}",
            "category": "character",
            "title": str(item.get("name") or f"人物{index}"),
            "content": "\n".join(
                f"- {label}：{value}"
                for label, value in [
                    ("剧情功能", item.get("role")), ("阵营", item.get("faction")),
                    ("核心欲望", item.get("desire")), ("核心恐惧", item.get("fear")),
                    ("隐藏秘密", item.get("secret")), ("最终状态", item.get("ending_state")),
                ]
                if value
            ),
            "raw": item,
        }
        for index, item in enumerate(data.get("characters", []), start=1)
        if isinstance(item, dict)
    ]
    world_rules = [
        {
            "slug": f"world-rule-{index}", "category": "worldview",
            "title": str(item.get("title") or f"世界规则{index}"),
            "content": str(item.get("content") or ""), "raw": item,
        }
        for index, item in enumerate(data.get("world_rules", []), start=1)
        if isinstance(item, dict)
    ]
    foreshadowing: list[dict[str, Any]] = [
        {**item, "status": item.get("status") or "active"}
        for item in data.get("foreshadowing", [])
        if isinstance(item, dict)
    ]
    work = ImportedWork(
        user_id=current_user.id,
        title=payload.title,
        author=payload.author,
        source_platform="external-free-ai",
        genre=str(metadata.get("genre") or "其他"),
        total_chapters=int(metadata.get("total_chapters") or 0),
        total_words=int(metadata.get("total_words") or 0),
        analysis_status="completed",
        analysis_progress=100,
        extracted_data={
            "book": data.get("book", {}), "volumes": data["volumes"], "arcs": data.get("arcs", []),
            "characters": characters, "world_rules": world_rules, "foreshadowing": foreshadowing,
        },
        style_profile=data["style_profile"],
        breakpoint_analysis=data.get("breakpoint_analysis", {}),
    )
    db.add(work)
    await db.flush()
    from app.engine.analyzer import _rebuild_work_codex

    await _rebuild_work_codex(db, work, [])
    await db.commit()
    await db.refresh(work)
    return ImportedWorkRead.model_validate(work)


@router.get("", response_model=list[ImportedWorkRead])
async def list_imported_works(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ImportedWorkRead]:
    works = list(
        (
            await db.scalars(
                select(ImportedWork)
                .where(ImportedWork.user_id == current_user.id)
                .order_by(ImportedWork.created_at.desc())
            )
        ).all()
    )
    return [ImportedWorkRead.model_validate(w) for w in works]


@router.post("", response_model=ImportedWorkRead, status_code=status.HTTP_201_CREATED)
async def create_imported_work(
    payload: ImportedWorkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportedWorkRead:
    from app.services.import_service import create_import

    work = await create_import(
        db,
        user_id=current_user.id,
        title=payload.title,
        raw_content=payload.content,
        author=payload.author,
        source_platform=payload.source_platform,
    )
    return ImportedWorkRead.model_validate(work)


@router.get("/{work_id}", response_model=ImportedWorkRead)
async def get_imported_work(
    work_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportedWorkRead:
    work = await db.scalar(
        select(ImportedWork).where(ImportedWork.id == work_id, ImportedWork.user_id == current_user.id)
    )
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入作品不存在")
    return ImportedWorkRead.model_validate(work)


@router.get("/{work_id}/status")
async def get_analysis_status(
    work_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    work = await db.scalar(
        select(ImportedWork).where(ImportedWork.id == work_id, ImportedWork.user_id == current_user.id)
    )
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入作品不存在")
    completed_chapters = await db.scalar(
        select(func.count())
        .select_from(ImportedChapter)
        .where(
            ImportedChapter.work_id == work_id,
            ImportedChapter.analysis_status == "completed",
        )
    )
    raw_progress = float(work.analysis_progress or 0)
    if work.analysis_status == "completed":
        progress = 100.0
    elif 0 < raw_progress <= 1:
        progress = raw_progress * 100
    else:
        progress = raw_progress
    return {
        "analysis_status": work.analysis_status,
        "analysis_progress": round(min(max(progress, 0), 100), 2),
        "total_chapters": work.total_chapters,
        "completed_chapters": int(completed_chapters or 0),
        "total_words": work.total_words,
        "attempt": work.analysis_attempt,
        "error": work.analysis_error,
    }


@router.post("/{work_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_analysis(
    work_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    work = await db.scalar(
        select(ImportedWork).where(ImportedWork.id == work_id, ImportedWork.user_id == current_user.id)
    )
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入作品不存在")
    if work.analysis_status not in {"failed", "pending"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前状态不能重试")
    work.analysis_status = "pending"
    work.analysis_attempt = 0
    work.analysis_progress = 0
    work.analysis_claim_token = None
    work.analysis_error = None
    await db.commit()
    return {"status": "pending"}


@router.get("/{work_id}/codex")
async def list_codex_entries(
    work_id: uuid.UUID,
    layer: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    work = await db.scalar(
        select(ImportedWork.id).where(ImportedWork.id == work_id, ImportedWork.user_id == current_user.id)
    )
    if work is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入作品不存在")
    query = select(WorkCodexEntry).where(WorkCodexEntry.imported_work_id == work_id)
    if layer:
        query = query.where(WorkCodexEntry.layer == layer)
    rows = list((await db.scalars(query.order_by(WorkCodexEntry.layer, WorkCodexEntry.created_at))).all())
    return {
        "entries": [
            {
                "id": str(row.id),
                "layer": row.layer,
                "kind": row.kind,
                "title": row.title,
                "content": row.content,
                "confidence": row.confidence,
                "user_verified": row.user_verified,
                "source_chapter_ids": [str(value) for value in row.source_chapter_ids],
            }
            for row in rows
        ]
    }


@router.patch("/{work_id}/codex/{entry_id}")
async def update_codex_entry(
    work_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: CodexEntryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await db.scalar(
        select(WorkCodexEntry)
        .join(ImportedWork, ImportedWork.id == WorkCodexEntry.imported_work_id)
        .where(
            WorkCodexEntry.id == entry_id,
            WorkCodexEntry.imported_work_id == work_id,
            ImportedWork.user_id == current_user.id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识条目不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    if payload.content is not None and payload.user_verified is None:
        row.user_verified = True
    await db.commit()
    return {"id": str(row.id), "updated": True}


@router.delete("/{work_id}/codex/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_codex_entry(
    work_id: uuid.UUID,
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = await db.scalar(
        select(WorkCodexEntry)
        .join(ImportedWork, ImportedWork.id == WorkCodexEntry.imported_work_id)
        .where(
            WorkCodexEntry.id == entry_id,
            WorkCodexEntry.imported_work_id == work_id,
            ImportedWork.user_id == current_user.id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识条目不存在")
    await db.delete(row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{work_id}/report", response_model=ImportedWorkReport)
async def get_analysis_report(
    work_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportedWorkReport:
    work = await db.scalar(
        select(ImportedWork).where(ImportedWork.id == work_id, ImportedWork.user_id == current_user.id)
    )
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入作品不存在")
    if work.analysis_status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="分析尚未完成")

    extracted = work.extracted_data or {}
    characters = extracted.get("characters", [])
    world_rules = extracted.get("world_rules", [])
    foreshadowing = extracted.get("foreshadowing", [])

    power_system = None
    for rule in world_rules:
        content = rule.get("content", "")
        if "力量" in content or "修炼" in content:
            power_system = {"title": rule.get("title", ""), "content": content}
            break

    style_summary = None
    if work.style_profile:
        sp = work.style_profile
        tone = "、".join(sp.get("tone_keywords", [])[:5])
        rhythm = sp.get("rhythm", "未知")
        pov = sp.get("pov_style", "未知")
        style_summary = f"视角：{pov}，节奏：{rhythm}，基调：{tone}"

    breakpoint = work.breakpoint_analysis or {}
    thrill_formula = breakpoint.get("main_arc_stage")

    return ImportedWorkReport(
        work=ImportedWorkRead.model_validate(work),
        characters=characters,
        world_rules=world_rules,
        foreshadowing=foreshadowing,
        power_system=power_system,
        thrill_formula=thrill_formula,
        style_summary=style_summary,
    )


@router.post("/{work_id}/continue", response_model=ProjectRead)
async def create_continuation(
    work_id: uuid.UUID,
    payload: ContinuationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="续写现在必须从新书向导创建")
    work = await db.scalar(
        select(ImportedWork).where(ImportedWork.id == work_id, ImportedWork.user_id == current_user.id)
    )
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入作品不存在")
    if work.analysis_status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="分析尚未完成")

    breakpoint = work.breakpoint_analysis or {}
    directions = breakpoint.get("suggested_directions", [])
    strategy_map = {"faithful": 0, "accelerate": 1, "diverge": 2}
    idx = strategy_map.get(payload.strategy, 0)
    direction = directions[idx] if idx < len(directions) else {}

    one_sentence = direction.get("description", f"续写《{work.title}》")
    extracted = work.extracted_data or {}
    protagonist_name = "主角"
    chars = extracted.get("characters", [])
    if chars:
        protagonist_name = chars[0].get("title", "主角")

    fallback_sentence = f"续写小说《{work.title}》的故事"
    project_payload = ProjectCreate(
        title=f"续·{work.title}"[:200],
        genre=work.genre or "其他",
        one_sentence=one_sentence[:2000] if len(one_sentence) >= 10 else fallback_sentence,
        protagonist_name=protagonist_name,
        protagonist_gender="男",
        protagonist_personality="延续原作角色设定",
        target_words=payload.target_words,
        creation_mode="continuation",
        source_work_id=work.id,
    )

    from app.services.project_bootstrap import seed_new_project

    project = Project(
        user_id=current_user.id,
        title=project_payload.title,
        genre=project_payload.genre,
        one_sentence=project_payload.one_sentence,
        protagonist_name=project_payload.protagonist_name,
        protagonist_gender=project_payload.protagonist_gender,
        protagonist_personality=project_payload.protagonist_personality,
        target_words=project_payload.target_words,
        creation_mode="continuation",
        source_work_id=work.id,
    )
    db.add(project)
    await db.flush()

    await seed_new_project(db, project, project_payload)
    from app.services.imported_project import materialize_imported_assets

    await materialize_imported_assets(db, project, work, inherit_facts=True, inherit_narrative=True)
    project.generation_state = {
        **project.generation_state,
        "publication_policy": "disabled_derivative",
        "publication_reason": "续写项目默认仅供个人创作，未核验权利前禁止导出发布",
    }
    await db.commit()
    await db.refresh(project)
    return ProjectRead.model_validate(project)


@router.post("/{work_id}/fanfic", response_model=ProjectRead)
async def create_fanfic(
    work_id: uuid.UUID,
    payload: FanficRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同人现在必须从新书向导创建")
    work = await db.scalar(
        select(ImportedWork).where(ImportedWork.id == work_id, ImportedWork.user_id == current_user.id)
    )
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入作品不存在")
    if work.analysis_status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="分析尚未完成")

    type_labels = {
        "new_protagonist": "新主角",
        "what_if": "如果线",
        "cp": "CP向",
        "ensemble": "群像篇",
        "after_story": "后日谈",
        "side_story": "原作支线",
        "character_pov": "角色视角",
        "au": "AU世界",
        "fanfic_continuation": "同人续写",
    }
    type_label = type_labels.get(payload.fanfic_type, "同人")
    default_summary = f"基于《{work.title}》的{type_label}同人"

    project_payload = ProjectCreate(
        title=f"同人·{work.title}·{type_label}"[:200],
        genre=work.genre or "其他",
        one_sentence=payload.seed_description[:2000] if len(payload.seed_description) >= 10 else default_summary,
        protagonist_name="新主角",
        protagonist_gender="男",
        protagonist_personality="在原作世界中走出自己的道路",
        target_words=payload.target_words,
        creation_mode="fanfic",
        source_work_id=work.id,
    )

    from app.services.project_bootstrap import seed_new_project

    project = Project(
        user_id=current_user.id,
        title=project_payload.title,
        genre=project_payload.genre,
        one_sentence=project_payload.one_sentence,
        protagonist_name=project_payload.protagonist_name,
        protagonist_gender=project_payload.protagonist_gender,
        protagonist_personality=project_payload.protagonist_personality,
        target_words=project_payload.target_words,
        creation_mode="fanfic",
        source_work_id=work.id,
    )
    db.add(project)
    await db.flush()

    await seed_new_project(db, project, project_payload)
    from app.services.imported_project import materialize_imported_assets

    await materialize_imported_assets(db, project, work, inherit_facts=True, inherit_narrative=True)
    project.generation_state = {
        **project.generation_state,
        "publication_policy": "disabled_derivative",
        "publication_reason": "同人项目默认仅供个人创作，未核验权利前禁止导出发布",
    }
    await db.commit()
    await db.refresh(project)
    return ProjectRead.model_validate(project)


@router.delete("/{work_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_imported_work(
    work_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    work = await db.scalar(
        select(ImportedWork).where(ImportedWork.id == work_id, ImportedWork.user_id == current_user.id)
    )
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入作品不存在")
    await db.delete(work)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
