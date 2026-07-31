from __future__ import annotations

from dataclasses import dataclass

from app.schemas import ProjectCreate

GENRE_STYLE_MAP = {
    "玄幻": {"tone": "热血、升级、奇诡", "chapter_goal": "强冲突推进"},
    "都市": {"tone": "现实、反差、节奏快", "chapter_goal": "爽点密集"},
    "科幻": {"tone": "设定驱动、悬疑感", "chapter_goal": "世界观揭示"},
    "言情": {"tone": "情绪细腻、关系拉扯", "chapter_goal": "关系推进"},
    "历史": {"tone": "厚重、谋略、群像", "chapter_goal": "局势变化"},
    "悬疑": {"tone": "压迫、反转、线索回收", "chapter_goal": "谜题推进"},
    "游戏": {"tone": "规则明确、成长反馈", "chapter_goal": "目标升级"},
}

GENRE_WRITING_CONTRACTS = {
    "历史": {
        "reader_experience": "从人物处境与利益碰撞中看见时代，而不是听作者讲历史",
        "narrative_distance": "贴近限知人物，判断允许出错，历史知识只转化为风险意识",
        "scene_engine": "身份差、资源差和信息差推动试探、交易、误判与代价",
        "dialogue": "称谓、沉默和言外之意体现身份秩序，每句话都服务于利益",
        "prose_texture": "以衣食、器物、气味、路程和礼法构成时代质感，少用抽象形容",
        "rhythm": "谋划从现场细节生长，关键选择前放慢，后果出现时收紧",
        "information_release": "史实附着于人物行动与局部见闻，不作百科说明，不提前宣布未来必然发生",
        "avoid": ["现代咨询报告术语", "把人物当棋子和变量概括", "全知式历史剧透", "空泛棋局收尾"],
    },
    "悬疑": {
        "reader_experience": "读者与视角人物共享有限证据，能够推理但不能被作者欺骗",
        "narrative_distance": "近距离限知，区分事实、判断与误判",
        "scene_engine": "每场获得一条可验证信息，同时让旧解释产生裂缝",
        "dialogue": "问答存在回避、试探和信息不对称，沉默也必须有动机",
        "prose_texture": "选择可复查的物证、空间关系和行为异常，避免纯气氛堆砌",
        "rhythm": "发现时放慢，危险时加速，反转后留出重新理解证据的空间",
        "information_release": "关键答案必须有前置证据，反转改变解释而不是推翻事实",
        "avoid": ["藏住视角人物已知信息", "无证据反转", "连续阴森形容", "万能巧合"],
    },
    "言情": {
        "reader_experience": "从具体互动感受关系变化，而不是听旁白宣布心动或误会",
        "narrative_distance": "贴近身体感受与自我辩解，保留人物不愿承认的情绪",
        "scene_engine": "欲望与防御相冲突，同一行为在两人眼中有不同含义",
        "dialogue": "台词表层处理事情，潜台词处理关系，避免直接说明全部感受",
        "prose_texture": "用动作距离、目光、触觉和生活细节承载情绪",
        "rhythm": "互动前建立期待，关键停顿留白，关系变化后给出余波",
        "information_release": "先让读者看见行为，再逐步理解动机",
        "avoid": ["反复脸红心跳", "无缘由误会", "越界行为浪漫化", "情绪标签代替互动"],
    },
    "玄幻": {
        "reader_experience": "能力、世界规则与代价同时可感，成长来自选择而非数值播报",
        "narrative_distance": "贴近行动者的身体负荷、判断和未知",
        "scene_engine": "明确目标遭遇规则性阻力，能力使用改变局势也制造新代价",
        "dialogue": "立场和实力差通过行动结果体现，少用互相介绍设定",
        "prose_texture": "奇观必须有尺度、材质、运动和人物反应",
        "rhythm": "建立规则后快速兑现，升级节点给足因果与反馈",
        "information_release": "规则在使用和失败中揭示，禁止说明书式灌输",
        "avoid": ["战力标签代替战斗", "围观者轮流震惊", "无代价金手指", "设定名词连发"],
    },
}

