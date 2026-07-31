from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import MarketTrack
from app.services.llm_client import llm_client
from app.utils.canonical import parse_json_object

logger = logging.getLogger(__name__)

SPECULATIVE_MARKERS = (
    "灵异",
    "诡异",
    "怪谈",
    "超能力",
    "异能",
    "无限流",
    "副本",
    "主神",
    "复苏",
    "末日",
    "废土",
    "灾变",
    "丧尸",
    "玄幻",
    "修仙",
)


def _track_text(track: Any) -> str:
    return " ".join(
        str(value or "")
        for value in (
            track.track_name,
            track.genre,
            track.sub_genre,
            track.golden_formula,
            " ".join(track.taste_tags or []),
        )
    )


def _conflicts_with_reader_boundary(track: Any, selected_categories: list[str], reader_text: str) -> bool:
    track_text = _track_text(track)
    wants_reality = "现实" in " ".join(selected_categories) or any(
        marker in reader_text for marker in ("现实题材", "现实悬疑", "社会派", "无超自然")
    )
    if wants_reality and any(marker in track_text for marker in SPECULATIVE_MARKERS):
        return True

    explicit_boundaries = {
        "系统": ("系统",),
        "重生": ("重生",),
        "穿越": ("穿越",),
        "超能力": ("超能力", "异能"),
        "灵异": ("灵异", "诡异", "怪谈"),
        "无限流": ("无限流", "副本", "主神"),
    }
    return any(
        boundary in reader_text and any(marker in track_text for marker in markers)
        for boundary, markers in explicit_boundaries.items()
    )


def _seed_boundary_violation(
    seed: dict[str, Any],
    avoid_elements: str | None,
    selected_categories: list[str] | None = None,
) -> str | None:
    seed_text = json.dumps(seed, ensure_ascii=False)
    forbidden = {
        "系统": ("系统",),
        "重生": ("重生",),
        "穿越": ("穿越",),
        "超能力": ("超能力", "异能"),
        "灵异": ("灵异", "诡异", "怪谈"),
        "无限流": ("无限流", "副本", "主神"),
    }
    boundary_text = avoid_elements or ""
    categories = " ".join(selected_categories or [])
    wants_reality = "现实" in categories or any(
        marker in boundary_text for marker in ("现实题材", "现实悬疑", "社会派", "无超自然")
    )
    if wants_reality:
        marker = next((item for item in SPECULATIVE_MARKERS if item in seed_text), None)
        if marker:
            return f"现实题材中出现了超自然元素“{marker}”"
    for boundary, markers in forbidden.items():
        if boundary not in boundary_text:
            continue
        marker = next((item for item in markers if item in seed_text), None)
        if marker:
            return f"故事包含明确避雷元素“{marker}”"
    return None


def _seed_violates_boundaries(seed: dict[str, Any], avoid_elements: str) -> bool:
    return _seed_boundary_violation(seed, avoid_elements) is not None


SEED_CORE_FIELDS = {
    "title",
    "one_sentence",
    "protagonist_name",
    "hook",
    "opening_event",
    "story_engine",
    "long_term_growth",
}
SEED_OPTIONAL_DEFAULTS = {
    "protagonist_gender": "",
    "protagonist_personality": "",
    "reader_promise": "",
    "difference": "",
    "risk_note": "",
    "genre": "",
    "story_question": "",
    "protagonist_method": "",
    "protagonist_cost": "",
}
SEED_FIELD_ALIASES = {
    "premise": "one_sentence",
    "protagonist": "protagonist_name",
    "selling_point": "hook",
    "promise": "reader_promise",
    "inciting_incident": "opening_event",
    "engine": "story_engine",
    "growth_arc": "long_term_growth",
    "unique_point": "difference",
    "risk": "risk_note",
    "category": "genre",
}


