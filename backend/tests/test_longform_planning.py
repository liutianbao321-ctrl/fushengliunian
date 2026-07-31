import pytest

from app.engine.context import summarize_creation_brief
from app.services.replan import generate_next_volume_plan
from app.services.skill_loader import load_skill_prompt


def test_skill_loader_injects_project_skill_without_frontmatter() -> None:
    prompt = load_skill_prompt("novel-writer")
    assert "# 小说写手" in prompt
    assert "name: novel-writer" not in prompt
    assert load_skill_prompt("world-simulator") == ""


def test_creation_brief_marks_due_foreshadowing_and_explains_reason() -> None:
    brief = summarize_creation_brief({
        "chapter_sequence": 20,
        "story_position": {"volume_title": "第二卷", "arc_title": "失踪案", "arc_plan": {}},
        "foreshadowing": [
            {"content": "旧钥匙来源", "target_chapter": 20, "importance": "A"},
            {"content": "远方来信", "target_chapter": 80, "importance": "B"},
        ],
        "active_state": [{"entity_key": "林川", "field": "位置", "value": "旧宅"}],
        "recent_chapters": [],
        "scene_entities": ["林川"],
        "style_profile": {"writing_contract": {"rhythm": "紧凑"}},
    })
    assert brief["due_foreshadowing"][0]["urgency"] == "overdue"
    assert brief["due_foreshadowing"][1]["urgency"] == "active"
    assert "伏笔进入推进或回收窗口" in brief["why_this_chapter"]
    assert brief["character_states"]["林川"][0]["value"] == "旧宅"


@pytest.mark.asyncio
async def test_mock_replan_is_complete_and_handles_overdue_foreshadowing(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.replan.get_settings",
        lambda: type("Settings", (), {"llm_backend": "mock"})(),
    )
    result = await generate_next_volume_plan({
        "next_volume_sequence": 2,
        "project": {"protagonist": "林川"},
        "active_foreshadowing": [{"content": "旧钥匙来源", "overdue": True}],
    })
    assert len(result["arcs"]) == 4
    assert "旧钥匙来源" in result["foreshadowing_to_resolve"]
    assert all(arc["goal"] and arc["resolution"] for arc in result["arcs"])