# 世界发动机是类型的可运行规则，不是气氛描述。它决定什么会持续制造冲突、
# 主角如何获得成长，以及每次使用能力必须付出什么代价。
GENRE_WORLD_CONTRACTS = {
    "玄幻": {
        "engine_name": "力量与资源竞争",
        "power_source": "修炼体系、血脉/功法或可验证的超凡资源",
        "social_order": "宗门、家族、王朝与强者共同分配资源和身份",
        "progression_axes": ["境界", "功法能力", "资源", "身份", "地图"],
        "conflict_generators": ["资源稀缺", "规则限制", "势力争夺", "能力反噬"],
        "cost_required": True,
    },
    "仙侠": {
        "engine_name": "修行与因果代价",
        "power_source": "功法、灵物、道统与对天地规则的理解",
        "social_order": "宗门、世家、散修和天道秩序形成多层约束",
        "progression_axes": ["境界", "道心", "道统", "资源", "因果关系"],
        "conflict_generators": ["天劫", "寿元", "因果债", "道统冲突", "资源争夺"],
        "cost_required": True,
    },
    "武侠": {
        "engine_name": "技艺与江湖秩序",
        "power_source": "武学、经验、情报、兵器和名望",
        "social_order": "门派、帮会、官府与江湖信誉分配机会",
        "progression_axes": ["武学", "实战经验", "人情网络", "名望", "立场"],
        "conflict_generators": ["恩怨债务", "门派规则", "名声反噬", "情报不对称"],
        "cost_required": True,
    },
    "都市": {
        "engine_name": "身份与资源跃迁",
        "power_source": "职业能力、资本、信息、关系和可验证成果",
        "social_order": "行业门槛、组织权力、法律规则和舆论共同约束行动",
        "progression_axes": ["能力", "财富", "身份", "组织控制力", "公众信誉"],
        "conflict_generators": ["利益竞争", "身份反差", "资源封锁", "选择代价"],
        "cost_required": True,
    },
    "言情": {
        "engine_name": "关系议价与自我成长",
        "power_source": "人物的选择、边界、能力、身份和情感信任",
        "social_order": "家庭、职场、阶层和亲密关系中的边界决定议价权",
        "progression_axes": ["自我能力", "生存空间", "身份财富", "关系信任", "边界感"],
        "conflict_generators": ["欲望与防御冲突", "关系误读", "现实压力", "成长后的重新选择"],
        "cost_required": True,
    },
    "悬疑": {
        "engine_name": "证据与解释竞争",
        "power_source": "可核验的证据、行动能力和有限信息",
        "social_order": "机构、关系网络和证据规则影响谁能定义真相",
        "progression_axes": ["证据链", "调查权限", "风险承受力", "关系代价", "真相层级"],
        "conflict_generators": ["信息不对称", "证据缺口", "时间压力", "错误解释的代价"],
        "cost_required": True,
    },
    "科幻": {
        "engine_name": "技术能力与系统副作用",
        "power_source": "技术、资源、制度和对未知的认知优势",
        "social_order": "技术垄断、组织权限、法律和生存环境分配机会",
        "progression_axes": ["技术", "权限", "资源", "认知边界", "生存空间"],
        "conflict_generators": ["副作用", "技术封锁", "伦理选择", "环境压力"],
        "cost_required": True,
    },
}

GENRE_ALIASES = {
    "奇幻": "玄幻",
    "诸天无限": "玄幻",
    "轻小说": "玄幻",
    "现实": "都市",
    "体育": "都市",
    "军事": "历史",
    "游戏": "科幻",
    "末世": "科幻",
    "悬疑灵异": "悬疑",
    "悬疑推理": "悬疑",
    "古代言情": "言情",
    "仙侠奇缘": "仙侠",
    "现代言情": "言情",
    "浪漫青春": "言情",
    "玄幻言情": "言情",
    "科幻空间": "科幻",
    "游戏竞技": "游戏",
    "女生剧场": "言情",
    "现实生活": "言情",
    "宫斗宅斗": "言情",
    "种田经商": "言情",
    "豪门总裁": "言情",
    "青春校园": "言情",
}


def resolve_primary_genre(genre: str) -> str:
    if genre in GENRE_ALIASES:
        genre = GENRE_ALIASES[genre]
    known_genres = set(GENRE_WRITING_CONTRACTS) | set(GENRE_STYLE_MAP) | set(GENRE_WORLD_CONTRACTS)
    if genre in known_genres:
        return genre
    matches = [key for key in known_genres if key in genre]
    return min(matches, key=genre.index) if matches else genre


