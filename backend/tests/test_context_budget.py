from app.api.chapters import _chapter_planning_context
from app.engine.context import (
    _compact_chapter_outline,
    _compact_story_plan,
    _compact_style_profile,
    _strategic_memory,
    context_for_node,
)


def test_compact_chapter_outline_removes_embedded_creation_brief() -> None:
    outline = {
        "goal": "推进眼前冲突",
        "beats": [{"event": "主角采取行动"}],
        "creation_brief": {"position": {"volume_plan": {"huge": "x" * 50_000}}},
    }

    compact = _compact_chapter_outline(outline)

    assert compact == {"goal": "推进眼前冲突", "beats": [{"event": "主角采取行动"}]}


def test_compact_story_plan_keeps_only_current_chapter_direction() -> None:
    plan = {
        "title": "第一卷",
        "goal": "守住客栈",
        "opening_window": {"duplicated": "x" * 30_000},
        "chapter_directions": [
            {"sequence": 1, "main_action": "接待客人"},
            {"sequence": 2, "main_action": "检查桌椅痕迹"},
        ],
    }

    compact = _compact_story_plan(plan, 2)

    assert compact["title"] == "第一卷"
    assert compact["current_chapter_mandate"]["main_action"] == "检查桌椅痕迹"
    assert "opening_window" not in compact
    assert "chapter_directions" not in compact


def test_compact_story_plan_drops_early_direction_after_chapter_plan_is_confirmed() -> None:
    plan = {
        "title": "第一卷",
        "goal": "守住客栈",
        "chapter_directions": [
            {"sequence": 2, "main_action": "建书时预想的旧行动"},
        ],
        "protected_reveals": ["掌柜的真实身份"],
    }

    compact = _compact_story_plan(plan, 2, include_chapter_direction=False)

    assert "current_chapter_mandate" not in compact
    assert compact["goal"] == "守住客栈"
    assert compact["protected_reveals"] == ["掌柜的真实身份"]


def test_workspace_planning_context_keeps_volume_boundary_but_not_opening_draft() -> None:
    context = _chapter_planning_context(
        {
            "title": "第一卷",
            "goal": "守住客栈",
            "chapter_range": [1, 30],
            "chapter_directions": [{"sequence": 3, "main_action": "旧草案行动"}],
            "opening_window": {"chapter_directions": [{"sequence": 3, "main_action": "重复旧草案"}]},
            "protected_reveals": ["掌柜的真实身份"],
        },
        {},
        3,
    )

    assert context["volume_goal"] == "守住客栈"
    assert context["protected_reveals"] == ["掌柜的真实身份"]
    assert "current_chapter_mandate" not in context
    assert "opening_window" not in context


def test_compact_style_profile_does_not_send_creation_blueprint_to_every_node() -> None:
    profile = {
        "writing_contract": {"prose": "自然克制"},
        "author_constitution": {"reader_promise": "选择有代价"},
        "creation_blueprint": {"entire_book": "x" * 50_000},
        "world_engine": {"entire_world": "x" * 50_000},
    }

    compact = _compact_style_profile(profile)

    assert compact["writing_contract"]["prose"] == "自然克制"
    assert "creation_blueprint" not in compact
    assert "world_engine" not in compact


def test_strategic_memory_keeps_unique_long_range_intent_and_relevant_characters() -> None:
    profile = {
        "creation_blueprint": {
            "creation_v2": {
                "core": {"central_question": "主角是否会为真相付出代价"},
                "world": {"core_rule": "每次借力都留下痕迹"},
                "stages": [
                    {"name": "开局", "chapter_range": [1, 20], "goal": "查清来客身份"},
                    {"name": "远行", "chapter_range": [21, 50], "goal": "进入京城"},
                ],
                "protagonist": {"name": "陆景", "fear": "再次失去家人"},
            },
            "characters": [
                {"name": "陆景", "desire": "守住客栈"},
                {"name": "白晓晓", "desire": "寻找旧案"},
                {"name": "未登场者", "desire": "不应进入本章"},
            ],
        }
    }

    memory = _strategic_memory(profile, 2, ["陆景", "白晓晓"])

    assert memory["core_intent"]["central_question"].startswith("主角")
    assert memory["current_stage"]["name"] == "开局"
    assert [item["name"] for item in memory["scene_character_designs"]] == ["陆景", "白晓晓"]


def test_strategic_memory_keeps_external_research_outside_canon() -> None:
    profile = {
        "creation_blueprint": {
            "creation_v2": {"core": {"central_question": "主角会如何选择"}},
            "web_research": {
                "status": "completed",
                "memo": "现实职业资料",
                "sources": [{"title": "官方来源", "url": "https://example.cn"}],
            },
        }
    }

    memory = _strategic_memory(profile, 1, [])

    assert memory["external_research"]["memo"] == "现实职业资料"
    assert "不是小说 Canon" in memory["rule"]


def test_context_for_node_uses_different_views_and_reports_manifest() -> None:
    pack = {
        "project": {"title": "测试"},
        "chapter_sequence": 2,
        "chapter_outline": {"goal": "推进"},
        "strategic_memory": {"core_intent": {"reader_promise": "选择有代价"}},
        "writing_guidance": {"method_cards": ["场景方法"]},
        "serialized_characters": 9999,
    }

    simulation = context_for_node(pack, "world-simulator")
    writer = context_for_node(pack, "novel-writer")

    assert "writing_guidance" not in simulation
    assert writer["writing_guidance"]["method_cards"] == ["场景方法"]
    assert simulation["strategic_memory"]["core_intent"]["reader_promise"] == "选择有代价"
    assert writer["context_manifest"]["source_pack_characters"] == 9999


def test_writer_context_trims_refetchable_evidence_but_keeps_authored_memory() -> None:
    pack = {
        "project": {"title": "测试"},
        "chapter_sequence": 2,
        "chapter_outline": {"goal": "绝不能丢的本章目标"},
        "strategic_memory": {"core_intent": {"central_question": "绝不能丢的核心命题"}},
        "living_memory": {"previous_ending": "绝不能丢的前章结尾"},
        "writing_guidance": {"source_excerpts": ["教程" * 5_000]},
        "pageindex": {"source_excerpts": [{"content": "历史摘录" * 3_000}]},
        "retrieval_hits": [{"content": "命中" * 500} for _ in range(10)],
        "wiki": [{"title": f"人物{i}", "content": "设定" * 500} for i in range(10)],
    }

    writer = context_for_node(pack, "novel-writer")

    assert writer["chapter_outline"]["goal"].startswith("绝不能丢")
    assert writer["strategic_memory"]["core_intent"]["central_question"].startswith("绝不能丢")
    assert writer["living_memory"]["previous_ending"].startswith("绝不能丢")
    assert writer["serialized_characters"] <= 15_000
    assert writer["context_manifest"]["reduced_refetchable_sections"]