def _normalize_story_seeds(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("seeds", "response", "data", "stories"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                value = candidate
                break
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        seed = dict(item)
        for alias, canonical in SEED_FIELD_ALIASES.items():
            if not seed.get(canonical) and seed.get(alias):
                seed[canonical] = seed[alias]
        for field, default in SEED_OPTIONAL_DEFAULTS.items():
            seed.setdefault(field, default)
        normalized.append(seed)
    return normalized


def _story_seed_rejection_reason(
    seeds: list[dict[str, Any]],
    count: int,
    avoid_elements: str | None,
    selected_categories: list[str],
    require_agency: bool = False,
) -> str | None:
    if len(seeds) < count:
        return f"只返回了 {len(seeds)} 个故事，需要 {count} 个"
    for index, seed in enumerate(seeds[:count], start=1):
        missing = sorted(field for field in SEED_CORE_FIELDS if not seed.get(field))
        if missing:
            return f"第 {index} 个故事缺少字段：{', '.join(missing)}"
        if require_agency:
            agency_fields = ("story_question", "protagonist_method", "protagonist_cost")
            missing_agency = [field for field in agency_fields if not seed.get(field)]
            if missing_agency:
                return f"第 {index} 个故事缺少人物因果字段：{', '.join(missing_agency)}"
        violation = _seed_boundary_violation(seed, avoid_elements, selected_categories)
        if violation:
            return f"第 {index} 个故事不符合要求：{violation}"
    return None


def _cast_rejection_reasons(characters: Any, categories: list[str], mode: str) -> list[str]:
    reasons: list[str] = []
    if not isinstance(characters, list) or not characters:
        return ["没有返回人物数组"]
    required_fields = ("name", "role") if mode == "names" else (
        "name",
        "role",
        "personality",
        "desire",
        "flaw",
        "relationship",
        "method",
        "bottom_line",
        "pressure_action",
    )
    if not all(isinstance(item, dict) and all(item.get(field) for field in required_fields) for item in characters):
        reasons.append("人物字段不完整")
        return reasons
    if mode == "full" and not 4 <= len(characters) <= 6:
        reasons.append("完整人物组必须包含1名主角和3至5名关键人物")
    if mode == "names" or "悬疑" not in categories:
        return reasons
    if len(characters) < 5 or not any("受害" in item["role"] or "死者" in item["role"] for item in characters):
        reasons.append("悬疑人物组必须至少5人并包含事件受害者")
    leaked_answers = ("凶手", "挪用", "造假", "倒签", "代开发票", "补了进货日期")
    card_text = json.dumps(characters, ensure_ascii=False)
    leaked = [marker for marker in leaked_answers if marker in card_text]
    if leaked:
        reasons.append(f"人物卡提前泄露案情：{'、'.join(leaked)}")
    if any(
        "争吵" in str(item.get("flaw", "")) and "隐瞒" in str(item.get("flaw", ""))
        for item in characters
    ):
        reasons.append("不要再用隐瞒事发前争吵充当人物秘密")
    return reasons


def _cast_meets_genre_requirements(characters: Any, categories: list[str], mode: str) -> bool:
    return not _cast_rejection_reasons(characters, categories, mode)


async def match_taste_to_tracks(
    db: AsyncSession,
    taste_tags: list[str],
    channel: str | None = None,
    feeling: str | None = None,
    reader_wish: str | None = None,
    primary_category: str | None = None,
    primary_categories: list[str] | None = None,
    favorite_works: str | None = None,
    avoid_elements: str | None = None,
    target_words: int = 800_000,
    limit: int = 5,
) -> tuple[list[Any], str | None]:
    """Match user taste preferences to market tracks. Returns (tracks, ai_commentary)."""
    from app.services.market_catalog import ensure_market_catalog

    await ensure_market_catalog(db)
    query = select(MarketTrack)
    if channel:
        query = query.where(MarketTrack.channel == channel)

    all_tracks = list((await db.scalars(query.order_by(MarketTrack.heat.desc()))).all())

    if not all_tracks:
        return [], None

    selected_categories = primary_categories or ([primary_category] if primary_category else [])
    reader_text = " ".join(filter(None, [reader_wish, favorite_works, avoid_elements, feeling]))
    compatible_tracks = [
        track for track in all_tracks
        if not _conflicts_with_reader_boundary(track, selected_categories, avoid_elements or "")
    ]
    if compatible_tracks:
        all_tracks = compatible_tracks

    # Score tracks by taste tag overlap + heat
    scored = []
    for track in all_tracks:
        tag_overlap = len(set(taste_tags) & set(track.taste_tags)) if taste_tags else 0
        wish = reader_wish or ""
        wish_overlap = sum(1 for tag in track.taste_tags if tag and tag in wish)
        if track.genre in wish or track.track_name in wish:
            wish_overlap += 2
        category_bonus = 2.5 if any(
            track.genre == category or category in track.track_name for category in selected_categories
        ) else 0
        intent_bonus = sum(
            0.7
            for marker in (track.sub_genre, track.track_name, *(track.taste_tags or []))
            if marker and marker in reader_text
        )
        heat_score = track.heat / 10.0
        trend_bonus = 0.2 if track.heat_trend == "rising" else -0.1 if track.heat_trend == "falling" else 0
        difficulty_bonus = 0.1 if track.difficulty == "beginner" else -0.1 if track.difficulty == "advanced" else 0
        score = (
            category_bonus
            + tag_overlap * 0.4
            + wish_overlap * 0.5
            + heat_score * 0.3
            + trend_bonus
            + difficulty_bonus
            + intent_bonus
        )
        scored.append((score, track))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_tracks = [t for _, t in scored[:limit]]

    # Generate AI commentary
    track_summary = "\n".join(
        f"- {t.track_name} (热度{t.heat}, {t.heat_trend}, {t.difficulty})"
        for t in top_tracks
    )
    taste_str = "、".join(taste_tags) if taste_tags else "未指定"
    feeling_str = feeling or "未指定"

    try:
        commentary = await llm_client.complete(
            "你是网文市场分析师，用轻松口吻给新手作者推荐赛道。",
            f"频道：{channel or '由AI判断'}\n故事类型：{'、'.join(selected_categories) or '未指定'}\n"
            f"用户口味标签：{taste_str}\n用户自己描述：{reader_wish or '未填写'}\n"
            f"喜欢的作品：{favorite_works or '未填写'}\n明确避雷：{avoid_elements or '无'}\n"
            f"计划篇幅：约{target_words}字\n想要的感觉：{feeling_str}\n"
            f"推荐赛道：\n{track_summary}\n\n"
            "用2-3句话如实点评为什么推荐这些赛道。不得声称用户明确避雷的元素与其要求相配；"
            "市场热度只能参考，题材边界优先。语气自然友好。",
            "text",
        )
        if commentary.lstrip().startswith("[MOCK:"):
            commentary = None
    except Exception:
        commentary = None

    return top_tracks, commentary


def _normalize_world_engine(value: Any, base: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("world_engine"), dict):
        value = value["world_engine"]
    if not isinstance(value, dict):
        value = {}
    result = {**base, **value}
    for field in ("progression_axes", "conflict_generators", "limitations", "daily_life_effects"):
        raw = result.get(field)
        if isinstance(raw, str):
            result[field] = [item.strip() for item in re.split(r"[、；;，,]", raw) if item.strip()]
        elif not isinstance(raw, list):
            result[field] = []
    tests = result.get("pressure_tests")
    result["pressure_tests"] = tests if isinstance(tests, list) else []
    return result


async def generate_world_engine(
    payload: dict[str, Any],
    guide_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a project-specific world engine grounded in approved guide evidence."""
    from app.engine.worldbuilder import get_genre_world_contract, validate_world_engine

    genre = str(payload.get("genre") or "").strip()
    base = get_genre_world_contract(genre)
    evidence = [
        {
            "title": item.get("title") or item.get("source_title") or "写作指导",
            "principle": item.get("principle") or item.get("content", "")[:900],
            "checks": item.get("checks") or [],
        }
        for item in (guide_context or [])[:8]
    ]
    prompt = (
        f"主类型：{genre}\n"
        f"频道与辅助类型：{payload.get('channel') or '未限定'}；"
        f"{'、'.join(payload.get('primary_categories') or []) or genre}\n"
        f"作者想看的故事：{payload.get('reader_wish') or '未填写'}\n"
        f"作者创作宪章：{json.dumps(payload.get('author_intent') or {}, ensure_ascii=False)}\n"
        f"喜欢作品只借鉴吸引力：{payload.get('favorite_works') or '未填写'}\n"
        f"明确避雷：{payload.get('avoid_elements') or '无'}\n"
        f"类型基础契约：{json.dumps(base, ensure_ascii=False)}\n"
        "作者已修改的世界字段（非空内容优先保留）："
        f"{json.dumps(payload.get('world_engine') or {}, ensure_ascii=False)}\n"
        f"已审核/可追溯写作指导：{json.dumps(evidence, ensure_ascii=False)}\n\n"
        "为这一部小说生成专属世界发动机，不写故事大纲，不生成三套方案，不堆地名、纪年和百科。"
        "主类型决定发动机，辅助类型只能补充体验。每项规则都要能制造人物选择；"
        "能力不能替人物解决问题，成长必须同时改变资源、身份、关系或地图中的至少两项。"
        "男频重点检查能力/资源/身份扩张，女频重点检查人物自身成长、选择权与关系议价，"
        "但不得使用性别刻板印象。保留作者心意，主动舍弃不支撑核心体验的设定。"
        "输出一个JSON对象，字符串尽量不超过80字："
        '{"engine_name":string,"reader_promise":string,"core_rule":string,'
        '"power_source":string,"scarcity":string,"social_order":string,'
        '"progression_axes":[string],"conflict_generators":[string],'
        '"limitations":[string],"core_cost":string,"daily_life_effects":[string],'
        '"escalation_model":string,"opening_pressure":string,'
        '"pressure_tests":[{"desire":string,"rule_pressure":string,"costly_choice":string}],'
        '"kept_innovations":[string],"rejected_ideas":[string]}。'
        "pressure_tests必须恰好3项，分别验证资源竞争、关系/身份冲突、能力限制。"
    )
    last_error: Exception | None = None
    feedback = ""
    for _attempt in range(2):
        try:
            raw = await llm_client.complete(
                "你是长篇小说世界设计总编。世界观是剧情发动机，不是设定百科。只输出JSON。",
                prompt + feedback,
                "json",
                max_tokens=2600,
            )
            world = _normalize_world_engine(json.loads(raw), base)
            issues = validate_world_engine(world, genre, strict=True)
            if not issues:
                return world
            last_error = ValueError("；".join(issues))
            feedback = "\n上次世界包被阻断：" + "；".join(issues) + "。只修正这些硬伤。"
        except Exception as exc:
            last_error = exc
            feedback = "\n上次输出无法解析或不完整。本次压缩表达并保证JSON字段完整。"
    raise RuntimeError(f"世界发动机仍未通过压力测试：{last_error}") from last_error


async def generate_story_seeds(
    taste_tags: list[str],
    channel: str | None = None,
    reader_wish: str | None = None,
    primary_category: str | None = None,
    primary_categories: list[str] | None = None,
    favorite_works: str | None = None,
    avoid_elements: str | None = None,
    style_description: str | None = None,
    author_intent: dict[str, str] | None = None,
    world_engine: dict[str, Any] | None = None,
    target_words: int = 800_000,
    count: int = 3,
) -> list[dict[str, str]]:
    """Generate story seeds directly from the author's intent."""
    taste_str = "、".join(taste_tags) if taste_tags else "无特定偏好"

    prompt = (
        f"阅读方向：{channel or '由故事自然决定'}\n"
        f"用户口味：{taste_str}\n\n"
        f"作品故事类型：{'、'.join(primary_categories or []) or primary_category or '未指定'}\n"
        f"用户想看的故事：{reader_wish or '未具体说明'}\n"
        f"喜欢的作品（只借鉴吸引力，不复制设定与表达）：{favorite_works or '未填写'}\n"
        f"明确不要出现：{avoid_elements or '无'}\n"
        f"文笔与叙事要求：{style_description or '暂不限定'}\n"
        f"作者创作宪章：{json.dumps(author_intent or {}, ensure_ascii=False)}\n"
        f"已确认世界发动机：{json.dumps(world_engine or {}, ensure_ascii=False)}\n"
        f"计划篇幅：约{target_words}字\n"
        f"生成 {count} 个故事入口。用户想看的内容、创作宪章、世界规则和避雷项是硬约束。"
        "故事必须由已确认世界规则自然产生，主角要有具体欲望、个人化解决方法和必须支付的代价。"
        "故事问题写成“主角能否得到X而不失去Y”的可持续两难；开篇事件中主角必须主动做出选择。"
        f"只返回下方列出的字段，不要补充其他字段。"
        f"一句话故事和开篇事件各不超过45字，其余说明各不超过35字，总输出不超过1200个中文字符。"
        f"字符串内引用名称只用中文引号《》或「」，"
        f"禁止使用未转义的英文双引号，必须保证JSON完整闭合。\n\n"
        f"输出 JSON 数组：\n"
        f'[{{"title": string, "one_sentence": string, "protagonist_name": string, '
        f'"protagonist_gender": "男"|"女", "protagonist_personality": string, '
        f'"hook": string, "reader_promise": string, "opening_event": string, "story_engine": string, '
        f'"long_term_growth": string, "difference": string, "risk_note": string, "genre": string, '
        f'"story_question": string, "protagonist_method": string, "protagonist_cost": string}}]'
    )

    last_error: Exception | None = None
    rejection_reason = ""
    selected_categories = primary_categories or ([primary_category] if primary_category else [])
    for attempt in range(2):
        retry_note = (
            f"\n上次结果未通过检查：{rejection_reason}。请只修正这个问题，并保证 {count} 个对象和 JSON 完整闭合。"
            if attempt else ""
        )
        try:
            raw = await llm_client.complete(
                "你是网文选题编辑。只做简洁、完整的结构化输出，不展开写大纲。",
                prompt + retry_note,
                "json",
            )
            seeds = _normalize_story_seeds(json.loads(raw))
            rejection_reason = _story_seed_rejection_reason(
                seeds, count, avoid_elements, selected_categories, require_agency=bool(world_engine)
            ) or ""
            if not rejection_reason:
                return seeds[:count]
            last_error = ValueError(rejection_reason)
        except json.JSONDecodeError as exc:
            rejection_reason = f"JSON 无法解析（{exc.msg}）"
            last_error = exc
        except Exception as exc:
            rejection_reason = str(exc) or type(exc).__name__
            last_error = exc

    raise RuntimeError(f"故事构思未通过检查：{rejection_reason}，请重新生成") from last_error


async def polish_style_description(description: str, genre: str | None = None) -> str:
    prompt = (
        f"故事类型：{genre or '未指定'}\n用户原话：{description}\n\n"
        "把用户原话整理成一段可以直接约束小说写作的文笔要求。保留用户意图，不加入市场分析，"
        "不模仿具体作者原句。说明叙述距离、句子与段落节奏、细节选择、对话方式、信息释放和明确避免项。"
        "只输出整理后的正文，不要标题、解释或列表，不超过500字。"
    )
    return (await llm_client.complete("你是小说文笔编辑，负责把作者口味整理成准确、可执行的写作合同。", prompt)).strip()


STYLE_ANALYZE_SYSTEM_PROMPT = (
    "你是资深小说编辑，擅长拆解作品的文笔、叙事与世界观写法，"
    "并把观察整理成可以被另一个写作者直接执行的要求清单。"
)


def build_style_analyze_prompt(title: str, text: str, genre: str | None, focus: str) -> str:
    focus_instruction = {
        "style": "只分析文笔与叙事：叙述视角与距离、句子长短与节奏、细节选择、对话方式、信息释放、情绪表达。",
        "world": "只分析世界观与设定：世界规则、力量/社会体系、信息如何随剧情释放、设定如何服务冲突。",
        "both": (
            "分两部分分析：先讲文笔与叙事（视角、节奏、细节、对话、信息释放），"
            "再讲世界观与设定（规则、体系、释放方式）。"
        ),
    }[focus]
    return (
        f"作品：《{title or '未命名'}》\n大致类型：{genre or '未指定'}\n\n"
        f"原文节选：\n{text}\n\n"
        f"{focus_instruction}\n"
        "要求：\n"
        "1. 用具体、可执行的描述，不写空泛赞美；每一点都说明“写作时该怎么做”。\n"
        "2. 引用原文中的短句作为例子（每处不超过30字），说明例子体现了什么手法。\n"
        "3. 最后输出一份“可以直接当作写作要求使用”的总结，用第二人称祈使句，不少于1500字，"
        "覆盖叙述视角、节奏、细节、对话、信息释放和世界观释放方式，"
        "让另一个 AI 或写作者照着写就能接近这种感觉。\n"
        "4. 不复述剧情，不分析市场。"
    )


async def refine_story_seed(
    seed: dict[str, str],
    adjustments: dict[str, str],
) -> dict[str, str]:
    """Refine a story seed based on user adjustments."""
    adj_text = "\n".join(f"- {k}: {v}" for k, v in adjustments.items())
    seed_text = json.dumps(seed, ensure_ascii=False, indent=2)

    prompt = (
        f"原始故事种子：\n{seed_text}\n\n"
        f"用户调整要求：\n{adj_text}\n\n"
        f"根据调整要求修改故事种子，保持格式不变，输出修改后的完整 JSON。"
    )

    try:
        raw = await llm_client.complete(
            "你是一个网文策划，根据用户反馈微调故事种子。",
            prompt,
            "json",
        )
        return json.loads(raw)
    except Exception as exc:
        raise RuntimeError("AI 暂时无法调整故事，请稍后重试") from exc


async def generate_character_cast(payload: dict[str, Any]) -> dict[str, Any]:
    mode = payload.get("mode", "full")
    existing = payload.get("existing_characters") or []
    if mode == "names" and not existing:
        existing = [{"role": "主角"}, {"role": "关键同伴"}, {"role": "主要对手"}]
    categories = payload.get("primary_categories") or []
    task = (
        "只为现有人物分别换一个贴合时代、地域和性格的中文姓名，其他字段保持原意。"
        if mode == "names"
        else "设计1名主角和3至5名真正能推动主线的关键人物，人物之间必须有合作、冲突或相互亏欠。"
    )
    genre_requirements = ""
    if "悬疑" in categories:
        genre_requirements = (
            "\n悬疑人物硬要求：必须写出事件受害者，并把他/她当作事发前有欲望、有选择的人；"
            "还要包含主角最切身的关系人，以及至少两名利益方向不同的熟人。"
            "每人的欲望要具体，弱点必须会让本人作出错误选择，关系要写清双方互相需要或牵制什么。"
            "人物卡不能直接宣布谁挪款、造假、说谎或犯案，不用常见的隐瞒争吵充当秘密；"
            "先设计完整的人，再让后续蓝图决定证据如何改变对他们的理解。"
        )
    prompt = (
        f"故事资料：{json.dumps(payload.get('seed', {}), ensure_ascii=False)}\n"
        f"已确认世界发动机：{json.dumps(payload.get('world_engine') or {}, ensure_ascii=False)}\n"
        "核心故事问题："
        f"{payload.get('story_question') or payload.get('seed', {}).get('story_question') or '待人物共同形成'}\n"
        f"故事类型：{'、'.join(payload.get('primary_categories') or []) or '未指定'}\n"
        f"用户想看：{payload.get('reader_wish') or '未填写'}\n"
        f"作者创作宪章：{json.dumps(payload.get('author_intent') or {}, ensure_ascii=False)}\n"
        f"现有人物：{json.dumps(existing, ensure_ascii=False)}\n\n"
        f"{task}{genre_requirements}人物不能只是标签或线索容器。每个人都要有自己的欲望、"
        "惯用方法、不可轻易跨越的底线，以及压力下会主动采取的行动；这些行动必须能合作、阻挠或反噬主角。"
        "每个字段不超过60字，总输出不超过2200个中文字符。输出JSON："
        '{"characters":[{"name":string,"gender":string,"role":string,"personality":string,'
        '"desire":string,"flaw":string,"relationship":string,"method":string,'
        '"bottom_line":string,"pressure_action":string}]}'
    )
    last_error: Exception | None = None
    retry_feedback = ""
    for _attempt in range(2):
        try:
            raw = await llm_client.complete(
                "你是小说人物编辑，只输出简洁、可编辑且完整的人物数据。",
                prompt + retry_feedback,
                "json",
            )
            result = json.loads(raw)
            characters = result.get("characters") if isinstance(result, dict) else None
            rejection_reasons = _cast_rejection_reasons(characters, categories, mode)
            if not rejection_reasons:
                fields = (
                    ("name", "gender", "role", "personality", "desire", "flaw", "relationship")
                    if mode == "names"
                    else (
                        "name", "gender", "role", "personality", "desire", "flaw", "relationship",
                        "method", "bottom_line", "pressure_action",
                    )
                )
                return {
                    "characters": [
                        {field: str(item.get(field) or "") for field in fields}
                        for item in characters[:6]
                    ]
                }
            last_error = ValueError("; ".join(rejection_reasons))
            retry_feedback = (
                "\n上次人物设计被拒绝，原因："
                + "；".join(rejection_reasons)
                + "。本次逐条修正，并优先保证JSON完整闭合。"
            )
        except Exception as exc:
            last_error = exc
            retry_feedback = "\n上次输出无法解析。本次优先保证所有人物字段齐全且JSON完整闭合。"
    raise RuntimeError("AI 连续两次没有返回完整人物，请稍后再试") from last_error


async def generate_lazy_project(db: AsyncSession) -> dict[str, str]:
    """Generate a complete project payload for lazy mode -- one click, surprise me."""
    # Pick a hot track
    hot_track = await db.scalar(
        select(MarketTrack).order_by(MarketTrack.heat.desc()).limit(1)
    )

    track_hint = ""
    if hot_track:
        track_hint = (
            f"赛道参考：{hot_track.track_name} ({hot_track.channel}·{hot_track.genre})\n"
            f"黄金公式：{hot_track.golden_formula or ''}\n"
        )

    prompt = (
        f"{track_hint}"
        "生成一个完整的小说项目配置，要求有创意、能吸引读者。\n"
        "输出 JSON：\n"
        '{"title": string, "genre": string, "one_sentence": string (50-150字), '
        '"protagonist_name": string, "protagonist_gender": "男"|"女", '
        '"protagonist_personality": string (30-80字), "target_words": 1000000, '
        '"channel": "男频"|"女频", "track": string}'
    )

    try:
        raw = await llm_client.complete(
            "你是一个畅销网文策划。随机选择一个有市场前景的方向，设计一个新颖有趣的故事。",
            prompt,
            "json",
        )
        data = json.loads(raw)
        data.setdefault("target_words", 1_000_000)
        data["creation_mode"] = "lazy"
        return data
    except Exception as exc:
        raise RuntimeError("AI 暂时没有生成成功，请稍后重试") from exc


def _chapter_plan_review_passes(review: Any) -> bool:
    return (
        isinstance(review, dict)
        and review.get("verdict") == "pass"
        and isinstance(review.get("score"), int | float)
        and review["score"] >= 82
        and not review.get("blocking_issues")
    )


def _chapter_plan_rejection_reasons(plan: Any) -> list[str]:
    if not isinstance(plan, dict):
        return ["章纲不是 JSON object"]
    reasons: list[str] = []
    titles = plan.get("title_candidates")
    if not isinstance(titles, list) or not any(str(item).strip() for item in titles):
        reasons.append("至少需要一个可用章名")
    beats = plan.get("beats")
    if not isinstance(beats, list) or not 1 <= len(beats) <= 8:
        reasons.append("必须包含一至八个连续情节段")
        return reasons
    for index, beat in enumerate(beats, start=1):
        if not isinstance(beat, dict):
            reasons.append(f"情节段{index}不是对象")
            continue
        if len(str(beat.get("event") or "").strip()) < 8:
            reasons.append(f"情节段{index}事件过于简略，必须写清谁做什么以及发生的结果")
    budget = plan.get("progression_budget")
    if isinstance(budget, dict):
        if len(str(budget.get("single_local_change") or "").strip()) < 8:
            reasons.append("推进预算必须明确本章唯一允许发生的局部变化")
        if len(str(budget.get("must_remain_open") or "").strip()) < 8:
            reasons.append("推进预算必须明确本章结束后仍未解决什么")
    return reasons


def _normalize_chapter_plan(plan: dict[str, Any]) -> dict[str, Any]:
    result = dict(plan)
    result["title_candidates"] = [
        str(item).strip() for item in (plan.get("title_candidates") or []) if str(item).strip()
    ][:3]
    beats = [dict(item) for item in (plan.get("beats") or []) if isinstance(item, dict)][:8]
    for index, beat in enumerate(beats):
        beat["segment"] = str(beat.get("segment") or f"情节 {index + 1}").strip()
        beat["event"] = str(beat.get("event") or "").strip()
        beat["characters"] = [
            str(item).strip() for item in (beat.get("characters") or []) if str(item).strip()
        ]
    result["beats"] = beats
    first = beats[0] if beats else {}
    last = beats[-1] if beats else {}
    goal = str(plan.get("goal") or plan.get("reader_experience") or first.get("event") or "").strip()
    conflict = str(plan.get("conflict") or first.get("obstacle") or "").strip()
    hook = str(plan.get("hook") or last.get("outcome") or last.get("event") or "").strip()
    result["goal"] = goal
    result["reader_experience"] = str(plan.get("reader_experience") or goal).strip()
    result["conflict"] = conflict
    result["hook"] = hook
    result["characters"] = [
        str(item).strip() for item in (plan.get("characters") or []) if str(item).strip()
    ]
    opening = plan.get("opening") if isinstance(plan.get("opening"), dict) else {}
    result["opening"] = {
        "situation": str(opening.get("situation") or first.get("location") or first.get("event") or "").strip(),
        "pressure": str(opening.get("pressure") or first.get("obstacle") or "").strip(),
        "first_action": str(opening.get("first_action") or first.get("event") or "").strip(),
    }
    budget = plan.get("progression_budget") if isinstance(plan.get("progression_budget"), dict) else {}
    unresolved = str(budget.get("must_remain_open") or "").strip()
    if not unresolved:
        unresolved = "仍未解决：" + str(plan.get("conflict") or conflict or hook).strip()
    result["progression_budget"] = {
        "chapter_function": str(
            budget.get("chapter_function") or plan.get("function") or "deepen"
        ).strip(),
        "single_local_change": str(
            budget.get("single_local_change") or last.get("outcome") or hook
        ).strip(),
        "event_span": str(
            budget.get("event_span") or "本章只展开当前事件的一段，必要时允许后续多章继续同一件事"
        ).strip(),
        "must_remain_open": unresolved,
        "forbidden_leaps": [
            str(item).strip() for item in (budget.get("forbidden_leaps") or []) if str(item).strip()
        ] or ["不完成下一章任务", "不跨地图或势力层级", "不同时完成能力、关系与真相三种跃迁"],
    }
    return result


async def review_chapter_plan(
    *,
    premise: str,
    chapter_sequence: int,
    previous_summary: str,
    story_context: str,
    volume_context: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    prompt = (
        f"故事核心：{premise}\n章节：第{chapter_sequence}章\n前情：{previous_summary}\n"
        f"首卷规划：{volume_context}\n人物与设定：{story_context}\n\n"
        f"待审章纲：{json.dumps(plan, ensure_ascii=False)}\n\n"
        "你是小说章节责任编辑。核对：本章是否只使用此时人物能知道的信息；是否严格遵守首卷给本章的任务，"
        "没有提前泄露后续证据、关系或真相；物证判断是否需要先查证，人物是否拥有所写知识和权限；"
        "每个场景是否由前一场结果触发，转折是否来自人物选择而非主动招供或巧合；人物关系是否符合熟人常识；"
        "开场与各场景中的人物到场时间、地点、道具来源是否互相一致，道具是否属于人物且能自然取得；"
        "章末是否来自本章未解决压力而非装饰画面，是否偷加首卷禁止的监控、神秘消息或新阴谋。"
        "重点核对推进速度：本章是否只有一个局部目标和一种主要状态变化；是否同时完成查证、升级、关系转折、"
        "身份变化或地图扩张中的多项；是否把本该用数章积累的信任、证据或能力压进一章。"
        "只要存在先有结论后补验证、跨字段矛盾、道具来源不明、提前泄底、关系常识错误、"
        "无动机招供、越权取证或擅自增加谜团，必须判fail。输出JSON："
        '{"verdict":"pass"|"fail","score":number,"blocking_issues":'
        '[{"location":string,"problem":string,"repair_direction":string}],'
        '"non_blocking_issues":[string],"strengths":[string]}'
    )
    raw = await llm_client.complete(
        "你是独立于章纲策划的小说责任编辑。字段齐全不等于故事合理，必须按可写性和信息节奏审查。",
        prompt,
        "json",
    )
    review = json.loads(raw)
    if not isinstance(review, dict) or not review.get("verdict"):
        raise ValueError("invalid chapter plan review")
    return review


async def generate_chapter_plan(
    *,
    book_title: str,
    premise: str,
    chapter_sequence: int,
    previous_summary: str,
    story_context: str = "",
    volume_context: str = "",
    style_profile: dict[str, Any] | None = None,
    author_instruction: str = "",
    current_plan: dict[str, Any] | None = None,
    target_words: int = 1_000_000,
) -> dict[str, Any]:
    planning_models = _planning_models()
    attempt_models = planning_models if len(planning_models) > 1 else planning_models * 2
    style_contract = (style_profile or {}).get("writing_contract", style_profile or {})
    author_constitution = (style_profile or {}).get("author_constitution", {})
    revision_context = (
        f"当前已采用章纲：{json.dumps(current_plan, ensure_ascii=False)}\n"
        f"作者本次修改要求（最高优先级）：{author_instruction.strip()}\n"
        "这是修改章纲：保留作者未要求改变的关键事件、连续性与写作边界，只调整明确要求的部分。\n\n"
        if author_instruction.strip() and current_plan
        else ""
    )
    regeneration_rule = (
        "这是全新重规划：不要沿用之前采用的章纲，也不要试图还原建书时预想的逐章事件；"
        "只服从已发生正文事实、卷级目标、禁揭晓项和作者创作宪章。\n\n"
        if current_plan and not author_instruction.strip()
        else ""
    )
    prompt = (
        f"书名：《{book_title}》\n故事核心：{premise}\n"
        f"当前章节：第{chapter_sequence}章\n前情：{previous_summary or '故事刚刚开始'}\n"
        f"连载篇幅策略：{_serial_scale_strategy(target_words, chapter_sequence)}\n"
        f"本卷方向：{volume_context or '围绕故事核心自然推进'}\n"
        f"人物与设定：{story_context or '以故事核心为准'}\n"
        f"本书写作方式：{json.dumps(style_contract, ensure_ascii=False)}\n\n"
        f"作者创作宪章：{json.dumps(author_constitution, ensure_ascii=False)}\n\n"
        f"{revision_context}"
        f"{regeneration_rule}"
        "像连载网文作者一样先判断这一章为什么必须存在，再设计读者看得懂、写手能直接落笔的情节。"
        "本章必须用人物选择和后果回应作者宪章中的想留下的感受与每章验收问题，禁止用旁白说教代替。"
        "章纲不是四字标签和抽象策划术语；不得把事件写成‘接规矩’‘稳住局面’‘关系升温’。"
        "根据当前连载需要选择章节功能：orient负责让读者认清人物与处境，deepen负责加深理解，"
        "attempt负责一次有限尝试，complicate负责让既有问题更难，partial_payoff用于局部兑现。"
        "本章只需让眼前局面产生清楚的局部变化；重大不可逆选择只放在小情节、卷或阶段高潮。"
        "如果一个事件需要多章讲清，就把本章设计成该事件的一段：进入、试探、受阻、误判、谈判、追索、余波或局部兑现。"
        "先给本章划定推进预算：只允许一个局部目标、确认一个主要新事实、造成一种主要状态变化，并写清该事件还要不要延续到后续章节。"
        "能力增长、关系改变、真相揭露、身份变化、地图/势力升级五类中，本章最多实质推进一类；其他只可留下摩擦或疑问。"
        "即使本章目标成功，也只能得到下一步行动条件，不能顺手解决上层问题。失败也必须产生具体余波，不能用新案件替换旧问题。"
        "建书时预想的前几章逐章方向不是硬约束，不得为了迁就旧草案而违背已写正文或作者本次要求。"
        "不得完成后续章节、卷中点或卷末任务；protected_reveals 中的内容本章绝不能揭晓。"
        "承接前章最后已经发生的结果，不能让人物失忆或重新开场。"
        "根据题材选择适合的章节形态，可以是试探、发现、交易、追逐、关系拉扯、失败余波或艰难决定，"
        "不要机械制造反转，不要每章都用同一种开头和钩子。根据章节功能设计1至8段连续情节："
        "短的章节可以只有一次谈话、一次试探或一个失败余波；长的章节可以在同一地点停留多段，不要为了凑段数换地图。"
        "让作者只看 event 就知道这一段该写什么，不要为了填字段把一个动作拆成许多策划术语。"
        "event 必须用15至80字写成完整事件句，明确人物在具体地点采取什么行动、对方如何反应、局面发生什么变化；"
        "普通读者只看 event 就应能复述本章发生了什么。第一场要让人立刻知道视角人物是谁、在哪里、想做什么、"
        "什么东西打断了正常状态。相邻情节必须有清楚因果，禁止靠巧合换场。"
        "只规划视角人物当下能知道的内容；历史题材禁止用未来史实替人物保证判断正确。"
        "总输出不超过2200个中文字符。输出 JSON："
        '{"title_candidates":[string,string,string],"reader_experience":string,'
        '"goal":string,"conflict":string,"characters":[string],'
        '"opening":{"situation":string,"pressure":string,"first_action":string},'
        '"progression_budget":{"chapter_function":"orient|deepen|attempt|complicate|partial_payoff",'
        '"single_local_change":string,"event_span":string,"must_remain_open":string,"forbidden_leaps":[string]},'
        '"beats":[{"segment":string,"location":string,"characters":[string],'
        '"event":string,"obstacle":string,"outcome":string}],'
        '"hook":string,"ending_image":string,"must_avoid":[string]}'
    )
    last_error: Exception | None = None
    retry_feedback = ""
    for planning_model in attempt_models:
        try:
            raw = await llm_client.complete(
                "你是长篇小说策划，帮助只读过小说的新手把想法拆成能动笔的一章。",
                prompt + retry_feedback,
                "json",
                model=planning_model,
                max_tokens=2500,
                timeout_seconds=60,
                request_attempts=1,
            )
            result = _normalize_chapter_plan(_unwrap_json_object(raw, "plan", "chapter_plan", "data"))
            reasons = _chapter_plan_rejection_reasons(result)
            if not reasons:
                result["quality_review"] = {
                    "verdict": "pass",
                    "score": 90,
                    "blocking_issues": [],
                    "reviewer": "local-writeability-check",
                }
                return result
            last_error = ValueError("；".join(reasons))
            retry_feedback = "\n上次章纲不可直接写作：" + "；".join(reasons) + "。逐条修正，不得改掉本章任务。"
        except Exception as exc:
            last_error = exc
            retry_feedback = "\n上次输出失败。严格守住首卷信息节奏，并优先保证JSON完整。"
    if isinstance(last_error, httpx.HTTPError | TimeoutError):
        raise RuntimeError("AI 章纲服务暂时繁忙，请稍后再试") from last_error
    raise RuntimeError("AI 没有返回可用的章纲，请重新生成") from last_error


async def generate_chapter_plan_window(
    *,
    book_title: str,
    premise: str,
    start_sequence: int,
    count: int,
    previous_summary: str,
    story_context: str,
    volume_context: str,
    style_profile: dict[str, Any] | None = None,
    target_words: int = 1_000_000,
) -> list[dict[str, Any]]:
    """Plan a causal rolling window in one call so adjacent chapters form one progression."""
    settings = get_settings()
    end_sequence = start_sequence + count - 1
    style_contract = (style_profile or {}).get("writing_contract", style_profile or {})
    author_constitution = (style_profile or {}).get("author_constitution", {})
    prompt = (
        f"书名：《{book_title}》\n故事核心：{premise}\n"
        f"规划范围：第{start_sequence}章至第{end_sequence}章\n"
        f"前情：{previous_summary or '故事刚刚开始'}\n本卷方向：{volume_context}\n"
        f"连载篇幅策略：{_serial_scale_strategy(target_words, start_sequence)}\n"
        f"人物、当前状态与待推进线索：{story_context}\n"
        f"写作方式：{json.dumps(style_contract, ensure_ascii=False)}\n"
        f"作者创作宪章：{json.dumps(author_constitution, ensure_ascii=False)}\n\n"
        "这是长篇小说的滚动阅读窗口，不是十个互不相关的点子，也不是十章跑完一卷。"
        "同一个事件可以占用多章：一章进入现场，一章试探失败，一章追索证据，一章处理余波。"
        "每章必须承接上一章的结果，但一次只推进有限一步。按需要使用orient、deepen、attempt、complicate、"
        "partial_payoff五种章节功能；重大不可逆选择属于小情节或卷高潮，不得强迫每章支付巨大代价。"
        "读者每章都必须知道跟着谁、在哪里、人物眼前想做什么、为什么下一件事会发生。"
        "开篇窗口前三章聚焦主角、前五章最多两个地点、每章最多确认一个主要新信息；"
        "不得提前解决本卷终局，也不得泄露protected_reveals。不要连续使用陌生消息、偶遇、昏迷、偷听等巧合钩子。"
        "每章都必须写progression_budget：只允许一个局部目标、一个主要新事实和一种主要状态变化；"
        "能力、关系、真相、身份、地图/势力五类进展每章最多实质推进一类，并明确章末仍未解决的问题。"
        "相邻章节不能轮流抛出新任务；下一章必须先消化上一章留下的动作、误解、损失或关系余波。"
        "每章按功能设计1至8个连续情节段，event要写清谁在何处做什么、遭遇什么反应、局面怎样改变；"
        "不要让每章都完整完成一个任务，也不要为了凑结构强行安排反转、底牌或地图切换。"
        "title必须是可直接使用的小说章名。只输出JSON，章节数量和序号必须严格匹配："
        '{"chapters":[{"chapter_sequence":number,"title":string,"reader_experience":string,'
        '"function":"orient"|"deepen"|"attempt"|"complicate"|"partial_payoff",'
        '"reader_orientation":string,"goal":string,"conflict":string,"characters":[string],'
        '"protagonist_change":{"start":string,"desire":string,"decision":string,"cost":string,"end":string},'
        '"opening":{"situation":string,"pressure":string,"first_action":string},'
        '"progression_budget":{"chapter_function":"orient|deepen|attempt|complicate|partial_payoff",'
        '"single_local_change":string,"event_span":string,"must_remain_open":string,"forbidden_leaps":[string]},'
        '"beats":[{"segment":string,"location":string,"characters":[string],"event":string,'
        '"obstacle":string,"outcome":string}],"hook":string,"ending_image":string,"must_avoid":[string]}]}'
    )
    models = [settings.llm_planning_model or settings.llm_model]
    if settings.llm_planning_fallback_model and settings.llm_planning_fallback_model not in models:
        models.append(settings.llm_planning_fallback_model)
    if settings.llm_model not in models:
        models.append(settings.llm_model)
    last_error: Exception | None = None
    for model in models if len(models) > 1 else models * 2:
        try:
            raw = await llm_client.complete(
                "你是长篇连载小说的执行主编，擅长把一段故事拆成连续、可写、可调整的十章。",
                prompt,
                "json",
                model=model,
                max_tokens=7000,
            )
            payload = _unwrap_json_object(raw, "data", "chapter_plan_window")
            items = payload.get("chapters") if isinstance(payload, dict) else None
            if not isinstance(items, list) or len(items) != count:
                raise ValueError("滚动章纲数量不正确")
            normalized: list[dict[str, Any]] = []
            for offset, item in enumerate(items):
                expected = start_sequence + offset
                if not isinstance(item, dict) or int(item.get("chapter_sequence") or 0) != expected:
                    raise ValueError(f"第{expected}章序号缺失")
                title = str(item.get("title") or "").strip()
                plan = _normalize_chapter_plan({**item, "title_candidates": [title]})
                reasons = _chapter_plan_rejection_reasons(plan)
                if not title or reasons:
                    raise ValueError(f"第{expected}章不可用：{'；'.join(reasons) or '缺少标题'}")
                normalized.append({"chapter_sequence": expected, "title": title, "plan": plan})
            return normalized
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"AI 没有返回完整的{count}章连续章纲，请重新生成") from last_error


def _volume_review_passes(review: Any) -> bool:
    return (
        isinstance(review, dict)
        and review.get("verdict") == "pass"
        and isinstance(review.get("score"), int | float)
        and review["score"] >= 82
        and not review.get("blocking_issues")
    )


async def review_volume_plan(seed: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        f"已确认全书蓝图：{json.dumps(seed, ensure_ascii=False)}\n\n"
        f"待审首卷规划：{json.dumps(plan, ensure_ascii=False)}\n\n"
        "你是长篇小说责任编辑。核对卷纲是否忠于已确认的真实因果、人物关系、证据顺序和结局代价；"
        "是否擅自增加幕后人物、新案件、新谜团或改变谁做了什么；前三章是否每章只推进有限一步，"
        "没有让人物无理由招供；普通主角取得材料的方式是否合法自然；章末吸引力是否来自当前人物压力，"
        "而不是陌生短信、神秘来信或突然监听。只要改写核心真相、前三章泄完答案、取证越权或卷末另开阴谋，"
        "必须判fail。输出JSON："
        '{"verdict":"pass"|"fail","score":number,"blocking_issues":'
        '[{"location":string,"problem":string,"repair_direction":string}],'
        '"non_blocking_issues":[string],"strengths":[string]}'
    )
    raw = await llm_client.complete(
        "你是独立的小说卷纲责任编辑。先守住已确认蓝图，再判断节奏和追读感。",
        prompt,
        "json",
    )
    review = json.loads(raw)
    if not isinstance(review, dict) or not review.get("verdict"):
        raise ValueError("invalid volume review")
    return review


async def generate_volume_plan(seed: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        f"新书信息：{json.dumps(seed, ensure_ascii=False)}\n\n"
        "规划第一卷这一叙事阶段。先按全书目标字数估算总章数与卷长，不得把百万字小说按短篇速度推进。"
        "内容简洁，总输出控制在1800个中文字符内，"
        "已确认的真实因果、人物行为、证据顺序和结局代价都是硬设定，不得改写，不得新增幕后人物或第二案件。"
        "第一卷不是用前三章解释清楚世界，也不是十章跑完一个完整案件/副本/关系闭环；"
        "一个开篇麻烦可以连续占用多章，每章只推进进入、试探、受阻、误判、追索、余波中的一段。"
        "开篇三章每章最多确认一项新事实，持续聚焦主角与一个主要地点；单章只需完成定位、加深、尝试、"
        "复杂化或局部兑现中的一种功能，不强迫每章发生大选择或支付巨大代价。"
        "后一个场景必须由前一个结果触发。人物不能为推进剧情主动招供，材料获取必须符合主角身份。"
        "卷末吸引力来自本案结局的情感余波或人物新处境，不得用陌生短信、神秘来信或新阴谋强开下一案。"
        "字符串内禁止未转义的英文双引号，必须保证JSON完整闭合。输出 JSON："
        '{"title":string,"goal":string,"opening":string,"turning_points":[string],'
        '"climax":string,"ending_hook":string,"suggested_chapters":number,'
        '"first_three_chapters":[{"sequence":number,"title":string,"goal":string,'
        '"conflict":string,"key_event":string,"choice":string,"cost":string,'
        '"state_change":string,"ending_hook":string}]}'
    )
    last_error: Exception | None = None
    retry_feedback = ""
    for _attempt in range(2):
        try:
            raw = await llm_client.complete(
                "你是长篇网文主编，擅长把已确认的全书蓝图拆成忠实、清晰、能够展开的第一卷。",
                prompt + retry_feedback,
                "json",
                max_tokens=2200,
            )
            result = json.loads(raw)
            chapters = result.get("first_three_chapters") if isinstance(result, dict) else None
            required = ("goal", "conflict", "key_event", "choice", "cost", "state_change", "ending_hook")
            if (
                not isinstance(result, dict)
                or not result.get("goal")
                or not isinstance(chapters, list)
                or len(chapters) != 3
                or not all(
                    isinstance(chapter, dict) and all(chapter.get(field) for field in required)
                    for chapter in chapters
                )
            ):
                raise ValueError("卷纲字段不完整")
            review = await review_volume_plan(seed, result)
            if _volume_review_passes(review):
                result["quality_review"] = review
                return result
            issues = [
                f"{item.get('location', '卷纲')}：{item.get('problem', '')}；修正：{item.get('repair_direction', '')}"
                for item in (review.get("blocking_issues") or [])
                if isinstance(item, dict)
            ]
            last_error = ValueError("; ".join(issues) or f"卷纲审稿仅{review.get('score', 0)}分")
            retry_feedback = "\n上次卷纲审稿未通过：" + ("；".join(issues) or str(last_error)) + "。逐条修正。"
        except Exception as exc:
            last_error = exc
            retry_feedback = "\n上次输出失败。请保持已确认蓝图不变，并优先保证JSON完整。"
    raise RuntimeError("AI 连续两次没有生成合格的第一卷规划，请稍后再试") from last_error


def _blueprint_rejection_reasons(result: Any, categories: list[str]) -> list[str]:
    if not isinstance(result, dict):
        return ["没有返回全书蓝图"]
    required = (
        "title_candidates",
        "synopsis",
        "protagonist_desire",
        "story_engine",
        "main_conflict",
        "stakes",
        "endgame",
        "major_arcs",
    )
    missing = [field for field in required if not result.get(field)]
    if missing:
        return [f"蓝图缺少字段：{'、'.join(missing)}"]
    arcs = result["major_arcs"]
    if not isinstance(arcs, list) or len(arcs) != 3:
        return ["全书必须有三段主线"]
    reasons: list[str] = []
    if not result.get("story_question"):
        reasons.append("蓝图缺少贯穿全书的故事问题")
    if "悬疑" not in categories:
        return reasons
    if any(marker in result["protagonist_desire"] for marker in ("查清真相", "调查", "破案", "换完楼道灯")):
        reasons.append("主角长线欲望不能只是调查任务")
    if any(marker in result["endgame"] for marker in ("不牵连", "两全", "皆大欢喜", "突破路径")):
        reasons.append("结局不能用两全办法逃掉核心代价")
    if not all(
        isinstance(arc, dict) and all(arc.get(field) for field in ("title", "goal", "turn", "choice", "cost", "result"))
        for arc in arcs
    ):
        reasons.append("每段主线都要写明主角的选择和代价")
    case_design = result.get("case_design")
    if not isinstance(case_design, dict) or not all(
        case_design.get(field) for field in ("central_question", "surface_explanation", "actual_truth", "final_choice")
    ):
        reasons.append("悬疑蓝图缺少明确谜面、表层解释、真实因果、证据链或最终选择")
        return reasons
    evidence_ladder = case_design.get("evidence_ladder")
    if not isinstance(evidence_ladder, list) or len(evidence_ladder) < 4 or not all(
        isinstance(item, dict)
        and all(
            item.get(field)
            for field in ("evidence", "verification", "initial_meaning", "revised_meaning", "consequence")
        )
        for item in evidence_ladder
    ):
        reasons.append("证据链至少4步，且每步必须可核验、会改变解释并产生后果")
    final_choice = case_design.get("final_choice")
    if not isinstance(final_choice, dict) or not all(
        final_choice.get(field) for field in ("options", "decision", "sacrifice")
    ):
        reasons.append("最终选择必须写明选项、决定和不可回避的牺牲")
    return reasons


def _normalize_book_blueprint(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    arcs = result.get("major_arcs")
    if isinstance(arcs, dict):
        ordered = [arcs.get(key) for key in ("stage_1_opening", "stage_2_expansion", "stage_3_endgame")]
        if all(isinstance(arc, dict) for arc in ordered):
            result = {**result, "major_arcs": ordered}
        else:
            result = {**result, "major_arcs": [arc for arc in arcs.values() if isinstance(arc, dict)]}
    return result


def _blueprint_review_passes(review: Any) -> bool:
    return (
        isinstance(review, dict)
        and review.get("verdict") == "pass"
        and isinstance(review.get("score"), int | float)
        and review["score"] >= 82
        and not review.get("blocking_issues")
    )


async def review_book_blueprint(payload: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    categories = payload.get("primary_categories") or [payload.get("primary_category", "")]
    is_suspense = "悬疑" in categories
    review_focus = (
        "逐项核验：1. 物理过程和职业常识是否真实；2. 主角是否有合法、现实、可写进场景的证据获取方式；"
        "3. 每条证据能否推出所写结论，是否只是相关性冒充因果；4. 人物行动是否来自自身欲望，"
        "而不是为发线索服务；5. 三段升级是否围绕同一核心问题且不会靠重复查账拖篇幅；"
        "6. 结局是否真的支付前文承诺的代价。只要核心物证不成立、普通人无权取证、"
        "真实因果含糊或靠巧合取得证据，必须判 fail。"
        if is_suspense else
        "逐项核验：1. 三段主线是否分别改变人物处境和冲突层级，而非重复同一种任务；"
        "2. 主角每次升级是否来自可写进场景的行动、选择与代价；3. 关键人物是否有自己的欲望，"
        "能持续合作、阻挠或反噬主角；4. 故事机制能否支撑目标篇幅且不会沦为机械循环；"
        "5. 中后期局面是否由前期选择自然升级；6. 结局是否兑现称霸、关系或成长承诺。"
        "只要三段同质、关键人物无作用、升级没有代价或终局凭空发生，必须判 fail。"
    )
    verdict_fields = (
        ',"factual_feasibility":string,"causality_verdict":string,"evidence_access_verdict":string'
        if is_suspense else
        ',"arc_progression_verdict":string,"character_agency_verdict":string,"serial_engine_verdict":string'
    )
    prompt = (
        f"创作要求：{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"待审蓝图：{json.dumps(blueprint, ensure_ascii=False)}\n\n"
        "你是严苛的小说责任编辑，不改写蓝图，只找会让后续写作失败的硬伤。"
        f"{review_focus}不能因为字段齐全给高分。"
        "输出JSON："
        '{"verdict":"pass"|"fail","score":number,"blocking_issues":'
        '[{"location":string,"problem":string,"why_it_breaks":string,"repair_direction":string}],'
        '"non_blocking_issues":[string],"strengths":[string],'
        f'"review_summary":string{verdict_fields}}}'
    )
    raw = await llm_client.complete(
        "你是独立于策划作者的长篇小说责任编辑。宁可退稿，也不放过因果、人物和连载结构硬伤。",
        prompt,
        "json",
    )
    review = json.loads(raw)
    if not isinstance(review, dict) or not review.get("verdict"):
        raise ValueError("invalid blueprint review")
    return review


async def generate_book_blueprint(payload: dict[str, Any]) -> dict[str, Any]:
    from app.engine.worldbuilder import validate_character_agency, validate_world_engine

    world_engine = payload.get("world_engine") or {}
    if world_engine:
        world_issues = validate_world_engine(
            world_engine,
            str((payload.get("primary_categories") or [payload.get("primary_category", "")])[0]),
            strict=True,
        )
        if world_issues:
            raise RuntimeError("世界发动机尚未通过校验：" + "；".join(world_issues))
    characters = payload.get("characters") or []
    if characters and any(validate_character_agency(item) for item in characters if isinstance(item, dict)):
        raise RuntimeError("人物缺少欲望、方法、底线或压力下的主动行为，不能进入路线规划")
    categories = payload.get("primary_categories") or [payload.get("primary_category", "")]
    suspense_requirements = ""
    suspense_schema = ""
    if "悬疑" in categories:
        suspense_requirements = (
            "悬疑题材额外要求：主角欲望必须是调查之外的具体生活目标，调查会威胁它。"
            "先确定唯一真实因果，再安排至少4步公平证据链；每项证据写清现实核验方法、初看含义、"
            "后来如何被新证据改写，以及它逼人物做出的行动。不能靠整栋楼共同串供、万能利益链、"
            "死者生前威胁举报或突然出现的证据推进。三段主线每段都以主角主动选择和实际损失收束。"
            "结尾必须兑现核心代价，禁止找到不牵连亲近者的两全漏洞。"
        )
        suspense_schema = (
            ',"case_design":{"central_question":string,"surface_explanation":string,"actual_truth":string,'
            '"evidence_ladder":[{"evidence":string,"verification":string,"initial_meaning":string,'
            '"revised_meaning":string,"consequence":string}],'
            '"final_choice":{"options":string,"decision":string,"sacrifice":string}}'
        )
    prompt = (
        f"用户已选故事与定位：{json.dumps(payload, ensure_ascii=False)}\n\n"
        "在写第一卷前，生成一份能支撑滚动创作的方向蓝图。不要堆术语，每项都让普通读者看懂。"
        "世界规则是硬边界，不得另造一套体系。书名给3个候选；全书只给开局、扩张、终局三个方向锚点，"
        "不预写具体章节，不制造三套故事。各阶段必须推动同一个核心故事问题并改变局面。"
        "三段的主要冲突和胜利条件必须不同，前一段付出的代价要成为后一段的限制；"
        "关键人物必须凭自己的欲望推动、阻挠或反噬主角，不能让系统奖励直接解决全部问题。"
        f"{suspense_requirements}简介不超过120字，其余字符串尽量不超过80字，标签不超过6个，"
        "卖点3条、风险2条，总输出不超过3000个中文字符。输出JSON："
        '{"title_candidates":[string,string,string],"synopsis":string,"audience":string,'
        '"category":string,"tags":[string],"reader_promise":string,"story_question":string,'
        '"protagonist_desire":string,"protagonist_flaw":string,"story_engine":string,'
        '"main_conflict":string,"stakes":string,"endgame":string,'
        '"major_arcs":{'
        '"stage_1_opening":{"title":string,"goal":string,"turn":string,"choice":string,"cost":string,"result":string},'
        '"stage_2_expansion":{"title":string,"goal":string,"turn":string,"choice":string,"cost":string,"result":string},'
        '"stage_3_endgame":{"title":string,"goal":string,"turn":string,"choice":string,"cost":string,"result":string}},'
        f'"selling_points":[string,string,string],"risk_warnings":[string,string]{suspense_schema}}}。'
        "字符串内引用名称只用中文引号，禁止未转义的英文双引号，必须保证JSON完整闭合。"
    )
    last_error: Exception | None = None
    retry_feedback = ""
    for _attempt in range(2):
        try:
            raw = await llm_client.complete(
                "你是成熟的长篇网文总编，帮助只会读小说的新手把阅读直觉变成可持续、连贯且有市场坐标的原创故事。",
                prompt + retry_feedback,
                "json",
                max_tokens=3500,
            )
            result = _normalize_book_blueprint(json.loads(raw))
            rejection_reasons = _blueprint_rejection_reasons(result, categories)
            if rejection_reasons:
                last_error = ValueError("; ".join(rejection_reasons))
                retry_feedback = "\n上次蓝图被拒绝，原因：" + "；".join(rejection_reasons) + "。本次逐条修正。"
                continue
            return result
        except httpx.TimeoutException:
            last_error = RuntimeError("上游模型响应超时")
            retry_feedback = "\n上次请求超时。本次严格压缩表达，优先保证 JSON 完整，不扩写解释。"
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else 502
            last_error = RuntimeError(f"上游模型暂时不可用（HTTP {status_code}）")
            retry_feedback = "\n上次上游服务暂时不可用。本次保持输出简洁并重试。"
        except Exception as exc:
            last_error = exc
            retry_feedback = "\n上次输出无法解析。本次优先保证字段齐全且JSON完整闭合。"
    reason = str(last_error) if last_error else "返回内容不完整"
    raise RuntimeError(f"全书路线仍需调整：{reason}") from last_error


async def generate_reader_feedback(
    chapter_content: str,
    preceding_summary: str,
    chapter_plan: dict[str, Any] | None = None,
    canon_context: str = "",
    track_info: str | None = None,
    taste_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Run an evidence-backed editorial audit; unsupported model claims are discarded."""
    prompt = (
        f"赛道：{track_info or '未指定赛道'}\n目标读者口味：{'、'.join(taste_tags or []) or '通用读者'}\n\n"
        f"前情概要：{preceding_summary[:1000]}\n\n"
        f"已确认章纲：{json.dumps(chapter_plan or {}, ensure_ascii=False)}\n"
        f"世界与人物当前事实：{canon_context[:3000]}\n\n"
        f"本章正文：\n{chapter_content[:12000]}\n\n"
        "你是小说责任编辑，执行可复核的章节审查，不模拟读者、不打追读分。逐项检查："
        "章纲兑现、因果连续、人物主动性、人物知识边界、世界设定连续性、对话与叙述行为、章末承诺。"
        "POV是叙事参考而非机械禁令：动作、表情、停顿、语气和身体反应都是外部可观察信息，"
        "描写这些内容或由视角人物据此猜测，不能判为视角越界。只有明确断言非视角人物未说出的思想、"
        "记忆或秘密知识时才可提出POV建议，而且POV建议不得blocking。只有人物使用不可能知道的信息采取行动，"
        "才属于可阻断的知识边界问题。"
        "只报告会影响理解、人物可信度或后续连续性的具体问题。每个问题必须引用正文中逐字连续出现的原句，"
        "quote不得改写、拼接或使用省略号。blocking仅用于事实矛盾、因果断裂、人物使用不可能知道的信息采取行动、"
        "章纲关键任务未完成等硬伤；任何POV或视角建议都不得blocking。"
        "输出JSON："
        '{"verdict":"pass"|"needs_revision","summary":string,"checks":['
        '{"category":string,"status":"pass"|"warning"|"fail","finding":string,'
        '"quote":string,"reason":string,"suggestion":string,"blocking":boolean}]}'
    )
    result: dict[str, Any] | None = None
    last_error: Exception | None = None
    models = _planning_models()[:3]
    if len(models) == 1:
        models.append(models[0])
    for attempt, model in enumerate(models, start=1):
        retry_instruction = (
            "\n\n上一次返回无法解析。本次只能返回一个完整 JSON 对象，"
            "不要输出思考过程、Markdown、代码围栏或 JSON 以外的文字。"
            if attempt > 1
            else ""
        )
        try:
            raw = await llm_client.complete(
                "你是严谨的小说责任编辑。没有原文证据就不提出问题，绝不虚构引文。",
                prompt + retry_instruction,
                "json",
                model=model,
                max_tokens=3000,
                temperature=0.1,
            )
            result = parse_json_object(raw)
            if not isinstance(result.get("checks"), list):
                raise ValueError("checks 不是数组")
            break
        except Exception as exc:
            last_error = exc
            logger.warning(
                "章节检查结构化响应失败，第 %s 次，模型=%s，错误=%s",
                attempt,
                model,
                type(exc).__name__,
            )
    if result is None:
        raise RuntimeError("章节检查没有返回可核验结果") from last_error
    if not isinstance(result, dict) or not isinstance(result.get("checks"), list):
        raise RuntimeError("章节检查没有返回可核验结果")
    checks = []
    for item in result["checks"]:
        if not isinstance(item, dict):
            continue
        status_value = item.get("status")
        quote = str(item.get("quote") or "").strip()
        if status_value in {"warning", "fail"} and (not quote or quote not in chapter_content):
            continue
        pov_text = " ".join(
            str(item.get(field) or "") for field in ("category", "finding", "reason")
        )
        is_pov_finding = "POV" in pov_text.upper() or "视角" in pov_text
        if is_pov_finding and status_value in {"warning", "fail"}:
            explicit_interiority = any(
                marker in quote
                for marker in (
                    "心想", "暗想", "暗道", "意识到", "内心", "心里", "想起",
                    "记起", "觉得", "认为", "确信", "知道自己", "明白自己",
                )
            )
            if not explicit_interiority:
                continue
            item = {**item, "status": "warning", "blocking": False, "hard_category": None}
        if status_value == "pass":
            quote = ""
        checks.append({**item, "quote": quote, "blocking": bool(item.get("blocking"))})
    blocking = [item for item in checks if item.get("blocking") and item.get("status") == "fail"]
    suggestions = [item for item in checks if item.get("status") in {"warning", "fail"} and item not in blocking]
    verdict = "needs_revision" if blocking else "pass"
    summary = (
        f"发现 {len(blocking)} 项有正文证据的连续性硬伤。"
        if blocking
        else f"未发现阻断性问题；有 {len(suggestions)} 项可选建议。"
        if suggestions
        else "未发现阻断性问题。"
    )
    return {
        "verdict": verdict,
        "summary": summary,
        "checks": checks,
    }


async def generate_light_chapter_edits(
    chapter_content: str,
    instruction: str,
    *,
    focus: list[str] | None = None,
    preserve: list[str] | None = None,
) -> list[dict[str, str]]:
    """Generate verified local replacements without invoking the full chapter pipeline."""
    prompt = (
        f"修改要求：{instruction.strip()}\n"
        f"重点：{'、'.join(focus or []) or '按要求局部修改'}\n"
        f"必须保留：{'、'.join(preserve or []) or '情节事实、人物关系和段落顺序'}\n\n"
        f"正文：\n{chapter_content[:16000]}\n\n"
        "只做必要的局部修改，不重写整章，不改变未被要求修改的句子。"
        "输出 JSON 对象：{\"edits\":[{\"find\":正文中逐字连续出现且唯一的原文,"
        "\"replace\":替换后的文字,\"reason\":修改理由}]}。最多12处。"
        "find 必须与正文逐字一致，不得用省略号，不得拼接不相邻句子。没有必要修改时 edits 返回空数组。"
    )
    models = _planning_models()[:2]
    if len(models) == 1:
        models.append(models[0])
    last_error: Exception | None = None
    for attempt, model in enumerate(models, start=1):
        try:
            raw = await llm_client.complete(
                "你是小说文字编辑，只提交可以机械应用的局部替换，不重新创作整章。",
                prompt + ("\n上次格式不可用，本次只返回完整 JSON 对象。" if attempt > 1 else ""),
                "json",
                model=model,
                max_tokens=2200,
                temperature=0.1,
            )
            payload = parse_json_object(raw)
            candidates = payload.get("edits")
            if not isinstance(candidates, list):
                raise ValueError("edits 不是数组")
            working = chapter_content
            accepted: list[dict[str, str]] = []
            affected_chars = 0
            affected_limit = min(max(len(chapter_content) // 3, 400), 2400)
            for item in candidates[:12]:
                if not isinstance(item, dict):
                    continue
                find = str(item.get("find") or "")
                replace = str(item.get("replace") or "")
                reason = str(item.get("reason") or "").strip()
                if not find or find == replace or working.count(find) != 1:
                    continue
                if len(find) > 600 or len(replace) > max(len(find) * 3, 900):
                    continue
                if affected_chars + len(find) > affected_limit:
                    continue
                working = working.replace(find, replace, 1)
                affected_chars += len(find)
                accepted.append({"find": find, "replace": replace, "reason": reason})
            return accepted
        except Exception as exc:
            last_error = exc
            logger.warning("轻量章节优化响应失败，第 %s 次，模型=%s，错误=%s", attempt, model, type(exc).__name__)
    raise RuntimeError("快速修改没有返回可应用的结果") from last_error


async def generate_health_check(
    db: AsyncSession,
    project_id: Any,
    chapter_range_start: int,
    chapter_range_end: int,
) -> dict[str, Any]:
    """Generate a periodic health check for a range of chapters."""
    from app.models import Chapter, Foreshadowing, ReaderFeedback

    # Gather reader feedback scores
    feedbacks = list((await db.scalars(
        select(ReaderFeedback).where(
            ReaderFeedback.project_id == project_id,
            ReaderFeedback.chapter_sequence >= chapter_range_start,
            ReaderFeedback.chapter_sequence <= chapter_range_end,
        )
    )).all())

    scores = [f.chase_score for f in feedbacks if f.chase_score is not None]
    avg_score = sum(scores) / len(scores) if scores else 0

    # Foreshadowing status
    active_foreshadows = list((await db.scalars(
        select(Foreshadowing).where(
            Foreshadowing.project_id == project_id,
            Foreshadowing.status == "active",
        )
    )).all())
    resolved = list((await db.scalars(
        select(Foreshadowing).where(
            Foreshadowing.project_id == project_id,
            Foreshadowing.status == "resolved",
            Foreshadowing.resolved_chapter >= chapter_range_start,
        )
    )).all())

    # Count chapters and thrill points
    chapters = list((await db.scalars(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_sequence >= chapter_range_start,
            Chapter.chapter_sequence <= chapter_range_end,
            Chapter.status.in_(["draft", "confirmed"]),
        )
    )).all())

    total_thrills = sum(
        f.thrill_analysis.get("thrill_count", 0) for f in feedbacks
        if isinstance(f.thrill_analysis, dict)
    )
    chapter_count = max(1, len(chapters))
    thrill_per_chapter = total_thrills / chapter_count

    # Generate AI suggestions
    summary_text = (
        f"章节范围：第{chapter_range_start}-{chapter_range_end}章\n"
        f"平均追读分：{avg_score:.0f}\n"
        f"爽点密度：每章{thrill_per_chapter:.1f}个\n"
        f"未收伏笔：{len(active_foreshadows)}个\n"
        f"已收伏笔：{len(resolved)}个"
    )

    try:
        raw = await llm_client.complete(
            "你是一个网文写作教练，根据数据给出改进建议。",
            f"数据：\n{summary_text}\n\n给出3条具体的改进建议，每条一句话。输出JSON数组：[string, string, string]",
            "json",
        )
        suggestions = json.loads(raw)
        if not isinstance(suggestions, list):
            suggestions = []
    except Exception:
        suggestions = ["保持当前节奏", "考虑回收一个伏笔", "下一卷引入新角色"]

    pacing = "节奏良好" if avg_score >= 7 else "节奏尚可，建议加快" if avg_score >= 4 else "节奏偏慢，需要调整"
    consistency_issues = []
    if len(active_foreshadows) > 5:
        consistency_issues.append(f"有{len(active_foreshadows)}个伏笔未收回，建议适时回收")
    if thrill_per_chapter < 0.5 and chapter_count > 3:
        consistency_issues.append("爽点密度偏低，建议增加冲突或转折")

    return {
        "overall_score": round(avg_score, 1),
        "pacing_verdict": pacing,
        "consistency_issues": consistency_issues,
        "improvement_suggestions": suggestions,
    }


async def generate_chapter_directions(
    chapter_content: str,
    context_summary: str,
    genre: str,
) -> list[dict[str, str]]:
    """Generate 3 possible directions for the next chapter."""
    prompt = (
        f"类型：{genre}\n"
        f"前情：{context_summary[:1500]}\n"
        f"上一章结尾：\n{chapter_content[-1500:]}\n\n"
        "为下一章生成3个不同方向，输出JSON数组：\n"
        '[{"title": "方向名称", "description": "详细描述", '
        '"pros": "这样写的好处", "cons": "这样写的风险"}]'
    )

    try:
        raw = await llm_client.complete(
            "你是一个网文写作顾问，擅长设计情节走向。每个方向要有明确差异。",
            prompt,
            "json",
        )
        directions = json.loads(raw)
        if isinstance(directions, list):
            return directions[:3]
    except Exception:
        pass

    return [
        {"title": "正面冲突", "description": "主角直面挑战", "pros": "爽感强", "cons": "节奏可能太快"},
        {"title": "暗中布局", "description": "主角收集情报暗中准备", "pros": "铺垫充分", "cons": "可能显得拖沓"},
        {"title": "意外转折", "description": "新势力介入打破僵局", "pros": "出人意料", "cons": "需要合理伏笔"},
    ]


async def generate_stuck_help(
    chapter_content: str,
    context_summary: str,
    genre: str,
) -> dict[str, list[str]]:
    """Generate writing tips and inspiration prompts for stuck writers."""
    prompt = (
        f"类型：{genre}\n"
        f"前情：{context_summary[:1500]}\n"
        f"最新内容：\n{chapter_content[-1000:]}\n\n"
        "作者卡文了，请给出建议。输出JSON：\n"
        '{"tips": ["写作建议1", "写作建议2", "写作建议3"], '
        '"inspiration_prompts": ["灵感触发问题1", "灵感触发问题2"]}'
    )

    try:
        raw = await llm_client.complete(
            "你是一个资深写作教练，擅长帮助网文作者突破瓶颈。",
            prompt,
            "json",
        )
        result = json.loads(raw)
        return {
            "tips": result.get("tips", [])[:5],
            "inspiration_prompts": result.get("inspiration_prompts", [])[:5],
        }
    except Exception:
        return {
            "tips": ["试试换一个角色的视角来写", "回顾之前埋下的伏笔", "给主角制造一个意外障碍"],
            "inspiration_prompts": ["如果这时候出现一个新角色会怎样？", "主角最害怕什么？让它发生"],
        }


def _method_context(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep RAG advice compact and separate from the story's canonical facts."""
    return [
        {
            "title": card.get("title", "写作方法"),
            "principle": card.get("principle", ""),
            "procedure": card.get("procedure", []),
            "checks": card.get("checks", []),
            "anti_patterns": card.get("anti_patterns", []),
        }
        for card in cards[:4]
    ]


def _unwrap_json_object(raw: str, *keys: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("模型返回了空内容")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise ValueError("模型没有返回可识别的 JSON") from None
        try:
            value, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError as exc:
            raise ValueError("模型返回的 JSON 不完整") from exc
    if not isinstance(value, dict):
        raise ValueError("模型没有返回 JSON 对象")
    for key in keys:
        nested = value.get(key)
        if isinstance(nested, dict):
            return nested
    return value


def _planning_models() -> list[str]:
    settings = get_settings()
    return list(
        dict.fromkeys(
            filter(
                None,
                (
                    settings.llm_planning_model or settings.llm_model,
                    f"aliyun:{settings.llm_aliyun_planning_model or settings.llm_aliyun_model}"
                    if settings.llm_aliyun_planning_model or settings.llm_aliyun_model
                    else None,
                    f"deepseek:{settings.llm_deepseek_model}"
                    if settings.llm_deepseek_model
                    else None,
                    *settings.llm_planning_fallback_models,
                    settings.llm_planning_fallback_model,
                    settings.llm_model,
                    *settings.llm_fallback_models,
                    settings.llm_fallback_model,
                ),
            )
        )
    )


def _scale_facts(target_words: int) -> dict[str, int]:
    estimated_chapters = max(60, min(2500, round(target_words / 3300)))
    planned_volumes = max(3, min(20, estimated_chapters // 50))
    per_volume, remainder = divmod(estimated_chapters, planned_volumes)
    first_volume_end = per_volume + (1 if remainder else 0)
    return {
        "target_words": target_words,
        "estimated_chapters": estimated_chapters,
        "planned_volumes": planned_volumes,
        "average_chapters_per_volume": round(estimated_chapters / planned_volumes),
        "first_volume_end": first_volume_end,
        "opening_window_chapters": 10,
    }


def _serial_scale_strategy(target_words: int | None, chapter_sequence: int | None = None) -> str:
    words = int(target_words or 1_000_000)
    chapter = int(chapter_sequence or 1)
    if words >= 2_000_000:
        scale = (
            "几百万字长篇：一个事件、一次调查、一段关系变化可以跨多章展开；"
            "单章通常只写一个可理解的现场片段、一次试探、一次失败余波或一次局部兑现。"
            "前30章只建立主角方法、生活秩序、核心关系和第一层压力，不抢跑卷中点。"
        )
    elif words >= 800_000:
        scale = (
            "百万字长篇：一个小情节可用3至8章完成；单章只让眼前局面清楚变化，"
            "不把查证、升级、关系转折和新地图同时塞进一章。"
        )
    else:
        scale = "中短篇尺度：可以更紧凑，但仍必须保证读者看懂人物处境、目标、阻力和因果。"
    opening = (
        "当前仍属开篇阅读窗口：优先让读者看懂人物、地点、眼前目标、规则如何作用；"
        "不得为了追求高潮把本该铺垫数章的信任、证据、能力或关系一次写完。"
        if chapter <= 30
        else "当前已过开篇，可根据已发生正文滚动推进，但每章仍只承担一个主要叙事功能。"
    )
    return scale + opening


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _ensure_items(items: list[str], defaults: list[str], *, min_count: int, max_count: int) -> list[str]:
    result = list(dict.fromkeys([*items, *defaults]))
    return result[:max_count] if len(result) >= min_count else result[:max_count]


def _foundation_quality_rejection_reasons(value: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    """Reject empty/template output without policing the author's subject matter."""
    reasons: list[str] = []
    world = value.get("world") if isinstance(value.get("world"), dict) else {}
    protagonist = value.get("protagonist") if isinstance(value.get("protagonist"), dict) else {}
    first_volume = value.get("first_volume") if isinstance(value.get("first_volume"), dict) else {}
    opening_window = value.get("opening_window") if isinstance(value.get("opening_window"), dict) else {}
    required_fields = [
        ("世界核心规则", world.get("core_rule"), 12),
        ("世界社会秩序", world.get("social_order"), 12),
        ("世界代价", world.get("cost"), 12),
        ("开篇地点", world.get("opening_locality"), 6),
        ("主角开场处境", protagonist.get("starting_state"), 14),
        ("主角眼前欲望", protagonist.get("desire"), 10),
        ("主角惯用办法", protagonist.get("method"), 10),
        ("第一卷局部目标", first_volume.get("volume_goal"), 12),
    ]
    for label, raw, min_len in required_fields:
        text = str(raw or "").strip()
        if len(text) < min_len:
            reasons.append(f"{label}太短或太空，必须写成读者能想象的具体处境/规则")

    if payload.get("section") in {None, "creative_brief"}:
        brief = value.get("creative_brief")
        if not isinstance(brief, list) or len(brief) < 3:
            reasons.append("动态创作蓝图至少需要3个真正服务这本书的条目")
        else:
            generic_markers = ("具体困境", "重要的人或事", "真正珍视的东西", "更深一层", "连续压力")
            if any(
                any(marker in str(item.get("content") or "") for marker in generic_markers)
                for item in brief if isinstance(item, dict)
            ):
                reasons.append("动态创作蓝图仍是通用占位话，没有写出本书独有的人、地点、规则或冲突")

    directions = opening_window.get("chapter_directions")
    if isinstance(directions, list):
        placeholder_markers = ("读者要明白", "新增信息", "主角采取行动", "眼前问题", "局部后果", "某个")
        for item in directions[:3]:
            if not isinstance(item, dict):
                continue
            chapter_text = json.dumps(item, ensure_ascii=False)
            if any(marker in chapter_text for marker in placeholder_markers):
                reasons.append("前三章方向仍像模板占位，必须写出具体人、地点、麻烦、动作和后果")
                break
    return reasons


def _normalize_foundation_defaults(value: dict[str, Any], payload: dict[str, Any], scale_facts: dict[str, int]) -> None:
    """Coerce recoverable model omissions so one weak list does not block creation."""
    idea = str(payload.get("idea") or "").strip() or "一个人物在压力中做出选择，并为选择承担后果。"
    selected_genres = payload.get("genres") or ([payload.get("genre")] if payload.get("genre") else [])
    genre = " / ".join(str(item) for item in selected_genres if item) or "长篇"
    core = value.get("core") if isinstance(value.get("core"), dict) else {}
    title_candidates = _as_text_list(core.get("title_candidates"))
    core.setdefault("title_candidates", title_candidates or ["未命名长篇", "因果之书", "风起之时"])
    core.setdefault("premise", idea[:500])
    core.setdefault("reader_promise", str(payload.get("reader_wish") or "看人物用行动改变局面，并承受代价。"))
    core.setdefault("central_question", "主角能否在压力升级中守住自己的选择？")
    core.setdefault("emotional_core", "人在困局中重新确认自己真正珍视的东西。")
    core.setdefault("ending_direction", "主角获得改变局面的资格，同时接受无法轻易抹去的代价。")
    value["core"] = core

    engine = value.get("engine") if isinstance(value.get("engine"), dict) else {}
    engine.setdefault("engine_type", "人物选择驱动")
    engine.setdefault("primary_genre", genre.split(" / ")[0])
    engine.setdefault("long_term_loop", "每次解决眼前问题，都会暴露更深一层的代价与机会。")
    engine["progression_dimensions"] = _ensure_items(
        _as_text_list(engine.get("progression_dimensions")),
        ["能力", "关系", "资源", "认知"],
        min_count=2,
        max_count=5,
    )
    engine.setdefault("escalation_rule", "从个人困境扩展到关系、势力与世界规则的连续压力。")
    value["engine"] = engine

    scale_plan = value.get("scale_plan") if isinstance(value.get("scale_plan"), dict) else {}
    scale_plan.update(scale_facts)
    scale_plan["progression_ladders"] = _ensure_items(
        _as_text_list(scale_plan.get("progression_ladders")),
        ["个人能力", "关系信任", "资源掌控", "规则解释权"],
        min_count=2,
        max_count=6,
    )
    scale_plan["pacing_boundaries"] = _ensure_items(
        _as_text_list(scale_plan.get("pacing_boundaries")),
        [
            "前10章只建立主角、地点、眼前目标与最少规则",
            "第一卷只完成第一个局部目标，不揭开终局真相",
            "每一卷只跨越一个主要竞争层级",
            "重大关系变化必须由连续行动铺垫",
        ],
        min_count=4,
        max_count=10,
    )
    value["scale_plan"] = scale_plan

    world = value.get("world") if isinstance(value.get("world"), dict) else {}
    world.setdefault("genre_flavor", f"{genre}世界：有自己的地域、势力、资源、规矩和普通人的生活方式。")
    world.setdefault("power_system", "人物改变处境依赖可训练、可交换或可争夺的能力/资源，不靠凭空奖励。")
    world.setdefault("factions", "开篇只出现与主角眼前困境有关的一两个势力，其余势力暂放幕后。")
    world.setdefault("geography", "从一个读者能记住的开篇地点开始，再随关系和压力扩大舞台。")
    world.setdefault("daily_life", "普通人按资源、身份、承诺和人情办事，规则会影响吃穿住行与机会。")
    world.setdefault("history_pressure", "旧规则留下的债、仇、承诺或资源分配问题，正在压到主角眼前。")
    world.setdefault("core_rule", "选择会改变资源、关系与可用道路。")
    world.setdefault("social_order", "人们按资源、承诺与实力形成稳定秩序。")
    world.setdefault("scarce_resource", "能真正改变处境的机会。")
    world.setdefault("cost", "每次借力都会留下可被追索的代价。")
    world.setdefault("opening_locality", "主角熟悉但正在失控的日常地点。")
    world["visible_rules"] = _ensure_items(
        _as_text_list(world.get("visible_rules")),
        ["承诺必须付出代价", "资源会改变人与人的位置"],
        min_count=1,
        max_count=8,
    )
    world["reserve"] = _as_text_list(world.get("reserve"))[:8]
    value["world"] = world

    protagonist = value.get("protagonist") if isinstance(value.get("protagonist"), dict) else {}
    protagonist.setdefault("name", str(payload.get("protagonist_name") or "主角"))
    protagonist.setdefault("gender", str(payload.get("protagonist_gender") or "未限定"))
    protagonist.setdefault("starting_state", "正处在一个必须立刻处理的具体困境中。")
    protagonist.setdefault("desire", "保住眼前最重要的人或事。")
    protagonist.setdefault("fear", "发现自己坚持的东西并不可靠。")
    protagonist.setdefault("belief", "问题只要查清楚就能解决。")
    protagonist.setdefault("method", "从具体痕迹与人的反应里寻找突破口。")
    protagonist.setdefault("bottom_line", "不把无关者当成代价。")
    protagonist.setdefault("contradiction", "想掌控局面，却必须依赖别人给出的不完整信息。")
    value["protagonist"] = protagonist

    creative_brief = value.get("creative_brief")
    value["creative_brief"] = (
        [item for item in creative_brief if isinstance(item, dict)][:12]
        if isinstance(creative_brief, list)
        else []
    )

    first_volume = value.get("first_volume") if isinstance(value.get("first_volume"), dict) else {}
    first_volume.update({"sequence": 1, "chapter_range": [1, scale_facts["first_volume_end"]]})
    first_volume.setdefault("title", "第一卷")
    first_volume.setdefault("reader_promise", core["reader_promise"])
    first_volume.setdefault("starting_state", protagonist["starting_state"])
    first_volume.setdefault("volume_goal", "完成第一个能被读者看见的局部目标。")
    first_volume.setdefault("central_pressure", "规则看似合理，但会持续压缩主角选择空间。")
    first_volume.setdefault("midpoint_change", "主角发现原先理解的冲突只是真问题的一部分。")
    first_volume.setdefault("climax_choice", "主角公开承担一个代价，换取继续追查或推进的资格。")
    first_volume.setdefault("ending_state", "眼前问题被改写，但主角被卷入更大的规则。")
    first_volume.setdefault("progression_gain", "获得继续行动的资格、线索或资源。")
    first_volume.setdefault("relationship_change", "关键关系从单纯对立变成带条件的合作或试探。")
    first_volume["protected_reveals"] = _ensure_items(
        _as_text_list(first_volume.get("protected_reveals")),
        ["终局真相", "幕后核心动机", "主角命运的最终代价"],
        min_count=2,
        max_count=8,
    )
    value["first_volume"] = first_volume

    value["characters"] = list(value.get("characters") or [])[:4] if isinstance(value.get("characters"), list) else []
    value["stages"] = list(value.get("stages") or []) if isinstance(value.get("stages"), list) else []
    value.setdefault("opening_window", {})


def _fallback_story_foundation(payload: dict[str, Any], scale_facts: dict[str, int]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _normalize_foundation_defaults(value, payload, scale_facts)
    value["stages"] = [
        {
            "name": "开局立足",
            "chapter_range": [1, max(1, scale_facts["estimated_chapters"] // 4)],
            "starting_state": value["protagonist"]["starting_state"],
            "goal": "完成第一个局部目标并取得继续行动的资格。",
            "pressure": "眼前规则持续压缩主角选择空间。",
            "irreversible_choice": "主角承担一个公开代价，换取继续推进。",
            "changed_state": "主角从被动应对变成主动追索。",
            "promise_payoff": "读者看到主角的方法有效，但代价真实存在。",
        },
        {
            "name": "扩大局面",
            "chapter_range": [
                max(1, scale_facts["estimated_chapters"] // 4) + 1,
                max(2, scale_facts["estimated_chapters"] * 3 // 4),
            ],
            "starting_state": "主角取得局部资格，但更大的规则开始反制。",
            "goal": "进入更高层级的冲突并争取解释权。",
            "pressure": "旧关系、资源与规则同时提出代价。",
            "irreversible_choice": "主角放弃一个安全选择，保护关键线索或关系。",
            "changed_state": "主角获得更大舞台，也成为更明确的目标。",
            "promise_payoff": "能力、关系与认知同步升级。",
        },
        {
            "name": "改写规则",
            "chapter_range": [
                max(2, scale_facts["estimated_chapters"] * 3 // 4) + 1,
                scale_facts["estimated_chapters"],
            ],
            "starting_state": "主角拥有影响局面的资格，但旧代价集中爆发。",
            "goal": "完成核心承诺并改写最初困住人物的规则。",
            "pressure": "受益者与亲近者都不愿轻易接受改变。",
            "irreversible_choice": "主角承认自身也被旧规则塑造，并选择承担最终后果。",
            "changed_state": "新规则成立，主角接受无法回到原点。",
            "promise_payoff": "兑现读者等待的选择、代价与余味。",
        },
    ]
    value["opening_window"] = {
        "title": "",
        "chapter_range": [1, 10],
        "purpose": "",
        "reader_anchor": "",
        "local_goal": "",
        "scope_boundary": "",
        "ending_change": "",
        "introduced_characters": [],
        "introduced_rules": [],
        "chapter_directions": [],
    }
    _normalize_foundation_stage_ranges(value, scale_facts["estimated_chapters"])
    return value


def _normalize_foundation_stage_ranges(value: dict[str, Any], estimated_chapters: int) -> None:
    """Scale the model's relative phase lengths into one exact, gap-free book range."""
    stages = value.get("stages")
    if not isinstance(stages, list) or not stages or not all(isinstance(stage, dict) for stage in stages):
        return
    weights: list[int] = []
    for stage in stages:
        chapter_range = stage.get("chapter_range")
        if (
            isinstance(chapter_range, list)
            and len(chapter_range) == 2
            and all(isinstance(item, int) and not isinstance(item, bool) for item in chapter_range)
            and chapter_range[1] >= chapter_range[0]
        ):
            weights.append(chapter_range[1] - chapter_range[0] + 1)
        else:
            weights.append(1)

    total_weight = sum(weights)
    start = 1
    cumulative_weight = 0
    for index, (stage, weight) in enumerate(zip(stages, weights, strict=True)):
        cumulative_weight += weight
        remaining_stages = len(stages) - index - 1
        if remaining_stages == 0:
            end = estimated_chapters
        else:
            proportional_end = round(estimated_chapters * cumulative_weight / total_weight)
            end = max(start, min(proportional_end, estimated_chapters - remaining_stages))
        stage["chapter_range"] = [start, end]
        start = end + 1


def _foundation_rejection_reasons(value: dict[str, Any], target_words: int = 1_000_000) -> list[str]:
    from app.schemas import CreationFoundation

    try:
        foundation = CreationFoundation.model_validate(value)
    except Exception as exc:
        return [f"结构不完整：{exc}"]
    reasons: list[str] = []
    facts = _scale_facts(target_words)
    scale = foundation.scale_plan
    expected_scale = {
        "target_words": facts["target_words"],
        "estimated_chapters": facts["estimated_chapters"],
        "planned_volumes": facts["planned_volumes"],
        "average_chapters_per_volume": facts["average_chapters_per_volume"],
        "opening_window_chapters": facts["opening_window_chapters"],
    }
    for field, expected in expected_scale.items():
        if getattr(scale, field) != expected:
            reasons.append(f"篇幅尺度错误：{field}必须为{expected}")

    stages = foundation.stages
    if stages:
        if stages[0].chapter_range[0] != 1 or stages[-1].chapter_range[1] != facts["estimated_chapters"]:
            reasons.append("长线阶段必须从第1章连续覆盖到全书预计末章")
        if any(
            current.chapter_range[1] + 1 != following.chapter_range[0]
            for current, following in zip(stages, stages[1:], strict=False)
        ):
            reasons.append("长线阶段的章节范围必须连续且不重叠")

    if foundation.first_volume.chapter_range != [1, facts["first_volume_end"]]:
        reasons.append(f"第一卷范围必须为第1至{facts['first_volume_end']}章")
    directions = foundation.opening_window.chapter_directions
    if directions:
        if [item.sequence for item in directions] != list(range(1, len(directions) + 1)):
            reasons.append("当前阅读窗口必须从第1章连续排列")
        if len({item.title for item in directions}) != len(directions):
            reasons.append("前期章节不能使用重复标题")
        if directions[0].function != "orient":
            reasons.append("第一章必须先完成读者定位，function应为orient")
        if any(item.function == "partial_payoff" for item in directions[: max(4, len(directions) // 2)]):
            reasons.append("当前窗口前半段不能过早完成局部兑现")
        if directions[-1].function not in {"complicate", "partial_payoff"}:
            reasons.append("窗口末章应局部兑现或制造清晰的新复杂化")
        if any(item.focus_character != foundation.protagonist.name for item in directions[:3]):
            reasons.append("前三章必须持续聚焦主角，不能切换其他人物视角")
        if len({item.location for item in directions[:5]}) > 2:
            reasons.append("前五章最多使用两个地点，先让读者认清开篇舞台")
    else:
        reasons.append("前10章方向尚未补全（characters/stages/opening_window 已可单独生成）")
    # chapter_range 与 chapter_directions 始终对齐：默认空时不强校验
    if foundation.opening_window.chapter_range != [1, max(1, len(directions))]:
        reasons.append("当前阅读窗口范围必须与目录章数一致")
    names = [foundation.protagonist.name, *(item.name for item in foundation.characters)]
    if len(set(names)) != len(names):
        reasons.append("主角与关键人物不能重名，characters 不要重复主角")
    if directions and foundation.opening_window.ending_change == foundation.first_volume.ending_state:
        reasons.append("十章阅读窗口不能提前完成第一卷结局")
    opening_text = json.dumps(
        {
            "ending_change": foundation.opening_window.ending_change,
            "directions": [item.model_dump() for item in directions],
        },
        ensure_ascii=False,
    )
    fast_forward_markers = (
        "终极反派", "最终真相", "彻底击败", "统一天下", "登临巅峰", "完成复仇", "飞升成仙", "世界毁灭",
    )
    leaked = [marker for marker in fast_forward_markers if marker in opening_text]
    if leaked:
        reasons.append(f"前十章推进过快，出现了终局内容：{'、'.join(leaked)}")
    if foundation.world.core_rule.strip() == foundation.world.cost.strip():
        reasons.append("世界规则与使用代价不能是同一句空泛描述")
    return reasons


async def generate_story_foundation(
    payload: dict[str, Any],
    method_cards: list[dict[str, Any]],
    *,
    scope: str = "full",
) -> dict[str, Any]:
    """Co-design world, people and plot as one causal system.

    scope="full"   ：一次性生成 core/engine/world/主角/scale/first_volume/characters/stages/opening_window。
    scope="core"   ：只生成核心 + 引擎 + 世界 + 主角 + 尺度 + 第一卷；characters/stages/opening_window
                    留空，由用户每节单独调用 generate_foundation_section 补全。
    """
    selected_genres = payload.get("genres") or ([payload.get("genre")] if payload.get("genre") else [])
    genre = " / ".join(str(item) for item in selected_genres if item) or "由故事自然判断"
    target_words = int(payload.get("target_words") or 1_000_000)
    scale_facts = _scale_facts(target_words)
    if scope not in {"full", "core"}:
        scope = "full"

    if scope == "core":
        # core 模式：只问六大块，characters/stages/opening_window 直接空数组占位
        json_schema = (
            '{"core":{"title_candidates":[string],"premise":string,"reader_promise":string,'
            '"central_question":string,"emotional_core":string,"ending_direction":string},'
            '"engine":{"engine_type":string,"primary_genre":string,"long_term_loop":string,'
            '"progression_dimensions":[string],"escalation_rule":string},'
            '"scale_plan":{"target_words":number,"estimated_chapters":number,"planned_volumes":number,'
            '"average_chapters_per_volume":number,"opening_window_chapters":number,'
            '"progression_ladders":[string],"pacing_boundaries":[string]},'
            '"world":{"genre_flavor":string,"power_system":string,"factions":string,"geography":string,'
            '"daily_life":string,"history_pressure":string,"core_rule":string,"social_order":string,"scarce_resource":string,"cost":string,'
            '"opening_locality":string,"visible_rules":[string],"reserve":[string]},'
            '"protagonist":{"name":string,"gender":string,"starting_state":string,"desire":string,'
            '"fear":string,"belief":string,"method":string,"bottom_line":string,"contradiction":string},'
            '"creative_brief":[{"title":string,"content":string}],'
            '"characters":[],'
            '"stages":[],'
            '"first_volume":{"sequence":1,"title":string,"chapter_range":[1,number],"reader_promise":string,'
            '"starting_state":string,"volume_goal":string,"central_pressure":string,"midpoint_change":string,'
            '"climax_choice":string,"ending_state":string,"progression_gain":string,"relationship_change":string,'
            '"protected_reveals":[string]}}'
        )
    else:
        json_schema = (
            '{"core":{"title_candidates":[string],"premise":string,"reader_promise":string,'
            '"central_question":string,"emotional_core":string,"ending_direction":string},'
            '"engine":{"engine_type":string,"primary_genre":string,"long_term_loop":string,'
            '"progression_dimensions":[string],"escalation_rule":string},'
            '"scale_plan":{"target_words":number,"estimated_chapters":number,"planned_volumes":number,'
            '"average_chapters_per_volume":number,"opening_window_chapters":number,'
            '"progression_ladders":[string],"pacing_boundaries":[string]},'
            '"world":{"genre_flavor":string,"power_system":string,"factions":string,"geography":string,'
            '"daily_life":string,"history_pressure":string,"core_rule":string,"social_order":string,"scarce_resource":string,"cost":string,'
            '"opening_locality":string,"visible_rules":[string],"reserve":[string]},'
            '"protagonist":{"name":string,"gender":string,"starting_state":string,"desire":string,'
            '"fear":string,"belief":string,"method":string,"bottom_line":string,"contradiction":string},'
            '"creative_brief":[{"title":string,"content":string}],'
            '"characters":[{"name":string,"role":string,"desire":string,"method":string,'
            '"leverage":string,"relationship":string,"offstage_action":string}],'
            '"stages":[{"name":string,"chapter_range":[number,number],"starting_state":string,"goal":string,"pressure":string,'
            '"irreversible_choice":string,"changed_state":string,"promise_payoff":string}],'
            '"first_volume":{"sequence":1,"title":string,"chapter_range":[1,number],"reader_promise":string,'
            '"starting_state":string,"volume_goal":string,"central_pressure":string,"midpoint_change":string,'
            '"climax_choice":string,"ending_state":string,"progression_gain":string,"relationship_change":string,'
            '"protected_reveals":[string]}}'
        )

    if scope == "core":
        scope_directive = (
            "本次是初次建模，只生成：核心故事主张（core）、故事引擎（engine）、世界观（world）、主角九宫格、"
            "规模与第一卷。characters / stages / opening_window 必须为空数组（[]），"
            "后续由用户点击对应按钮逐节补全。不要替用户决定配角、阶段划分、前10章方向。"
        )
        validation_directive = ""
    else:
        scope_directive = "这是完整建模：核心、引擎、世界、人物、阶段、卷结构、前10章方向。"
        validation_directive = (
            "【强制要求】pacing_boundaries 必须至少4条；stages 必须至少3个阶段；characters 必须至少2人；"
            "progression_ladders 必须至少2条；protected_reveals 至少2条。缺一不可。"
        )

    prompt = (
        "作者原话（这是最高优先级，不要擅自换成更套路的故事）：\n"
        f"{payload.get('idea', '')}\n\n"
        f"类型倾向：{genre}\n频道倾向：{payload.get('channel') or '不限'}\n"
        f"不可更改的篇幅尺度：{json.dumps(scale_facts, ensure_ascii=False)}\n"
        f"希望读者获得：{payload.get('reader_wish') or '从作者原话推断，保持克制'}\n"
        f"明确不要：{payload.get('avoid_elements') or '无'}\n"
        f"文风参考（只提取叙事方法，不仿写句子）：{payload.get('style_reference') or '无'}\n"
        f"金手指设想：{payload.get('golden_finger') or '无'}\n"
        f"本次可用写作方法：{json.dumps(_method_context(method_cards), ensure_ascii=False)}\n\n"
        f"{scope_directive}\n"
        "只设计一部小说。世界、人物和故事必须在同一轮里互相约束，不要先写百科再硬塞情节。"
        "除书名和一句话故事外，不要把创作理解成填写固定设定表。creative_brief 是给作者确认的主界面："
        "请你根据这一本书的题材和作者原话，自行决定4至8个真正必要的条目及标题。武侠可以是江湖格局、武学与生计、"
        "主角处境、关键关系；言情可以是关系起点、双方需求、现实阻力、情感兑现；悬疑可以是案件表象、调查能力、嫌疑关系、信息边界。"
        "不要为了凑数使用统一模板，也不要出现'贯穿全书的问题''真正想留下的情绪'这类论文式栏目。每项content写成一段完整、具体、可修改的创作说明。"
        "先在内部形成一个统一的故事构思，再拆成creative_brief，禁止把人物、世界、爽点、阶段分别独立生成后拼接。"
        "所有条目必须围绕同一批具体人物、同一个开篇因果和同一种生活秩序互相咬合：人物的欲望从其生活处境中长出，"
        "能力或金手指改变他的做法，做法触碰他人的利益，后果再自然扩大关系和舞台。每个条目至少与另一个条目有明确因果关系。"
        "必须有本书独有的观察、人物矛盾和生活质感，让读者先相信这些人在过日子、做选择，再相信宏大世界和升级。"
        "长篇不是预填几百章事件；只确定不会轻易变化的灵魂、因果发动机和当前阶段方向，远期内容随已发生正文滚动校准。"
        "后台结构字段只是执行索引，内容必须与creative_brief一致。蓝图必须能直接服务正文，不要写概念口号。每个关键内容都要回答：读者第一章能看见什么、人物此刻为什么必须动、"
        "他的动作会撞上谁的利益、撞完以后局面怎么变。"
        "世界观要先像一个小说世界：如果是武侠，要有江湖规矩、门派/朝廷/帮会、武功资源、城镇驿路与普通人怎么过日子；"
        "如果是玄幻，要有修炼体系、宗门/王朝/禁地、资源分配、地域层级与凡人处境；其他类型也按自己的世界逻辑写清。"
        "不要只写一句抽象规则。规则必须通过人物办事、交易、求生、修炼、查案或关系拉扯自然显露。未知区域放入reserve，不提前解释。"
        "主角不是标签：不要只写变强、掌控、享受、复仇这类抽象欲望；必须写清开篇当天的具体压力、眼前目标、惯用解决办法、"
        "害怕失去的具体人/事，以及这个办法为什么会反噬他。"
        "人物不是履历卡：只保留开篇会主动做事的2至4名关键人物，characters不重复主角。"
        "系统、金手指和任何题材内容都按作者原话设计；本系统不审查、不替作者删改题材内容。只需保证它在故事中产生具体行动和后果。"
        "这是长篇连载，不是把短篇拉长。全书阶段只给远期方向；第一卷单独规划。"
        "几百万字规划要靠可重复变化的长线发动机：能力、关系、资源、认知、地盘/势力至少两条线交替推进；"
        "每卷只跨一个主要层级，靠已发生后果滚动扩展，不靠一开始塞满设定。"
        "重大不可逆选择只属于阶段、卷或小故事高潮，不能强迫每一章都付巨大代价。"
        "男频不以等级播报代替行动，女频不以误会拖延代替关系推进；均禁止性别刻板印象。"
        "不要给自己评分，不要输出分析过程。"
        f"{validation_directive}"
        "输出JSON对象："
        f"{json_schema}"
    )
    models = _planning_models()
    attempts = models if len(models) > 1 else models * 2
    feedback = ""
    last_error: Exception | None = None
    logger.info("[foundation] 开始生成，模型列表=%s，prompt长度=%d", attempts, len(prompt))
    for idx, model in enumerate(attempts):
        try:
            logger.info("[foundation] 第%d次尝试，model=%s", idx + 1, model)
            raw = await llm_client.complete(
                "你是长篇小说的共同创作者兼故事总设计师。忠于作者心意，用因果和人物选择组织材料。只输出JSON。",
                prompt + feedback,
                "json",
                model=model,
                max_tokens=5000,
                stream=True,
                temperature=0.45,
            )
            logger.info("[foundation] LLM原始返回长度=%d, 前200字符=%r", len(raw), raw[:200])
            value = _unwrap_json_object(raw, "foundation", "data")
            # Scale is arithmetic, not a creative decision. Recover weak list
            # fields before validation so a mostly usable foundation is not discarded.
            _normalize_foundation_defaults(value, payload, scale_facts)
            if scope == "core":
                value["opening_window"] = {
                    "title": "",
                    "chapter_range": [1, 10],
                    "purpose": "",
                    "reader_anchor": "",
                    "local_goal": "",
                    "scope_boundary": "",
                    "ending_change": "",
                    "introduced_characters": [],
                    "introduced_rules": [],
                    "chapter_directions": [],
                }
            else:
                _normalize_foundation_stage_ranges(value, scale_facts["estimated_chapters"])
            opening_context = {
                key: value.get(key)
                for key in ("core", "world", "protagonist", "characters", "first_volume")
            }
            if scope == "core":
                # core 模式：跳过 opening_window / stages 补充生成，直接返回
                value["opening_window"] = {
                    "title": "",
                    "chapter_range": [1, 10],
                    "purpose": "",
                    "reader_anchor": "",
                    "local_goal": "",
                    "scope_boundary": "",
                    "ending_change": "",
                    "introduced_characters": [],
                    "introduced_rules": [],
                    "chapter_directions": [],
                }
                from app.schemas import CreationFoundation

                _normalize_foundation_defaults(value, payload, scale_facts)
                quality_reasons = _foundation_quality_rejection_reasons(value, payload)
                if quality_reasons:
                    raise ValueError("；".join(quality_reasons))
                return CreationFoundation.model_validate(value).model_dump()
            opening_prompt = (
                f"已确定的故事与第一卷：{json.dumps(opening_context, ensure_ascii=False)}\n\n"
                "现在先规划第1至5章，不改动上面的设定。它们只负责建立第一阅读窗口的前半段，"
                "负责让读者认住主角、地点、眼前目标与最少规则，不解决第一卷目标。"
                "同一个开篇麻烦可以在第1至5章连续展开：进入现场、第一次处理、发现不顺、关系受压、留下下一步。"
                "前三章聚焦主角，前五章最多两个地点，每章最多增加一个主要信息；"
                "不得partial_payoff，不得揭晓protected_reveals。每章只承担orient、deepen、attempt、complicate之一。"
                "第1章必须像正式正文的开场方案：一个具体时刻、一个具体地点、一个马上要处理的麻烦、"
                "主角一个符合身份的动作、对方一个有利益的回应、章末一个让读者明白下一章要看的后果。"
                "每章字段不要写'读者要明白/新增信息/主角采取行动'这类模板话，必须写具体事件。"
                "只输出JSON："
                '{"opening_window":{"title":string,"chapter_range":[1,10],"purpose":string,'
                '"reader_anchor":string,"local_goal":string,"scope_boundary":string,"ending_change":string,'
                '"introduced_characters":[string],"introduced_rules":[string],'
                '"chapter_directions":[{"sequence":number,"title":string,'
                '"function":"orient"|"deepen"|"attempt"|"complicate"|"partial_payoff",'
                '"focus_character":string,"location":string,"reader_orientation":string,'
                '"immediate_goal":string,"obstacle":string,"main_action":string,"information_gain":string,'
                '"relationship_movement":string,"immediate_consequence":string,"ending_beat":string}]}}'
            )
            opening_raw = await llm_client.complete(
                "你是长篇小说的开篇执行主编。让读者先看懂和在意人物，再逐步扩大故事。只输出JSON。",
                opening_prompt,
                "json",
                model=model,
                max_tokens=3200,
                stream=True,
                temperature=0.5,
            )
            opening_value = _unwrap_json_object(opening_raw, "opening_window", "data")
            if isinstance(opening_value.get("opening_window"), dict):
                opening_value = opening_value["opening_window"]
            first_half = opening_value.get("chapter_directions")
            if not isinstance(first_half, list) or len(first_half) != 5:
                raise ValueError("前五章阅读窗口数量必须为5")
            window_goal = {
                key: item for key, item in opening_value.items() if key != "chapter_directions"
            }
            latter_prompt = (
                f"已确定的故事与第一卷：{json.dumps(opening_context, ensure_ascii=False)}\n"
                f"已确定的第1至5章：{json.dumps(first_half, ensure_ascii=False)}\n"
                "阅读窗口目标："
                f"{json.dumps(window_goal, ensure_ascii=False)}\n\n"
                "继续规划第6至10章。必须承接第5章的局部后果，只完成一次有限尝试或局部兑现，"
                "不得解决第一卷目标、跳到卷中点、快速换地图或揭晓protected_reveals。"
                "如果第1至5章的开篇事件还没讲完，第6至10章应优先消化它的后果，而不是另开任务清单。"
                "第6至10章每章仍只增加一个主要信息；每一章都必须由上一章后果触发，"
                "让读者能顺着'所以/但是'读下去，不能像并列任务清单。只输出JSON："
                '{"chapter_directions":[{"sequence":number,"title":string,'
                '"function":"orient"|"deepen"|"attempt"|"complicate"|"partial_payoff",'
                '"focus_character":string,"location":string,"reader_orientation":string,'
                '"immediate_goal":string,"obstacle":string,"main_action":string,"information_gain":string,'
                '"relationship_movement":string,"immediate_consequence":string,"ending_beat":string}]}'
            )
            latter_raw = await llm_client.complete(
                "你是长篇小说的开篇执行主编。承接已有内容，克制推进，不提前消费长线故事。只输出JSON。",
                latter_prompt,
                "json",
                model=model,
                max_tokens=3200,
                stream=True,
                temperature=0.5,
            )
            latter_value = _unwrap_json_object(latter_raw, "data")
            latter_half = latter_value.get("chapter_directions")
            if not isinstance(latter_half, list) or len(latter_half) != 5:
                raise ValueError("后五章阅读窗口数量必须为5")
            opening_value["chapter_directions"] = [*first_half, *latter_half]
            opening_value["chapter_range"] = [1, 10]
            protagonist_name = str(value.get("protagonist", {}).get("name") or "").strip()
            opening_locality = str(value.get("world", {}).get("opening_locality") or "").strip()
            for direction in opening_value["chapter_directions"][:3]:
                if isinstance(direction, dict):
                    direction["focus_character"] = protagonist_name
            if opening_locality:
                for direction in opening_value["chapter_directions"][:5]:
                    if isinstance(direction, dict):
                        direction["location"] = opening_locality
            opening_value["introduced_characters"] = list(opening_value.get("introduced_characters") or [])[:3]
            opening_value["introduced_rules"] = list(opening_value.get("introduced_rules") or [])[:2]
            value["opening_window"] = opening_value
            value["characters"] = list(value.get("characters") or [])[:4]
            _normalize_foundation_defaults(value, payload, scale_facts)
            reasons = _foundation_rejection_reasons(value, target_words)
            reasons.extend(_foundation_quality_rejection_reasons(value, payload))
            if reasons:
                raise ValueError("；".join(reasons))
            from app.schemas import CreationFoundation

            return CreationFoundation.model_validate(value).model_dump()
        except Exception as exc:
            last_error = exc
            logger.warning("[foundation] 第%d次尝试失败: %s: %s", idx + 1, type(exc).__name__, exc)
            feedback = f"\n上次结果不可用：{exc}。只修复这些问题，仍然忠于作者原话并返回完整JSON。"
    logger.warning("[foundation] 所有模型尝试失败，不返回空话保底蓝图: %s", last_error)
    raise RuntimeError(f"故事蓝图生成失败，请重试：{last_error}") from last_error


# ──────────────────────────────────────────────────────────────────
# 单节补全：让用户能精准修改 / 重新生成故事的某一个面
# ──────────────────────────────────────────────────────────────────

_SECTION_PROMPTS: dict[str, str] = {
    "creative_brief": (
        "只回答对象 {creative_brief}。不要套固定设定表。根据作者原话和当前已有执行资料，"
        "自行选择4至8个这本书最值得作者确认的创作块。"
        "每项只有title和content；title由你按题材命名，content是一段具体完整的创作说明。不同题材必须得到不同栏目。"
        "先把整本书看成一个统一生命体再拆分栏目；各栏目必须共享具体人物、开篇因果和生活秩序，并说明彼此如何因果相连，不能分别生成后拼接。"
        "优先保留本书独有的人性矛盾、日常质感、叙事声音和可持续冲突，不要用抽象术语代替构思。"
        "作者写明的任何题材内容都保留，不做内容审查。输出JSON。"
    ),
    "engine": (
        "只回答对象 {engine}。基于已确定的核心与主角，重新设计："
        "故事引擎（爽点引擎 / 世界引擎 / 谜题引擎 / 关系引擎 之一）、"
        "故事主线循环（这一部全靠什么反复制造新局面）、主线进度维度（2至5个，比如等级/势力/关系线/解谜/资源）、"
        "怎样自然扩大舞台与代价。必须能支撑几百万字：每轮循环都要由人物行动、关系变化、资源争夺或认知更新触发新局面，"
        "不能只写升级、打脸、接任务。禁止与已确定的核心/主角/世界规则冲突。只输出JSON。"
    ),
    "world": (
        "只回答对象 {world}。已确定核心与主角，重新设计小说世界观。必须包含："
        "genre_flavor（这是怎样的武侠/玄幻/都市/仙侠/科幻等世界，一两句让读者有画面）、"
        "power_system（武功/修炼/异能/职业/财富/权力等力量体系怎样获得、怎样分层）、"
        "factions（门派、宗门、朝廷、家族、公司、帮会等主要势力怎样分布）、"
        "geography（开篇所在地域与外部更大舞台的层级关系）、daily_life（普通人怎么生活、怎么被规则影响）、"
        "history_pressure（旧仇、旧案、灾变、王朝/宗门/行业矛盾等正在压到当下的历史压力）、"
        "core_rule、social_order、scarce_resource、cost、opening_locality、visible_rules、reserve。"
        "世界观必须像读者能进入的生活秩序，不要写成主角专属外挂说明，也不要只有抽象道理。"
        "opening_locality 要具体到可开场的地点和正在发生的压力；visible_rules 必须是人物办事时会撞上的规则。"
        "如果有系统/金手指，只写它如何改变选择和代价，不把系统任务当剧情。"
        "禁止与已确定的主角的开场处境冲突。只输出JSON。"
    ),
    "scale_volume": (
        "只回答对象 {scale_plan + first_volume}。scale_plan 直接使用下方提供的尺度事实，"
        "在此基础上回答 pacing_boundaries（至少4条进度分界线，每条对应一次势力/认知/代价跃迁），"
        "progression_ladders（至少2条成长分层，例如战功/修为/声望/势力）。first_volume 必须从第1章开始，"
        "覆盖到下方事实给的第一卷末章，禁止后移；midpoint_change、climax_choice、ending_state "
        "必须对应具体选择而非描述，"
        "protected_reveals 至少2条且不可在本卷揭晓。只输出JSON。"
    ),
    "characters": (
        "只回答对象 {characters}。给主角加上2至3位开场5至10章内会实际登场的关键人物。"
        "characters 不重复主角。每人必有：name、role、desire（自己要什么）、method（怎么要）、"
        "leverage（手握什么筹码）、relationship（与主角/他人之间的具体相互制约）、offstage_action（离场后仍会推进什么）。"
        "禁止让配角在前10章就完成自身伏笔或主角等级跃迁。只输出JSON。"
    ),
    "stages": (
        "只回答对象 {stages}。基于已有的尺度事实，把全书的远期格局分成3至5个阶段。"
        "每个阶段必须有：name、chapter_range（起止章号）、starting_state（开篇状态）、goal（本阶段目的）、"
        "pressure（什么外力/内驱推着走）、irreversible_choice（这个阶段必须做的不可逆选择）、"
        "changed_state（结束时已不能回头的事实）、promise_payoff（本阶段兑现哪条读者期待）。"
        "阶段章节必须从第1章连续不重叠覆盖到末章。只输出JSON。"
    ),
    "opening_window": (
        "只回答对象 {opening_window}。已经知道主角、世界与第一卷目标，根据前10章的章方向（chapter_directions）补全："
        "title、purpose（这个阅读窗口的单一目的）、reader_anchor（让读者认准的人/地点/目标）、"
        "local_goal（局部目标）、scope_boundary（这个窗口不管什么）、ending_change（读完10章后世界回不到原样）、"
        "introduced_characters（最多3人）、introduced_rules（最多2条规则），以及 chapter_directions"
        "（必须为第1至10章，每章含 "
        "sequence/title/function=orient|deepen|attempt|complicate|partial_payoff/focus_character/location/"
        "reader_orientation/immediate_goal/obstacle/main_action/information_gain/relationship_movement/"
        "immediate_consequence/ending_beat）。第1至3章 focus_character 必须等于主角，前5章最多两个地点，"
        "不可解第一卷目标、揭晓伏笔、跳到卷中点。第1章必须让普通读者不懵：具体时刻、具体地点、眼前麻烦、"
        "主角动作、对方回应、立刻产生的后果都要清楚。第2章必须承接第1章后果，第3章承接第2章后果；"
        "不要写模板话，不要写'读者要明白/新增信息/主角采取行动'。只输出JSON。"
    ),
}


async def generate_foundation_section(
    payload: dict[str, Any],
    section: str,
) -> dict[str, Any]:
    """只补全故事根基的一个节，便于用户逐节精确控制。"""
    if section not in _SECTION_PROMPTS:
        raise ValueError(f"未知节名：{section}")

    current = payload.get("current") or {}
    if not isinstance(current, dict):
        current = {}
    target_words = int(payload.get("target_words") or 1_000_000)
    scale_facts = _scale_facts(target_words)
    selected_genres = payload.get("genres") or ([payload.get("genre")] if payload.get("genre") else [])
    genre = " / ".join(str(item) for item in selected_genres if item) or "由故事自然判断"

    system_prompt = (
        "你是长篇连载小说的执行主编。严格忠于已确定的核心和主角，只补全作者指定的那一节。"
        "输出必须能让下一步直接写正文：具体、可演、读者友好，不写模板口号。只输出该节对应的JSON对象。"
    )

    context_lines = [
        f"作者原话（最高优先级）：{payload.get('idea', '')}",
        f"类型倾向：{genre} · 频道：{payload.get('channel') or '不限'}",
        f"希望读者获得：{payload.get('reader_wish') or '由作者原话推断'}",
        f"明确不要：{payload.get('avoid_elements') or '无'}",
        f"文风参考（只学习叙事方法）：{payload.get('style_reference') or '无'}",
        f"金手指设想：{payload.get('golden_finger_hint') or '无'}",
    ]
    core = current.get("core") or {}
    if core:
        context_lines.append(f"已确定核心：{json.dumps(core, ensure_ascii=False)}")
    protagonist = current.get("protagonist") or {}
    if protagonist:
        context_lines.append(f"已确定主角：{json.dumps(protagonist, ensure_ascii=False)}")
    world = current.get("world") or {}
    if world:
        context_lines.append(f"已确定世界：{json.dumps(world, ensure_ascii=False)}")
    engine = current.get("engine") or {}
    if engine:
        context_lines.append(f"已确定引擎：{json.dumps(engine, ensure_ascii=False)}")
    scale_plan = current.get("scale_plan") or {}
    if scale_plan:
        context_lines.append(f"已确定尺度：{json.dumps(scale_plan, ensure_ascii=False)}")
    first_volume = current.get("first_volume") or {}
    if first_volume:
        context_lines.append(f"已确定第一卷：{json.dumps(first_volume, ensure_ascii=False)}")
    characters = current.get("characters") or []
    if characters:
        context_lines.append(f"已有配角：{json.dumps(characters, ensure_ascii=False)}")
    stages = current.get("stages") or []
    if stages:
        context_lines.append(f"已有阶段：{json.dumps(stages, ensure_ascii=False)}")
    opening_window = current.get("opening_window") or {}
    if opening_window:
        context_lines.append(f"已有前10章方向：{json.dumps(opening_window, ensure_ascii=False)}")
    context_lines.append(f"不可改的尺度事实：{json.dumps(scale_facts, ensure_ascii=False)}")

    if section == "scale_volume":
        # scale_plan 完全使用事实，不让模型重新挑数
        prompt = "\n".join(context_lines) + (
            "\n\nscale_plan 必须直接使用下方 facts，其他都不要改："
            f"{json.dumps(scale_facts, ensure_ascii=False)}\n"
            f"{_SECTION_PROMPTS[section]}\n"
            "输出JSON示例：{\"scale_plan\":{...含facts的同样键，加上progression_ladders,pacing_boundaries}"
            ",\"first_volume\":{\"sequence\":1,\"title\":string,\"chapter_range\":[1,"
            + str(scale_facts["first_volume_end"])
            + "],"
            "\"reader_promise\":string,\"starting_state\":string,\"volume_goal\":string,\"central_pressure\":string,"
            "\"midpoint_change\":string,\"climax_choice\":string,\"ending_state\":string,\"progression_gain\":string,"
            "\"relationship_change\":string,\"protected_reveals\":[string]}}"
        )
    else:
        prompt = "\n".join(context_lines) + ("\n\n" + _SECTION_PROMPTS[section])

    models = _planning_models()
    last_error: Exception | None = None
    for model in models:
        try:
            raw = await llm_client.complete(
                system_prompt,
                prompt,
                "json",
                model=model,
                max_tokens=2400,
                stream=True,
                temperature=0.5,
            )
            value = _unwrap_json_object(raw, section, "data")
            # 用 schema 校验/裁剪，让 patch 干净
            patch = _validate_section_patch(section, value)
            probe = dict(current)
            probe.update(patch)
            quality_reasons = _foundation_quality_rejection_reasons(probe, payload)
            if quality_reasons:
                raise ValueError("；".join(quality_reasons))
            return {"section": section, "patch": patch}
        except Exception as exc:
            last_error = exc
            logger.warning("[foundation-section] model=%s 失败: %s: %s", model, type(exc).__name__, exc)
            continue
    raise RuntimeError(f"补全{_SECTION_LABELS.get(section, section)}失败：{last_error}") from last_error


_SECTION_LABELS: dict[str, str] = {
    "creative_brief": "动态创作蓝图",
    "engine": "故事引擎",
    "world": "世界设定",
    "scale_volume": "规模与第一卷",
    "characters": "关键配角",
    "stages": "全书阶段方向",
    "opening_window": "前10章方向",
}


def _validate_section_patch(section: str, value: Any) -> dict[str, Any]:
    """把模型输出按 schema 裁剪，返回可直接 merge 的 patch。"""
    from app.schemas import (
        ChapterDirection,
        FirstVolume,
        FoundationBriefItem,
        FoundationCharacter,
        FoundationWorld,
        OpeningWindow,
        StoryEngine,
        StoryStage,
    )

    if not isinstance(value, dict):
        raise ValueError("模型返回不是对象")
    patch: dict[str, Any] = {}
    if section == "creative_brief":
        items = value.get("creative_brief")
        if not isinstance(items, list):
            items = value.get("data") if isinstance(value.get("data"), list) else []
        cleaned = [FoundationBriefItem.model_validate(item).model_dump() for item in items if isinstance(item, dict)]
        if len(cleaned) < 3:
            raise ValueError("至少给出3个动态创作蓝图条目")
        patch["creative_brief"] = cleaned[:12]
    elif section == "engine":
        patch["engine"] = StoryEngine.model_validate(value.get("engine") or value).model_dump()
    elif section == "world":
        patch["world"] = FoundationWorld.model_validate(value.get("world") or value).model_dump()
    elif section == "characters":
        items = value.get("characters")
        if not isinstance(items, list):
            items = value.get("data") if isinstance(value.get("data"), list) else []
        cleaned = [FoundationCharacter.model_validate(item).model_dump() for item in items if isinstance(item, dict)]
        if len(cleaned) < 1:
            raise ValueError("至少给一位关键人物")
        patch["characters"] = cleaned[:4]
    elif section == "stages":
        items = value.get("stages")
        if not isinstance(items, list):
            items = value.get("data") if isinstance(value.get("data"), list) else []
        cleaned: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                cleaned.append(StoryStage.model_validate(item).model_dump())
        if len(cleaned) < 2:
            raise ValueError("至少给两个阶段")
        patch["stages"] = cleaned
    elif section == "scale_volume":
        sub: dict[str, Any] = {}
        if isinstance(value.get("scale_plan"), dict):
            sub["scale_plan"] = value["scale_plan"]
        if isinstance(value.get("first_volume"), dict):
            fv = FirstVolume.model_validate(value["first_volume"]).model_dump()
            sub["first_volume"] = fv
        if not sub:
            raise ValueError("至少给出 scale_plan 或 first_volume")
        patch.update(sub)
    elif section == "opening_window":
        sub = value.get("opening_window") if isinstance(value.get("opening_window"), dict) else value
        ow = OpeningWindow.model_validate(sub)
        # 确保 chapter_directions 类型
        ow.chapter_directions = [ChapterDirection.model_validate(d) for d in (ow.chapter_directions or [])]
        patch["opening_window"] = ow.model_dump()
    return patch


async def generate_opening_pilot(
    foundation: dict[str, Any],
    method_cards: list[dict[str, Any]],
    *,
    author_note: str = "",
    style_reference: str = "",
) -> dict[str, Any]:
    """Build a scene contract first, then write one unpolished-by-pipeline opening chapter."""
    from app.schemas import SceneContract

    opening_window = foundation.get("opening_window") if isinstance(foundation.get("opening_window"), dict) else {}
    directions = (
        opening_window.get("chapter_directions")
        if isinstance(opening_window.get("chapter_directions"), list)
        else []
    )
    protagonist = foundation.get("protagonist") if isinstance(foundation.get("protagonist"), dict) else {}
    world = foundation.get("world") if isinstance(foundation.get("world"), dict) else {}
    first_direction = directions[0] if directions else {
        "sequence": 1,
        "title": "第一章",
        "reader_orientation": opening_window.get("reader_anchor") or "认清主角、开篇地点与眼前处境",
        "immediate_goal": "处理开篇地点正在发生的具体麻烦",
        "obstacle": world.get("opening_pressure") or world.get("cost") or "眼前局势不允许主角轻易如愿",
        "main_action": protagonist.get("method") or "主角按自己的习惯先试着解决眼前问题",
        "immediate_consequence": "主角的行动改变了眼前局面，也带来下一步必须处理的后果",
        "information_gain": "读者从行动后果中理解一条必要规则",
        "ending_beat": "一个已经发生作用的新压力把人物推向下一章",
    }
    common = (
        f"已由作者确认的故事根基：{json.dumps(foundation, ensure_ascii=False)}\n"
        "其中 creative_brief 是作者可见、可修改的最高优先创作依据；若与后台结构索引冲突，以 creative_brief 为准。\n"
        f"第一章方向：{json.dumps(first_direction, ensure_ascii=False)}\n"
        f"作者本次补充：{author_note or '无'}\n"
        f"文风参考（只学习叙事距离、节奏和对话方式，禁止仿写原句）：{style_reference or '无'}\n"
        f"相关写作方法：{json.dumps(_method_context(method_cards), ensure_ascii=False)}\n"
    )
    contract_prompt = common + (
        "先把第一章变成可执行场景契约。只用开篇地点和此刻必要人物，不讲解全书设定。"
        "第一章的首要任务是让读者认清主角、地点、眼前目标和阻力，不追求重大反转。"
        "本章约3500至4500汉字，根据开篇功能设计1至8个连续情节段；可以在同一地点停留，不要为了凑场景频繁换地图。"
        "如果一个麻烦需要多章讲清，第一章只写它的进入、试探、受阻或余波之一，让读者看懂但不抢跑。"
        "整章只允许一个很小的状态变化：主角完成第一次试探，或确认一个直接事实，或付出一个眼前代价。"
        "不得解决开篇局部目标，不得洗清嫌疑、击败主要对手、完成升级、建立稳固联盟或揭开幕后真相。"
        "场景要给人物观察、误判、犹豫、尝试失败和对方反应留下空间，不能只保留剧情节点。"
        "每场都按感知→人物的有限判断→意图→行动→他人基于自身利益的回应→局部后果推进。"
        "场景之间必须有因果，不得用偶然事件救场。输出JSON："
        '{"title":string,"summary":string,"scene_contract":{"viewpoint":string,'
        '"starting_state":string,"immediate_goal":string,"resistance":string,"action":string,'
        '"decision":string,"immediate_consequence":string,"changed_state":string,"next_promise":string,'
        '"scenes":[{"place":string,"present_characters":string,"perception":string,'
        '"intention":string,"action_and_response":string,"consequence":string}]}}'
    )
    contract = None
    title = str(first_direction.get("title") or "第一章").strip()
    summary = str(first_direction.get("immediate_consequence") or "第一章让主角的眼前处境发生变化").strip()
    feedback = ""
    for model in _planning_models():
        try:
            raw_contract = await llm_client.complete(
                "你是小说场景导演。只规划人物真正看见、误解、选择并造成后果的场景。只输出JSON。",
                contract_prompt + feedback,
                "json",
                model=model,
                max_tokens=2200,
            )
            envelope = _unwrap_json_object(raw_contract, "pilot", "data")
            contract = SceneContract.model_validate(envelope.get("scene_contract"))
            title = str(envelope.get("title") or title).strip()
            summary = str(envelope.get("summary") or contract.changed_state).strip()
            break
        except Exception as exc:
            feedback = f"\n上次场景契约不可用：{exc}。压缩表达，保证JSON完整，不输出思考过程。"
    if contract is None:
        protagonist = foundation["protagonist"]
        opening_place = foundation["world"]["opening_locality"]
        contract = SceneContract(
            viewpoint=protagonist["name"],
            starting_state=first_direction["reader_orientation"],
            immediate_goal=first_direction["immediate_goal"],
            resistance=first_direction["obstacle"],
            action=first_direction["main_action"],
            decision=first_direction["main_action"],
            immediate_consequence=first_direction["immediate_consequence"],
            changed_state=first_direction["immediate_consequence"],
            next_promise=first_direction["ending_beat"],
            scenes=[
                {
                    "place": opening_place,
                    "present_characters": protagonist["name"],
                    "perception": "主角先察觉眼前局势中最具体的异常",
                    "intention": first_direction["immediate_goal"],
                    "action_and_response": f"主角采取行动，却遭遇{first_direction['obstacle']}",
                    "consequence": "原计划受到阻碍，主角必须调整下一步",
                },
                {
                    "place": opening_place,
                    "present_characters": "主角与当前阻力人物",
                    "perception": "主角发现自己对局势的理解并不完整",
                    "intention": "先解决眼前目标，而不是处理全部长期问题",
                    "action_and_response": first_direction["main_action"],
                    "consequence": first_direction["immediate_consequence"],
                },
            ],
        )

    prose_prompt = common + (
        f"已确认场景契约：{json.dumps(contract.model_dump(), ensure_ascii=False)}\n\n"
        "直接写完整第一章正文，不要输出标题、提纲、点评、Markdown或创作说明。"
        "正文建议3500至5500汉字；字数只作为节奏参考，不因自然偏长而删掉必要动作、对话、误判、等待和关系反应。"
        "只要章节事件链完整，略短或略长都可接受；不得靠重复解释、堆背景或同义改写凑字数。"
        "开头尽快让读者进入一个具体时刻，让世界规则通过人物处理眼前事情自然显露。"
        "始终贴着视角人物的感官、有限认知和当下欲望；允许误判、停顿、无效动作和未说出口的话。"
        "对话双方都有自己的目的，回答必须改变对方下一步。重要情绪落在动作、选择和身体反应上。"
        "不要总结人物性格，不罗列设定，不连续使用华丽比喻，不为凑长度重复解释。"
        "本章只能使用opening_window.introduced_characters和introduced_rules中的必要部分。"
        "不要解释全书问题，不触碰first_volume.protected_reveals，不替后续章节完成任务。"
        "结尾只兑现契约中的微小changed_state，并具体开启next_promise；读者应感觉事情刚真正开始，而不是第一章已经完成一个小故事。"
    )
    content = ""
    last_length = 0
    settings = get_settings()
    prose_models = list(dict.fromkeys([
        settings.llm_model,
        *settings.llm_fallback_models,
        settings.llm_fallback_model,
    ]))
    prose_models = [model for model in prose_models if model]
    for attempt in range(2):
        length_feedback = (
            ""
            if attempt == 0
            else f"\n上一稿正文只有约{last_length}字或推进过度。请从头完整重写，不要接写旧稿；"
                 "补足人物在同一件事中的观察、试错、对话反应与余波，同时把解决上层问题的内容留给后续章节。"
        )
        try:
            content = await llm_client.complete(
                "你是一位成熟的长篇类型小说作者。写的是小说现场，不是策划案扩写；第一章负责让故事活起来，不负责讲完一个故事。",
                prose_prompt + length_feedback,
                stream=True,
                model=prose_models[min(attempt, len(prose_models) - 1)],
                max_tokens=8192,
                temperature=0.75,
                timeout_seconds=150,
                request_attempts=1,
            )
        except Exception as exc:
            if attempt == 1:
                raise RuntimeError(f"第一章正文生成失败：{exc}") from exc
            continue
        content = re.sub(r"^\s*(?:#+\s*)?第[一二三四五六七八九十0-9]+章[^\n]*\n+", "", content.strip())
        last_length = len("".join(content.split()))
        if last_length >= 2500:
            break
    if last_length < 2500:
        raise RuntimeError(f"第一章疑似未写完整：当前约{last_length}字，请重新生成")
    return {
        "title": title,
        "content": content,
        "summary": summary,
        "scene_contract": contract.model_dump(),
    }


def _direction_rejection_reasons(directions: Any) -> list[str]:
    """Pillars must cover complementary engines of the same book."""
    if not isinstance(directions, list) or not 4 <= len(directions) <= 6:
        return ["必须提供四到六个可以融合的创作支柱"]
    reasons: list[str] = []
    required = (
        "key", "title", "logline", "reader_payoff", "differentiation", "protagonist_engine",
        "serial_engine", "emotional_throughline", "cost_and_risk",
    )
    for index, item in enumerate(directions, start=1):
        if not isinstance(item, dict):
            reasons.append(f"方向{index}不是结构化对象")
            continue
        for field in required:
            minimum = 2 if field in {"key", "title"} else 20
            if len(str(item.get(field) or "").strip()) < minimum:
                reasons.append(f"方向{index}的{field}缺少具体内容")
    titles = {str(item.get("title") or "").strip() for item in directions if isinstance(item, dict)}
    engines = {str(item.get("serial_engine") or "").strip() for item in directions if isinstance(item, dict)}
    if len(titles) != len(directions) or len(engines) != len(directions):
        reasons.append("创作支柱不能只换措辞，承担的叙事功能和连载发动机必须实质不同")
    return reasons


async def generate_story_directions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Story Director proposes complementary pillars to synthesize into one book."""
    prompt = (
        "作者原话：\n" + str(payload.get("idea") or "") + "\n\n"
        f"类型倾向：{payload.get('genres') or payload.get('genre') or '未限定'}\n"
        f"频道：{payload.get('channel') or '不限'}；目标字数：{payload.get('target_words') or 1_000_000}\n"
        f"读者体验：{payload.get('reader_wish') or '从作者原话谨慎推断'}\n"
        f"明确不要：{payload.get('avoid_elements') or '无'}\n\n"
        "你是故事总监。先不要写大纲、设定百科或第一章。提出五个属于同一本书、需要彼此配合的创作支柱，"
        "而不是五本互斥的候选书。支柱应分别覆盖读者核心快感、主角成长与行动、关系和情感连续性、"
        "世界/力量升级、主动对手与长期悬念等功能；每项都必须能进入同一条因果主线。"
        "每个支柱说明它如何支持多卷连载、与其他支柱的区别，以及最容易写崩的风险。不要评分，不要宣布哪个最好。"
        "只输出JSON：{\"directions\":[{\"key\":string,\"title\":string,\"logline\":string,"
        "\"reader_payoff\":string,\"differentiation\":string,\"protagonist_engine\":string,"
        "\"serial_engine\":string,\"emotional_throughline\":string,\"cost_and_risk\":string}]}"
    )
    last_error: Exception | None = None
    models = _planning_models()
    for model in (models if len(models) > 1 else models * 2):
        try:
            raw = await llm_client.complete(
                "你是长篇小说故事总监，只提供同一本书可组合的创作支柱。只输出JSON。",
                prompt,
                "json",
                model=model,
                max_tokens=3800,
                temperature=0.65,
            )
            value = _unwrap_json_object(raw, "data")
            directions = value.get("directions")
            reasons = _direction_rejection_reasons(directions)
            if reasons:
                raise ValueError("；".join(reasons))
            from app.schemas import StoryDirection

            return [StoryDirection.model_validate(item).model_dump() for item in directions]
        except Exception as exc:
            last_error = exc
            logger.warning("[creation-directions] model=%s 失败: %s", model, exc)
    raise RuntimeError(f"创作支柱生成失败：{last_error or '模型未返回有效支柱'}")


def viability_blocking_reasons(review: dict[str, Any]) -> list[str]:
    """Require observable long-form evidence; model verdict and numeric scores are not trusted."""
    evidence = review.get("evidence") if isinstance(review.get("evidence"), dict) else {}
    reasons = [str(item).strip() for item in review.get("blocking_issues", []) if str(item).strip()]
    text_fields = {
        "读者持续回报": "reader_payoff",
        "同类差异": "differentiation",
        "主角行动发动机": "protagonist_engine",
        "关系发动机": "relationship_engine",
        "对手主动性": "antagonist_agency",
        "升级上限": "escalation_capacity",
        "终局方向": "endgame_direction",
    }
    for label, field in text_fields.items():
        if len(str(evidence.get(field) or "").strip()) < 20:
            reasons.append(f"{label}没有给出可验证证据")
    variations = [str(item).strip() for item in evidence.get("story_engine_variations", []) if str(item).strip()]
    if len(variations) < 3 or len(set(variations)) < 3:
        reasons.append("故事循环至少需要三种不同的冲突变体")
    arcs = evidence.get("simulated_arcs") if isinstance(evidence.get("simulated_arcs"), list) else []
    required_arc_fields = ("stage", "new_pressure", "protagonist_choice", "irreversible_cost", "changed_state")
    valid_arcs = [
        arc for arc in arcs if isinstance(arc, dict)
        and all(len(str(arc.get(field) or "").strip()) >= 8 for field in required_arc_fields)
    ]
    if len(valid_arcs) < 3:
        reasons.append("至少模拟开篇、中期和后期三个具有选择与代价的故事弧")
    promises = evidence.get("promise_ledger") if isinstance(evidence.get("promise_ledger"), list) else []
    required_promise_fields = ("promise", "setup", "payoff_window", "payoff_form")
    valid_promises = [
        item for item in promises if isinstance(item, dict)
        and all(str(item.get(field) or "").strip() for field in required_promise_fields)
    ]
    if len(valid_promises) < 4:
        reasons.append("承诺账本至少需要四项明确的建立与兑现安排")
    opening = evidence.get("opening_strategy") if isinstance(evidence.get("opening_strategy"), dict) else {}
    for checkpoint in ("chapter_1", "chapter_3", "chapter_10", "chapter_30"):
        if len(str(opening.get(checkpoint) or "").strip()) < 10:
            reasons.append(f"开篇策略缺少{checkpoint}的读者留存目标")
    return list(dict.fromkeys(reasons))


async def review_story_viability(
    payload: dict[str, Any], direction: dict[str, Any], foundation: dict[str, Any]
) -> dict[str, Any]:
    """Commercial editor and long-form architect jointly stress-test a proposed book."""
    prompt = (
        f"作者原话：{payload.get('idea') or ''}\n"
        f"作者确认的多支柱融合方案：{json.dumps(direction, ensure_ascii=False)}\n"
        f"当前故事根基：{json.dumps(foundation, ensure_ascii=False)}\n\n"
        "你同时承担读者编辑和长篇架构师职责。不要写鼓励语，不要打分，也不能因为字段齐全就通过。"
        "用具体故事推演证明：读者持续回报、同类差异、主角行动发动机、至少三种循环变体、关系变化、"
        "具有自己目标的对手、百万字升级空间、开中后期三个故事弧、承诺账本、前1/3/10/30章留存目标和终局闭合。"
        "simulated_arcs每项必须包含stage/new_pressure/protagonist_choice/irreversible_cost/changed_state。"
        "promise_ledger每项必须包含promise/setup/payoff_window/payoff_form。"
        "发现副本重复、主角全知消解冲突、金手指无代价、配角工具化或中后期失速，写入blocking_issues。"
        "只输出JSON：{\"verdict\":\"pass|revise\",\"evidence\":{"
        "\"reader_payoff\":string,\"differentiation\":string,\"protagonist_engine\":string,"
        "\"story_engine_variations\":[string],\"relationship_engine\":string,\"antagonist_agency\":string,"
        "\"escalation_capacity\":string,\"simulated_arcs\":[object],\"promise_ledger\":[object],"
        "\"opening_strategy\":{\"chapter_1\":string,\"chapter_3\":string,\"chapter_10\":string,\"chapter_30\":string},"
        "\"endgame_direction\":string},\"blocking_issues\":[string],\"warnings\":[string]}"
    )
    last_error: Exception | None = None
    models = _planning_models()
    for model in (models if len(models) > 1 else models * 2):
        try:
            raw = await llm_client.complete(
                "你是严格的连载小说读者编辑与长篇架构师。只输出JSON。",
                prompt,
                "json",
                model=model,
                max_tokens=5000,
                temperature=0.25,
            )
            value = _unwrap_json_object(raw, "review", "data")
            from app.schemas import ViabilityReviewData

            parsed = ViabilityReviewData.model_validate(value).model_dump()
            blockers = viability_blocking_reasons(parsed)
            parsed["blocking_issues"] = blockers
            parsed["verdict"] = "pass" if not blockers else "revise"
            return parsed
        except Exception as exc:
            last_error = exc
            logger.warning("[viability-review] model=%s 失败: %s", model, exc)
    try:
        raw = await llm_client.complete(
            "你是严格的连载小说读者编辑与长篇架构师。只输出JSON。",
            prompt,
            "json",
            model=None,
            max_tokens=5000,
            temperature=0.25,
        )
        value = _unwrap_json_object(raw, "review", "data")
        from app.schemas import ViabilityReviewData

        parsed = ViabilityReviewData.model_validate(value).model_dump()
        blockers = viability_blocking_reasons(parsed)
        parsed["blocking_issues"] = blockers
        parsed["verdict"] = "pass" if not blockers else "revise"
        return parsed
    except Exception as exc:
        last_error = exc
        logger.warning("[viability-review] provider fallback 失败: %s", exc)
    raise RuntimeError(f"长篇可行性评审失败：{last_error or '模型未返回有效证据'}")