def get_genre_writing_contract(genre: str) -> dict:
    genre = resolve_primary_genre(genre)
    return GENRE_WRITING_CONTRACTS.get(
        genre,
        {
            "reader_experience": "跟随人物的具体欲望进入故事，并看见选择造成后果",
            "narrative_distance": "稳定限知视角，抽象判断落回现场证据",
            "scene_engine": "目标、阻力、策略、转折和结果构成因果场景",
            "dialogue": "人物带着目的说话，不轮流递送背景信息",
            "prose_texture": "用题材相关的具体细节建立质感",
            "rhythm": "节奏服从场景压力和情绪变化",
            "information_release": "信息随行动需要逐步释放",
            "avoid": ["作者总结腔", "模板排比", "抽象升华", "重复解释"],
        },
    )


def get_genre_world_contract(genre: str) -> dict:
    """返回主类型世界发动机，辅助类型不会覆盖主类型规则。"""
    primary = resolve_primary_genre(genre)
    if primary in GENRE_WORLD_CONTRACTS:
        return {
            "primary_genre": primary,
            **GENRE_WORLD_CONTRACTS[primary],
            "core_cost": "每次获得能力或资源都增加可追踪的关系、时间、身体或身份代价",
        }
    # 女频细分类型和现实题材回退到关系/秩序驱动，仍要求成长与代价。
    if "女频" in genre or "言情" in genre:
        return {
            "primary_genre": "言情",
            **GENRE_WORLD_CONTRACTS["言情"],
        "core_cost": "关系或身份发生关键跃迁时，要承担可追踪的信任、边界或安全感代价",
        }
    return {
        "primary_genre": primary,
        "engine_name": "人物欲望与秩序冲突",
        "power_source": "人物能力、资源、信息或关系",
        "social_order": "题材中的制度与群体规则",
        "progression_axes": ["能力", "资源", "身份", "关系"],
        "conflict_generators": ["目标阻力", "信息差", "选择代价"],
        "cost_required": True,
        "core_cost": "关键选择和成长节点必须受时间、资源、关系或安全感约束",
    }


def validate_world_engine(
    world: dict,
    genre: str | None = None,
    *,
    strict: bool = False,
) -> list[str]:
    """返回阻断级问题；为空才允许进入人物和情节阶段。"""
    errors: list[str] = []
    required = ("engine_name", "power_source", "social_order", "progression_axes", "conflict_generators")
    errors.extend(f"缺少世界发动机字段：{key}" for key in required if not world.get(key))
    if not isinstance(world.get("progression_axes"), list) or len(world.get("progression_axes", [])) < 2:
        errors.append("升级线至少需要两个不同维度，不能只有境界或数值")
    if not isinstance(world.get("conflict_generators"), list) or len(world.get("conflict_generators", [])) < 2:
        errors.append("世界必须提供至少两个可反复制造冲突的规则来源")
    has_cost = world.get("costs") or world.get("limitations") or world.get("core_cost")
    if world.get("cost_required", True) and not has_cost:
        errors.append("能力/资源没有限制或代价，金手指和成长线会失控")
    if genre:
        expected = get_genre_world_contract(genre)
        if world.get("primary_genre") and world["primary_genre"] != expected["primary_genre"]:
            errors.append("世界主类型与作品主类型不一致")
    if strict:
        strict_fields = {
            "core_rule": "缺少能被场景验证的核心规则",
            "scarcity": "缺少会引发竞争的稀缺资源",
            "escalation_model": "缺少升级后如何进入新竞争层级",
            "opening_pressure": "缺少第一章就能作用于主角的世界压力",
        }
        errors.extend(message for field, message in strict_fields.items() if not world.get(field))
        limitations = world.get("limitations")
        if not isinstance(limitations, list) or len(limitations) < 2:
            errors.append("至少需要两条明确的能力或资源限制")
        daily_life = world.get("daily_life_effects")
        if not isinstance(daily_life, list) or len(daily_life) < 2:
            errors.append("世界规则必须在普通人的生活中产生至少两种可见影响")
        tests = world.get("pressure_tests")
        if not isinstance(tests, list) or len(tests) < 3:
            errors.append("世界发动机必须通过至少三个不同冲突场景的压力测试")
        elif not all(
            isinstance(item, dict)
            and item.get("desire")
            and item.get("rule_pressure")
            and item.get("costly_choice")
            for item in tests[:3]
        ):
            errors.append("每个压力测试都要包含人物欲望、规则压力和有代价的选择")
    return errors


