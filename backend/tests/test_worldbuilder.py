from itertools import pairwise

from app.engine.worldbuilder import (
    build_project_bootstrap,
    get_genre_world_contract,
    validate_character_agency,
    validate_world_engine,
)
from app.schemas import ProjectCreate


def test_maximum_long_form_bootstrap_builds_multi_volume_tree() -> None:
    payload = ProjectCreate(
        title="长篇边界测试",
        genre="玄幻",
        one_sentence="主角跨越十二个阶段追查一场改变世界秩序的旧案。",
        protagonist_name="林川",
        protagonist_gender="男",
        protagonist_personality="谨慎但愿意承担选择的代价",
        target_words=4_200_000,
    )
    bundle = build_project_bootstrap(payload)

    assert bundle.generation_state["estimated_total_chapters"] == 1273
    assert bundle.chapters == [{
        "volume_sequence": 1,
        "chapter_sequence": 1,
        "title": "第1章",
        "summary": "",
        "status": "unplanned",
    }]
    volume_nodes = [node for node in bundle.toc_nodes if node["level"] == "volume"]
    assert len(volume_nodes) >= 8  # 百万字级必须多卷
    assert volume_nodes[0]["chapter_range_start"] == 1
    assert volume_nodes[-1]["chapter_range_end"] == 1273
    # 卷区间连续无缝
    for prev, nxt in pairwise(volume_nodes):
        assert nxt["chapter_range_start"] == prev["chapter_range_end"] + 1
    # 第一卷详细、后续卷锚点
    vol_outlines = [o for o in bundle.outlines if o["level"] == "volume"]
    assert vol_outlines[0]["content"]["status"] == "detailed"
    assert all(o["content"]["status"] == "anchor" for o in vol_outlines[1:])


def test_eight_million_word_bootstrap_keeps_volume_anchors_valid() -> None:
    payload = ProjectCreate(
        title="超长篇边界测试",
        genre="玄幻",
        one_sentence="主角在漫长时代更替中追索一场横跨诸域的因果旧案。",
        protagonist_name="林川",
        protagonist_gender="男",
        protagonist_personality="谨慎但愿意承担选择的代价",
        target_words=8_000_000,
    )
    bundle = build_project_bootstrap(payload)

    assert bundle.generation_state["estimated_total_chapters"] == 2424
    volume_nodes = [node for node in bundle.toc_nodes if node["level"] == "volume"]
    assert len(volume_nodes) == 20
    assert volume_nodes[-1]["title"] == "第二十卷"
    assert volume_nodes[-1]["chapter_range_end"] == 2424


def test_creation_blueprint_is_preserved_in_style_profile() -> None:
    payload = ProjectCreate(
        title="蓝图测试",
        genre="悬疑",
        one_sentence="普通人追查旧案时发现自己的一段记忆正是案件缺失的证据。",
        protagonist_name="周明",
        protagonist_gender="男",
        protagonist_personality="敏感谨慎，但无法对受害者袖手旁观",
        planning_profile={"reader_promise": "每卷解开一层真相", "major_arcs": [{"title": "旧案重启"}]},
    )
    bundle = build_project_bootstrap(payload)
    assert bundle.style_profile["creation_blueprint"]["reader_promise"] == "每卷解开一层真相"


def test_author_constitution_is_preserved_and_controls_autopilot() -> None:
    payload = ProjectCreate(
        title="心意测试",
        genre="现实",
        one_sentence="一个胆怯的人为了不再失信，决定公开自己隐瞒多年的真相。",
        protagonist_name="周明",
        protagonist_gender="男",
        protagonist_personality="胆怯但珍惜承诺",
        planning_profile={
            "author_constitution": {
                "why_write": "想写诚实的代价",
                "lasting_feeling": "害怕时仍能选择诚实",
                "non_negotiables": "不把创伤当爽点",
                "ai_mandate": "在创作宪章内自动推进整卷，只在质量门失败时停下来",
                "chapter_test": "人物是否为选择付出代价",
            }
        },
    )

    bundle = build_project_bootstrap(payload)

    assert bundle.style_profile["author_constitution"]["why_write"] == "想写诚实的代价"
    assert bundle.generation_state["auto_write"] is True
    assert any(page["title"] == "作者创作宪章" for page in bundle.wiki_pages)


