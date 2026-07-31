"""卷末再规划引擎：把当前 Canon 状态汇总成简报，驱动下一卷规划。

设计依据：9 部长篇拆解报告的共识——长篇必须"写一卷、规划下一卷"滚动
进行，而不是开局一次画死。本模块在每次"规划下一卷"调用时：

1. build_replan_brief: 从数据库装配当前快照（人物状态/伏笔账本/副线/
   近章摘要/待办清单），这就是"再规划上下文"。
2. generate_next_volume_plan: 拿简报 + 全书蓝图 + 上一卷卷纲，让 LLM
   产出下一卷的详细卷纲（目标/冲突/弧列表/收束钩子）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Chapter, CurrentState, OutlineNode, PlotLedger, Project, StoryWiki
from app.services.llm_client import llm_client


async def build_replan_brief(db: AsyncSession, project: Project, next_volume_sequence: int) -> dict[str, Any]:
    """组装"再规划简报"：写到当前位置，系统知道的全部事实。"""
    # 最近 6 章已确认/草稿章节
    recent_chapters = list(
        (
            await db.scalars(
                select(Chapter)
                .where(
                    Chapter.project_id == project.id,
                    Chapter.status.in_(["draft", "confirmed"]),
                )
                .order_by(Chapter.chapter_sequence.desc())
                .limit(6)
            )
        ).all()
    )
    # 活跃伏笔（按重要度+临期排序）
    active_foreshadows = list(
        (
            await db.scalars(
                select(PlotLedger)
                .where(PlotLedger.project_id == project.id, PlotLedger.status.in_(["open", "reminded"]))
                .order_by(PlotLedger.is_yy.desc(), PlotLedger.due_chapter.asc().nullslast())
                .limit(15)
            )
        ).all()
    )
    # 热人物/实体状态
    hot_states = list(
        (
            await db.scalars(
                select(CurrentState)
                .where(CurrentState.project_id == project.id)
                .order_by(CurrentState.last_chapter_sequence.desc(), CurrentState.confidence.desc())
                .limit(30)
            )
        ).all()
    )
    # 全书蓝图与已完成卷纲
    book_outline = await db.scalar(
        select(OutlineNode).where(OutlineNode.project_id == project.id, OutlineNode.layer == "L3", OutlineNode.seq == 1)
    )
    prev_volume = await db.scalar(
        select(OutlineNode).where(
            OutlineNode.project_id == project.id,
            OutlineNode.layer == "L4",
            OutlineNode.seq == next_volume_sequence - 1,
        )
    )
    next_anchor = await db.scalar(
        select(OutlineNode).where(
            OutlineNode.project_id == project.id,
            OutlineNode.layer == "L4",
            OutlineNode.seq == next_volume_sequence,
        )
    )
    # 人物 wiki 页（取最近更新的 12 页）
    character_pages = list(
        (
            await db.scalars(
                select(StoryWiki)
                .where(StoryWiki.project_id == project.id, StoryWiki.category == "character")
                .order_by(StoryWiki.last_updated_chapter.desc())
                .limit(12)
            )
        ).all()
    )

    current_seq = recent_chapters[0].chapter_sequence if recent_chapters else 0
    due_foreshadows = [
        {
            "content": f.description,
            "importance": "A" if f.is_yy else "B",
            "planted_chapter": f.planted_chapter,
            "target_chapter": f.due_chapter,
            "escalation_count": len(f.mentioned_chapters),
            "overdue": bool(f.due_chapter and f.due_chapter <= current_seq),
        }
        for f in active_foreshadows
    ]
    protagonist_states: dict[str, list[dict[str, Any]]] = {}
    for s in hot_states:
        protagonist_states.setdefault(s.entity_key, []).append(
            {"field": s.field, "value": s.value, "as_of_chapter": s.last_chapter_sequence}
        )

    return {
        "next_volume_sequence": next_volume_sequence,
        "current_chapter": current_seq,
        "project": {
            "title": project.title,
            "genre": project.genre,
            "premise": project.one_sentence,
            "protagonist": project.protagonist_name,
        },
        "book_blueprint": book_outline.meta if book_outline else {},
        "previous_volume": {
            "title": prev_volume.title if prev_volume else "",
            "content": prev_volume.meta if prev_volume else {},
        },
        "next_volume_anchor": next_anchor.meta if next_anchor else {},
        "protagonist_state": protagonist_states.get(project.protagonist_name, []),
        "key_character_states": {k: v for k, v in protagonist_states.items() if k != project.protagonist_name},
        "active_foreshadowing": due_foreshadows,
        "character_cards": [
            {"name": p.title, "content": p.content[:400]} for p in character_pages
        ],
        "recent_chapters": [
            {"sequence": c.chapter_sequence, "title": c.title, "summary": c.summary}
            for c in reversed(recent_chapters)
        ],
    }


async def generate_next_volume_plan(brief: dict[str, Any]) -> dict[str, Any]:
    """基于再规划简报，生成下一卷详细卷纲。"""
    if get_settings().llm_backend == "mock":
        sequence = int(brief["next_volume_sequence"])
        return {
            "title": f"第{sequence}卷：新的局面",
            "goal": "承接上一卷的选择后果，让主角在新的局面中完成一次不可逆的成长",
            "opening": "上一卷的余波改变人物处境，新目标从具体损失中自然出现",
            "new_elements": {
                "new_stage": "进入与上一卷规则不同的新舞台",
                "new_opponent_tier": "对手拥有更高一级的资源或信息优势",
                "new_gameplay": "从被动应对转为主动布局",
            },
            "turning_points": ["旧办法首次失效", "关键关系发生变化", "主角主动承担更大代价"],
            "climax": "主角利用本卷积累的信息和关系作出不可撤销的选择",
            "ending_hook": "胜利解决眼前问题，却让下一阶段的核心代价浮出水面",
            "suggested_chapters": 48,
            "foreshadowing_to_resolve": [
                item["content"] for item in brief["active_foreshadowing"] if item["overdue"]
            ],
            "arcs": [
                {
                    "sequence": index,
                    "title": title,
                    "goal": goal,
                    "conflict": conflict,
                    "climax": climax,
                    "resolution": resolution,
                    "estimated_chapters": chapters,
                    "involved_characters": [brief["project"]["protagonist"]],
                }
                for index, (title, goal, conflict, climax, resolution, chapters) in enumerate(
                    [
                        (
                            "余波", "确认上一卷造成的新处境", "旧关系无法维持",
                            "第一个现实代价落地", "主角被迫选择新目标", 6,
                        ),
                        (
                            "入局", "进入新舞台并理解规则", "主角处于信息劣势",
                            "第一次试探失败", "获得可验证的新线索", 10,
                        ),
                        (
                            "对抗", "建立可执行的反击方案", "对手控制关键资源",
                            "盟友关系发生逆转", "主角夺回局部主动权", 12,
                        ),
                        (
                            "破局", "完成本卷核心目标", "胜利需要支付不可逆代价",
                            "本卷矛盾正面爆发", "解决本卷问题并开启下一阶段", 14,
                        ),
                    ],
                    start=1,
                )
            ],
        }
    prompt = (
        f"全书蓝图：{json.dumps(brief['book_blueprint'], ensure_ascii=False)}\n"
        f"上一卷：{json.dumps(brief['previous_volume'], ensure_ascii=False)}\n"
        f"本卷锚点（卷{brief['next_volume_sequence']}）："
        f"{json.dumps(brief['next_volume_anchor'], ensure_ascii=False)}\n"
        f"主角当前状态：{json.dumps(brief['protagonist_state'], ensure_ascii=False)}\n"
        f"关键人物状态：{json.dumps(brief['key_character_states'], ensure_ascii=False)}\n"
        f"活跃伏笔（overdue=true 表示已过回收窗口，必须在本卷处理）："
        f"{json.dumps(brief['active_foreshadowing'], ensure_ascii=False)}\n"
        f"最近章节：{json.dumps(brief['recent_chapters'], ensure_ascii=False)}\n\n"
        "你是长篇网文主编。基于以上\"再规划简报\"规划下一卷。硬规则："
        "① 不得改写已发生的既定事实和已回收伏笔；"
        "② 所有 overdue 伏笔必须在本卷给出回收或推进方案；"
        "③ 本卷必须有明确的\"三增量\"——新舞台/新对手层级/新玩法至少占两项，防止读者疲劳；"
        "④ 卷末钩子承接上一卷结局余波，不得突兀开新案；"
        "⑤ 弧列表 4-8 个，每个弧是一个\"起因-发展-高潮-收束\"闭环，给出预计章数。"
        "输出 JSON："
        '{"title":string,"goal":string,"opening":string,"new_elements":{"new_stage":string,'
        '"new_opponent_tier":string,"new_gameplay":string},"turning_points":[string],'
        '"climax":string,"ending_hook":string,"suggested_chapters":number,'
        '"foreshadowing_to_resolve":[string],"arcs":[{"sequence":number,"title":string,'
        '"goal":string,"conflict":string,"climax":string,"resolution":string,'
        '"estimated_chapters":number,"involved_characters":[string]}]}'
    )
    raw = await llm_client.complete(
        "你是长篇网文主编，擅长在既有 Canon 约束下滚动规划下一卷，保持长线一致性。",
        prompt,
        "json",
    )
    result = json.loads(raw)
    if not isinstance(result, dict) or not result.get("goal") or not result.get("arcs"):
        raise ValueError("卷纲字段不完整")
    return result