def validate_character_agency(character: dict) -> list[str]:
    """人物必须能够依靠自己的欲望和方法改变局面。"""
    required = {
        "desire": "人物缺少具体欲望",
        "method": "人物缺少有个人特色的解决问题方法",
        "bottom_line": "人物缺少不可轻易跨越的底线",
        "pressure_action": "人物缺少压力下会采取的主动行为",
    }
    return [message for field, message in required.items() if not str(character.get(field) or "").strip()]


@dataclass
class BootstrapBundle:
    style_profile: dict
    wiki_pages: list[dict]
    outlines: list[dict]
    toc_nodes: list[dict]
    chapters: list[dict]
    generation_state: dict


def estimate_total_chapters(target_words: int) -> int:
    return max(60, min(2500, round(target_words / 3300)))


def estimate_volume_count(total_chapters: int) -> int:
    """按全书规模决定卷数：短篇 3 卷，超长篇最多 20 卷。"""
    return max(3, min(20, total_chapters // 50))


def _chinese_ordinal(value: int) -> str:
    numerals = "零一二三四五六七八九"
    if value <= 10:
        return "十" if value == 10 else numerals[value]
    if value < 20:
        return "十" + numerals[value - 10]
    if value == 20:
        return "二十"
    return str(value)


def build_volume_anchors(
    total_chapters: int,
    volume_count: int,
    blueprint: dict | None,
) -> list[dict]:
    """把全书切分为 volume_count 个阶段锚点。

    蓝图 major_arcs（通常 3 段）映射到前/中/后卷，未覆盖的卷标记为
    "待滚动规划"，由卷末再规划引擎在写到时填充细节。
    """
    blueprint = blueprint or {}
    route = blueprint.get("book_blueprint") if isinstance(blueprint.get("book_blueprint"), dict) else blueprint
    major_arcs = route.get("major_arcs") or []
    arc_titles = [str(a.get("title", "")) for a in major_arcs if isinstance(a, dict)]
    # 三段主线大致对应 前 1/4、中 1/2、后 1/4
    stage_of_volume = []
    for i in range(volume_count):
        ratio = i / max(volume_count - 1, 1)
        if ratio < 0.25:
            stage_of_volume.append(0)
        elif ratio < 0.75:
            stage_of_volume.append(1)
        else:
            stage_of_volume.append(2)

    anchors = []
    per = total_chapters // volume_count
    remainder = total_chapters % volume_count
    start = 1
    for i in range(volume_count):
        size = per + (1 if i < remainder else 0)
        end = start + size - 1
        stage_idx = stage_of_volume[i]
        arc_title = arc_titles[stage_idx] if stage_idx < len(arc_titles) else ""
        anchors.append({
            "sequence": i + 1,
            "title": f"第{_chinese_ordinal(i + 1)}卷",
            "chapter_range": [start, end],
            "stage_index": stage_idx,
            "stage_title": arc_title,
            "status": "detailed" if i == 0 else "anchor",
        })
        start = end + 1
    return anchors


def build_project_bootstrap(payload: ProjectCreate) -> BootstrapBundle:
    total_chapters = estimate_total_chapters(payload.target_words)
    volume_count = estimate_volume_count(total_chapters)
    primary_genre = resolve_primary_genre(payload.genre)
    genre_style = GENRE_STYLE_MAP.get(primary_genre, {"tone": "强叙事、可读性优先", "chapter_goal": "持续推进"})
    title = payload.title
    blueprint = payload.planning_profile or {}
    first_volume = (
        blueprint.get("first_volume", {})
        if isinstance(blueprint.get("first_volume"), dict)
        else blueprint.get("volume_plan", {})
    )
    world_input = blueprint.get("world_engine", {}) if isinstance(blueprint, dict) else {}
    world_engine = {**get_genre_world_contract(payload.genre), **world_input}
    world_validation = validate_world_engine(world_engine, payload.genre, strict=bool(world_input))
    volume_anchors = build_volume_anchors(total_chapters, volume_count, blueprint)

    selected_style = blueprint.get("writing_style", {}) if isinstance(blueprint, dict) else {}
    author_constitution = blueprint.get("author_constitution", {}) if isinstance(blueprint, dict) else {}
    writing_contract = get_genre_writing_contract(payload.genre)
    if selected_style:
        writing_contract = {
            **writing_contract,
            "author_style": selected_style.get("description_effective")
            or selected_style.get("description_raw")
            or selected_style.get("prose_style", "由作者自行描述"),
            "pov": selected_style.get("pov_style", writing_contract.get("pov", "按章纲确定")),
            "rhythm": selected_style.get("pace", writing_contract.get("rhythm", "按场景需要变化")),
            "reader_contract": "场景清楚、人物目标可感、秘密有理解支点，每章兑现预设读者感受",
        }
    style_profile = {
        "genre": payload.genre,
        "tone": genre_style["tone"],
        "chapter_goal": genre_style["chapter_goal"],
        "narrative_cards": [
            "聚焦化边界",
            "心理距离",
            "场景因果",
            "目标阻力变化",
            "情绪推动行动",
            "母题回归",
            "句法节奏",
            "自由间接引语",
            "对话潜台词",
        ],
        "anti_ai_rules": ["避免总结腔", "用动作代替概括", "减少模板连接词"],
        "writing_contract": writing_contract,
        "selected_style": selected_style,
        "author_constitution": author_constitution,
        "world_engine": world_engine,
        "world_validation": {
            "status": "pass" if not world_validation else "review_required",
            "blocking_issues": world_validation,
        },
    }
    if payload.planning_profile:
        style_profile["creation_blueprint"] = payload.planning_profile

    wiki_pages = [
        {
            "slug": "world-core",
            "category": "worldview",
            "title": "世界与背景",
            "content": (
                f"# {title} 世界与背景\n\n"
                f"- 类型：{payload.genre}\n"
                f"- 核心故事：{payload.one_sentence}\n"
                f"- 叙事基调：{genre_style['tone']}\n"
                f"- 主角：[[{payload.protagonist_name}]]\n"
                f"- 世界发动机：{world_engine['engine_name']}\n"
                f"- 核心规则：{world_engine.get('core_rule') or '随第一阶段继续确认'}\n"
                f"- 力量/资源来源：{world_engine['power_source']}\n"
                f"- 稀缺资源：{world_engine.get('scarcity') or '随第一阶段继续确认'}\n"
                f"- 世界秩序：{world_engine['social_order']}\n"
                f"- 升级维度：{'、'.join(world_engine['progression_axes'])}\n"
                f"- 限制：{'；'.join(world_engine.get('limitations') or []) or world_engine.get('core_cost', '')}\n"
                f"- 第一阶段压力：{world_engine.get('opening_pressure') or '由开篇场景确认'}\n"
            ),
            "aliases": [title, payload.genre],
            "wikilinks": [payload.protagonist_name],
            "visibility": "active",
        },
        {
            "slug": "canon-rules",
            "category": "canon_rule",
            "title": "写作边界",
            "content": (
                "# 写作边界\n\n"
                "1. 每章围绕一位主要人物的所见所感展开，避免视角混乱。\n"
                "2. 重要能力和关键转折需要提前给读者线索。\n"
                "3. 旧线索揭晓时，要带来新信息或让人物付出代价。\n"
            ),
            "aliases": ["硬规则"],
            "wikilinks": [],
            "visibility": "active",
        },
        {
            "slug": "author-constitution",
            "category": "canon_rule",
            "title": "作者创作宪章",
            "content": (
                "# 作者创作宪章\n\n"
                f"- 为什么写：{author_constitution.get('why_write') or '由作者后续补充'}\n"
                f"- 想留下的感受：{author_constitution.get('lasting_feeling') or '由作者后续补充'}\n"
                f"- 不可妥协：{author_constitution.get('non_negotiables') or '无额外约束'}\n"
                "- AI 可自主："
                f"{author_constitution.get('ai_mandate') or '在已确认边界内规划与起草，关键方向由作者确认'}\n"
                "- 每章验收："
                f"{author_constitution.get('chapter_test') or '人物是否作出改变局势的选择，并兑现预设读者感受'}\n"
            ),
            "aliases": ["创作心意", "作者意图", "创作宪章"],
            "wikilinks": [],
            "visibility": "active",
        },
        {
            "slug": payload.protagonist_name,
            "category": "character",
            "title": payload.protagonist_name,
            "content": (
                f"# {payload.protagonist_name}\n\n"
                f"- 性别：{payload.protagonist_gender}\n"
                f"- 性格：{payload.protagonist_personality}\n"
                "- 当前状态：故事开场前的普通人/待觉醒阶段\n"
                "- 长线目标：从眼前困局出发，逼近命运核心\n"
            ),
            "aliases": [payload.protagonist_name, "主角"],
            "wikilinks": ["world-core"],
            "visibility": "active",
        },
        {
            "slug": "main-timeline",
            "category": "timeline",
            "title": "故事进度",
            "content": f"# 故事进度\n\n- 第1章：{payload.protagonist_name} 被卷入故事核心冲突。\n",
            "aliases": ["时间线"],
            "wikilinks": [payload.protagonist_name],
            "visibility": "active",
        },
    ]
    research = blueprint.get("web_research") if isinstance(blueprint, dict) else None
    if isinstance(research, dict) and research.get("status") == "completed":
        source_lines = []
        for item in research.get("sources") or []:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            source_title = str(item.get("title") or "资料来源").replace("\n", " ")[:200]
            source_url = str(item["url"]).replace("\n", "")[:2000]
            source_lines.append(f"- [{source_title}]({source_url})")
        wiki_pages.append({
            "slug": "external-research",
            "category": "worldview",
            "title": "题材研究资料",
            "content": (
                "# 题材研究资料\n\n"
                "> 以下内容是带来源的现实资料，不是小说既定事实；采纳后仍需写入世界规则或正文才能成为 Canon。\n\n"
                f"{str(research.get('memo') or '')[:12000]}\n\n"
                "## 来源\n\n" + ("\n".join(source_lines[:12]) or "暂无可展示来源")
            ),
            "aliases": ["联网研究", "资料来源"],
            "wikilinks": ["world-core"],
            "visibility": "active",
        })
    planned_characters = payload.planning_profile.get("characters", []) if payload.planning_profile else []
    planned_protagonist = next(
        (
            character
            for character in planned_characters
            if isinstance(character, dict) and str(character.get("name") or "").strip() == payload.protagonist_name
        ),
        None,
    )
    if planned_protagonist:
        protagonist_page = next(page for page in wiki_pages if page["slug"] == payload.protagonist_name)
        protagonist_page["content"] = (
            f"# {payload.protagonist_name}\n\n"
            f"- 身份：{planned_protagonist.get('role') or '主角'}\n"
            f"- 性别：{planned_protagonist.get('gender') or payload.protagonist_gender}\n"
            f"- 性格：{planned_protagonist.get('personality') or payload.protagonist_personality}\n"
            f"- 最想得到：{planned_protagonist.get('desire') or '待完善'}\n"
            f"- 弱点：{planned_protagonist.get('flaw') or '待完善'}\n"
            f"- 惯用方法：{planned_protagonist.get('method') or '待完善'}\n"
            f"- 底线：{planned_protagonist.get('bottom_line') or '待完善'}\n"
            f"- 压力下的主动行为：{planned_protagonist.get('pressure_action') or '待完善'}\n"
            f"- 与他人的关系：{planned_protagonist.get('relationship') or '故事核心人物'}\n"
        )
    for character in planned_characters:
        if not isinstance(character, dict):
            continue
        name = str(character.get("name") or "").strip()
        if not name or name == payload.protagonist_name:
            continue
        wiki_pages.append(
            {
                "slug": name,
                "category": "character",
                "title": name,
                "content": (
                    f"# {name}\n\n"
                    f"- 身份：{character.get('role') or '关键人物'}\n"
                    f"- 性别：{character.get('gender') or '未限定'}\n"
                    f"- 性格：{character.get('personality') or '待完善'}\n"
                    f"- 最想得到：{character.get('desire') or '待完善'}\n"
                    f"- 弱点：{character.get('flaw') or '待完善'}\n"
                    f"- 惯用方法：{character.get('method') or '待完善'}\n"
                    f"- 底线：{character.get('bottom_line') or '待完善'}\n"
                    f"- 压力下的主动行为：{character.get('pressure_action') or '待完善'}\n"
                    f"- 与他人的关系：{character.get('relationship') or '待完善'}\n"
                ),
                "aliases": [name],
                "wikilinks": [payload.protagonist_name, "world-core"],
                "visibility": "active",
            }
        )

    outlines: list[dict] = []
    toc_nodes: list[dict] = []
    chapters: list[dict] = []
    book_outline = {
        "level": "book",
        "sequence": 1,
        "title": title,
        "content": {
            "premise": payload.one_sentence,
            "story_question": (
                blueprint.get("story_question")
                or blueprint.get("story_seed", {}).get("story_question", "")
            ),
            "world_engine": world_engine,
            "target_words": payload.target_words,
            "total_chapters": total_chapters,
            "volume_count": volume_count,
            "scale_plan": blueprint.get("book_blueprint", {}).get("scale_plan", {})
            if isinstance(blueprint.get("book_blueprint"), dict)
            else {},
        },
        "is_sealed": False,
    }
    outlines.append(book_outline)
    toc_nodes.append(
        {
            "level": "book",
            "sequence": 1,
            "title": title,
            "summary": payload.one_sentence,
            "characters": [payload.protagonist_name],
            "key_events": ["故事启动"],
            "chapter_range_start": 1,
            "chapter_range_end": total_chapters,
        }
    )

    # 多卷大纲树：书 → 卷锚点（第一卷详细，后续卷待滚动规划）→ 章
    volume_outlines: list[dict] = []
    volume_tocs: list[dict] = []
    for anchor in volume_anchors:
        vol_range = anchor["chapter_range"]
        if anchor["status"] == "detailed":
            content = {
                "title": first_volume.get("title") or anchor["title"],
                "goal": first_volume.get("goal") or "围绕故事核心展开第一阶段",
                "opening": first_volume.get("opening", ""),
                "turning_points": first_volume.get("turning_points", []),
                "climax": first_volume.get("climax", ""),
                "ending_hook": first_volume.get("ending_hook", ""),
                "protected_reveals": first_volume.get("protected_reveals", []),
                "opening_window": first_volume.get("opening_window", {}),
                "chapter_directions": first_volume.get("chapter_directions", []),
                "scale_plan": blueprint.get("book_blueprint", {}).get("scale_plan", {})
                if isinstance(blueprint.get("book_blueprint"), dict)
                else {},
                "stage_title": anchor["stage_title"],
                "chapter_range": vol_range,
                "status": "detailed",
            }
        else:
            content = {
                "goal": f"待第{anchor['sequence']}卷开始前滚动规划",
                "stage_title": anchor["stage_title"],
                "chapter_range": vol_range,
                "status": "anchor",
            }
        volume_outlines.append({
            "level": "volume",
            "sequence": anchor["sequence"],
            "title": content.get("title") or anchor["title"],
            "content": content,
            "is_sealed": False,
        })
        volume_tocs.append({
            "level": "volume",
            "sequence": anchor["sequence"],
            "title": content.get("title") or anchor["title"],
            "summary": content.get("goal", ""),
            "characters": [payload.protagonist_name],
            "key_events": [],
            "chapter_range_start": vol_range[0],
            "chapter_range_end": vol_range[1],
        })

    outlines.extend(volume_outlines)
    toc_nodes.extend(volume_tocs)
    chapters.append(
        {
            "volume_sequence": 1,
            "chapter_sequence": 1,
            "title": "第1章",
            "summary": "",
            "status": "unplanned",
        }
    )

    return BootstrapBundle(
        style_profile=style_profile,
        wiki_pages=wiki_pages,
        outlines=outlines,
        toc_nodes=toc_nodes,
        chapters=chapters,
        generation_state={
            "active": False,
            "auto_write": (
                "自动推进整卷" in str(author_constitution.get("ai_mandate") or "")
                and not world_validation
            ),
            "last_event": None,
            "estimated_total_chapters": total_chapters,
            "creation_phase": "world_review" if world_validation else "character_seed",
            "world_validation": {
                "status": "pass" if not world_validation else "review_required",
                "blocking_issues": world_validation,
            },
        },
    )