def test_combined_genre_uses_suspense_contract_and_seeds_confirmed_characters() -> None:
    payload = ProjectCreate(
        title="灯灭之后",
        genre="悬疑 / 现实",
        one_sentence="调解员从一张日期矛盾的维修收据追查老人摔亡责任。",
        protagonist_name="沈越",
        protagonist_gender="男",
        protagonist_personality="怕冲突却记性很好",
        target_words=120_000,
        planning_profile={
            "characters": [
                {
                    "name": "沈越",
                    "gender": "男",
                    "role": "社区调解员",
                    "personality": "怕冲突",
                    "desire": "保住工作",
                    "flaw": "习惯压事",
                    "relationship": "赵巧兰之子",
                },
                {
                    "name": "赵巧兰",
                    "gender": "女",
                    "role": "主角母亲",
                    "personality": "体面要强",
                    "desire": "搬进养老房",
                    "flaw": "碍于人情预签验收",
                    "relationship": "沈越的母亲",
                }
            ]
        },
    )

    bundle = build_project_bootstrap(payload)

    assert "无证据反转" in bundle.style_profile["writing_contract"]["avoid"]
    assert any(page["title"] == "沈越" and "保住工作" in page["content"] for page in bundle.wiki_pages)
    assert any(page["title"] == "赵巧兰" and "搬进养老房" in page["content"] for page in bundle.wiki_pages)


def test_world_engine_is_type_specific_and_persisted() -> None:
    fantasy = get_genre_world_contract("玄幻")
    romance = get_genre_world_contract("现代言情")
    assert fantasy["engine_name"] != romance["engine_name"]
    assert "境界" in fantasy["progression_axes"]
    assert "关系信任" in romance["progression_axes"]

    payload = ProjectCreate(
        title="世界先行",
        genre="玄幻",
        one_sentence="矿奴为了救出妹妹进入宗门争夺灵脉。",
        protagonist_name="陆沉",
        protagonist_gender="男",
        protagonist_personality="谨慎而固执",
    )
    bundle = build_project_bootstrap(payload)
    assert bundle.style_profile["world_validation"]["status"] == "pass"
    assert bundle.generation_state["creation_phase"] == "character_seed"
    assert "世界发动机" in next(page for page in bundle.wiki_pages if page["slug"] == "world-core")["content"]


def test_world_engine_without_cost_is_blocked() -> None:
    world = {
        **get_genre_world_contract("玄幻"),
        "core_cost": "",
        "limitations": [],
        "costs": [],
    }
    issues = validate_world_engine(world, "玄幻")
    assert any("限制或代价" in issue for issue in issues)


def test_strict_world_engine_requires_scene_level_pressure() -> None:
    world = get_genre_world_contract("仙侠奇缘")
    issues = validate_world_engine(world, "仙侠奇缘", strict=True)
    assert world["primary_genre"] == "仙侠"
    assert "缺少能被场景验证的核心规则" in issues
    assert any("压力测试" in issue for issue in issues)


def test_character_agency_requires_desire_method_line_and_action() -> None:
    assert validate_character_agency({"desire": "救妹妹"}) == [
        "人物缺少有个人特色的解决问题方法",
        "人物缺少不可轻易跨越的底线",
        "人物缺少压力下会采取的主动行为",
    ]
    assert validate_character_agency({
        "desire": "救妹妹",
        "method": "先交换情报再冒险",
        "bottom_line": "不拿无辜者试药",
        "pressure_action": "主动公开自己的禁术换取谈判机会",
    }) == []


def test_nested_wizard_blueprint_seeds_volume_goal_and_story_question() -> None:
    payload = ProjectCreate(
        title="滚动规划",
        genre="武侠",
        one_sentence="镖师为洗清污名追查一批被调换的赈灾银。",
        protagonist_name="沈砚",
        protagonist_gender="男",
        protagonist_personality="谨慎但不肯牺牲无辜",
        planning_profile={
            "story_question": "沈砚能否洗清污名而不出卖救过自己的山寨？",
            "book_blueprint": {"major_arcs": [{"title": "失镖"}, {"title": "入局"}, {"title": "抉择"}]},
            "first_volume": {"goal": "找出银箱被调换的地点"},
        },
    )
    bundle = build_project_bootstrap(payload)
    first_volume = next(item for item in bundle.outlines if item["level"] == "volume")
    book = next(item for item in bundle.outlines if item["level"] == "book")
    assert first_volume["content"]["goal"] == "找出银箱被调换的地点"
    assert first_volume["content"]["stage_title"] == "失镖"
    assert "洗清污名" in book["content"]["story_question"]
