from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ImmersiveSession, ImportedChapter, ImportedWork
from app.services.llm_client import llm_client


async def create_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    work_id: uuid.UUID,
    character_name: str,
    experience_style: str = "original",
) -> ImmersiveSession:
    """Create a new immersive session and generate the opening scene."""
    work = await db.get(ImportedWork, work_id)
    if not work:
        raise ValueError("作品不存在")

    # Get initial character state from analysis
    first_chapters = list((await db.scalars(
        select(ImportedChapter)
        .where(ImportedChapter.work_id == work_id)
        .order_by(ImportedChapter.chapter_sequence)
        .limit(3)
    )).all())

    opening_text = "\n".join(ch.content[:1000] for ch in first_chapters)

    experience_labels = {"original": "沿原剧情", "free": "自由探索"}
    experience_label = experience_labels.get(experience_style, "What-If改变历史")
    initial_state_prompt = (
        f"小说《{work.title}》，角色：{character_name}\n"
        f"体验模式：{experience_label}\n\n"
        f"开篇内容：\n{opening_text[:3000]}\n\n"
        f"提取{character_name}在故事开篇时的状态，输出JSON：\n"
        '{"location": string, "condition": string, "inventory": [string], '
        '"relationships": [{"name": string, "relation": string}], '
        '"current_goal": string, "stats": {}}'
    )

    try:
        raw = await llm_client.complete("提取小说角色初始状态。", initial_state_prompt, "json")
        character_state = json.loads(raw)
    except Exception:
        character_state = {
            "location": "故事起点",
            "condition": "正常",
            "inventory": [],
            "relationships": [],
            "current_goal": "未知",
        }

    session = ImmersiveSession(
        user_id=user_id,
        work_id=work_id,
        character_name=character_name,
        experience_style=experience_style,
        character_state=character_state,
        segments=[],
    )
    db.add(session)
    await db.flush()

    # Generate opening scene
    opening = await _generate_segment(work, session, None)
    session.segments = [opening]
    await db.commit()
    await db.refresh(session)

    return session


async def make_choice(
    db: AsyncSession,
    session: ImmersiveSession,
    choice_index: int,
) -> dict[str, Any]:
    """Process a player choice and generate the next scene."""
    existing = session.segments or []
    if not existing:
        raise ValueError("会话没有场景")

    last_segment = existing[-1]
    choices = last_segment.get("choices", [])
    if choice_index >= len(choices):
        raise ValueError("无效的选择")

    chosen = str(choices[choice_index])
    work = await db.get(ImportedWork, session.work_id)

    new_segment = await _generate_segment(work, session, chosen)

    if "character_state" in new_segment:
        session.character_state = dict(new_segment["character_state"])

    session.segments = list(existing) + [new_segment]
    await db.commit()

    return new_segment


async def _generate_segment(
    work: ImportedWork,
    session: ImmersiveSession,
    chosen_action: str | None,
) -> dict[str, Any]:
    """Generate a narrative segment with choices."""
    segments = session.segments or []
    recent_narrative = "\n".join(
        s.get("narrative", "")[-300:] for s in segments[-3:]
    )

    state_text = json.dumps(session.character_state, ensure_ascii=False)
    chosen_text = chosen_action or "（开场）"

    prompt = (
        f"小说《{work.title}》代入体验模式\n"
        f"你是{session.character_name}，{session.experience_style}模式\n\n"
        f"当前状态：{state_text}\n"
        f"最近剧情：{recent_narrative[:1500]}\n"
        f"玩家选择：{chosen_text}\n\n"
        "以第二人称写一段200-400字的场景叙述，然后给出2-3个选择。\n"
        "输出JSON：\n"
        '{"narrative": string, '
        '"choices": ["选项描述1", "选项描述2"], '
        '"character_state": {更新后的角色状态}}'
    )

    try:
        raw = await llm_client.complete(
            f"你是一个互动小说引擎。以第二人称讲述玩家的体验，"
            f"保持《{work.title}》的世界观和风格。每段结尾给2-3个有意义的选择。",
            prompt,
            "json",
        )
        segment = json.loads(raw)
        raw_choices = segment.get("choices", ["继续前进", "观察周围"])
        segment["choices"] = [
            c.get("label", str(c)) if isinstance(c, dict) else str(c)
            for c in raw_choices
        ]
        return segment
    except Exception:
        return {
            "narrative": f"你站在{work.title}的世界中，四周的一切都显得既熟悉又陌生。",
            "choices": ["探索周围环境", "回忆目前的情况"],
            "character_state": session.character_state,
        }


async def solidify_to_novel(
    db: AsyncSession,
    session: ImmersiveSession,
) -> dict[str, Any]:
    """Convert an immersive session's segments into a novel project payload."""
    work = await db.get(ImportedWork, session.work_id)
    segments = session.segments or []

    narratives = [s.get("narrative", "") for s in segments if s.get("narrative")]
    combined = "\n\n".join(narratives)

    prompt = (
        f"以下是玩家在《{work.title if work else '未知'}》中以{session.character_name}身份的互动体验记录：\n\n"
        f"{combined[:6000]}\n\n"
        "将这段体验整理成一个小说项目配置（同人小说），输出JSON：\n"
        '{"title": string, "genre": string, "one_sentence": string, '
        '"protagonist_name": string, "protagonist_gender": string, '
        '"protagonist_personality": string, "target_words": 300000}'
    )

    try:
        raw = await llm_client.complete(
            "将互动体验转化为小说大纲。保留玩家的选择作为核心情节。",
            prompt,
            "json",
        )
        project_data = json.loads(raw)
        project_data["creation_mode"] = "immersive"
        project_data["source_work_id"] = str(session.work_id)
        return project_data
    except Exception:
        return {
            "title": f"{session.character_name}的故事",
            "genre": work.genre or "玄幻" if work else "玄幻",
            "one_sentence": f"在{work.title if work else '异世界'}中，{session.character_name}走出了一条不同的道路。",
            "protagonist_name": session.character_name,
            "protagonist_gender": "男",
            "protagonist_personality": "坚毅果敢，在命运面前不屈",
            "target_words": 300_000,
            "creation_mode": "immersive",
        }
