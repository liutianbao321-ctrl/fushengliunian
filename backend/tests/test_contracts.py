import pytest
import json

from app.engine.changes import keep_evidenced_changes, merge_extractions, normalize_change, normalize_confidence
from app.engine.contracts import NodeContractError, validate_node_output
from app.engine.guardian import run_guardian_checks
from app.engine.humanizer import humanize_text
from app.engine.pipeline import (
    _evidenced_repair_issues,
    _hard_review_issues,
    _repairable_review_issues,
    _review_score,
    _rewrite_draft,
)
from app.engine.quality import find_pov_violations, max_consecutive_undirected_dialogue, outline_is_concrete
from app.engine.runtime import _architect_authored_continuity, mock_node, normalize_node_output, run_agent_node
from app.engine.wiki import extract_wikilinks
from app.engine.worldbuilder import get_genre_writing_contract
from app.utils.canonical import parse_json_object, payload_hash


def context_pack() -> dict:
    return {
        "project": {"protagonist": "林川"},
        "chapter_sequence": 2,
        "chapter_outline": {"goal": "林川必须在日落前找到失踪的账册"},
        "scene_entities": ["林川"],
        "recent_chapters": [{"sequence": 1, "summary": "线索中断"}],
        "active_state": [],
        "foreshadowing": [],
    }


def test_canonical_hash_is_order_independent() -> None:
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})
    assert parse_json_object('```json\n{"ok": true}\n```') == {"ok": True}


def test_repairs_minor_model_json_errors_and_groups_observer_changes() -> None:
    parsed = parse_json_object(
        '```json\n{"changes":[{"type":"knowledge","name":"林川",'
        '"new":"验证了"线索可信"","confidence":0.8}]}\n```'
    )
    normalized = normalize_node_output("observer-social", parsed, {})

    assert normalized["changes"]["knowledge"][0]["name"] == "林川"
    assert "线索可信" in normalized["changes"]["knowledge"][0]["new"]


def test_verifier_normalizes_single_item_collections() -> None:
    normalized = normalize_node_output(
        "novel-verifier",
        {"changes": {}, "omissions": {"one": {"field": "去向"}}, "conflicts": {"one": "时间冲突"}},
        {},
    )

    assert normalized["omissions"] == [{"field": "去向"}]
    assert normalized["conflicts"] == ["时间冲突"]


def test_verifier_normalizes_single_text_conflict() -> None:
    normalized = normalize_node_output(
        "novel-verifier",
        {"changes": {}, "omissions": None, "conflicts": "未发现状态冲突"},
        {},
    )

    assert normalized["omissions"] == []
    assert normalized["conflicts"] == []


def test_observer_recovers_dimension_from_misplaced_field() -> None:
    normalized = normalize_node_output(
        "observer-social",
        {
            "changes": {
                "other": [
                    {"entity_key": "沈越", "field": "knowledge", "new": "记住了批号", "confidence": 0.9}
                ]
            }
        },
        {},
    )

    assert normalized["changes"]["knowledge"][0]["entity_key"] == "沈越"
    assert "other" not in normalized["changes"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("high", 0.9), ("medium", 0.7), ("low", 0.4), ("85%", 0.85), (85, 0.85), ("unknown", 0.6)],
)
def test_confidence_accepts_model_labels_and_percentages(raw, expected) -> None:
    assert normalize_confidence(raw) == expected


def test_verifier_change_with_label_confidence_is_mergeable() -> None:
    change = normalize_change("knowledge", {"name": "林川", "new": "得知密信内容", "confidence": "high"})
    assert change["confidence"] == 0.9


def test_editor_rejects_an_abbreviated_long_draft() -> None:
    from app.engine.runtime import _validate_editor_completeness

    with pytest.raises(ValueError, match="过度压缩"):
        _validate_editor_completeness(
            {"content": "修" * 2100},
            {"draft": {"content": "初" * 4400}},
        )

    _validate_editor_completeness(
        {"content": "修" * 3400},
        {"draft": {"content": "初" * 5100}},
    )


def test_editor_uses_full_prose_output_channel() -> None:
    from app.engine.runtime import PROSE_NODES

    assert "novel-editor" in PROSE_NODES


def test_only_evidenced_hard_review_issues_trigger_repair() -> None:
    review = {
        "issues": [
            {"category": "prose_naturalness", "blocking": False, "evidence": "句式重复"},
            {"hard_category": "broken_causality", "blocking": True, "evidence": "他尚未拿钥匙便开了门"},
            {"hard_category": "pov_violation", "blocking": True, "evidence": ""},
        ]
    }
    assert [issue["hard_category"] for issue in _hard_review_issues(review)] == ["broken_causality"]


def test_evidenced_major_narrative_failure_triggers_real_repair() -> None:
    review = {
        "issues": [
            {
                "id": "continuity-1",
                "severity": "major",
                "category": "consciousness_continuity",
                "evidence": "她收回手。半个时辰后，她冷静地分析起局势。",
                "blocking": False,
            },
            {
                "id": "taste-1",
                "severity": "minor",
                "category": "prose_naturalness",
                "evidence": "一句普通的风格偏好",
                "blocking": False,
            },
        ]
    }

    assert [issue["id"] for issue in _repairable_review_issues(review)] == ["continuity-1"]


def test_critic_paraphrase_cannot_trigger_a_repair() -> None:
    review = {
        "issues": [
            {
                "id": "invented",
                "severity": "major",
                "category": "consciousness_continuity",
                "evidence": "正文：'她冷静地分析了眼前局势。' 这里重置了人物状态",
                "blocking": False,
            },
            {
                "id": "exact",
                "severity": "major",
                "category": "character_specificity",
                "evidence": "正文：'她把公交卡的折角压进掌心。'",
                "blocking": False,
            },
        ]
    }

    accepted, rejected = _evidenced_repair_issues(review, "她把公交卡的折角压进掌心。门外还在下雨。")

    assert [issue["id"] for issue in accepted] == ["exact"]
    assert [issue["id"] for issue in rejected] == ["invented"]


def test_cross_chapter_transition_uses_evidence_from_both_chapters() -> None:
    review = {
        "issues": [
            {
                "id": "transition-reset",
                "severity": "major",
                "category": "consciousness_continuity",
                "evidence": (
                    "上一章结尾：白晓晓死死攥住陆景的衣角……马蹄声逼近客栈门口\n"
                    "第二章开头：白晓晓趴在柜台上……急促沉重的马蹄声突然撞碎了深夜的宁静"
                ),
                "blocking": False,
            }
        ]
    }
    current = "白晓晓趴在柜台上。急促沉重的马蹄声突然撞碎了深夜的宁静。"
    previous = "白晓晓死死攥住陆景的衣角。马蹄声逼近客栈门口。"

    accepted, rejected = _evidenced_repair_issues(review, current, previous)

    assert [issue["id"] for issue in accepted] == ["transition-reset"]
    assert rejected == []


def test_cross_chapter_transition_requires_evidence_on_both_sides() -> None:
    review = {
        "issues": [
            {
                "id": "invented-transition",
                "severity": "major",
                "category": "consciousness_continuity",
                "evidence": "上一章结尾：并不存在的追兵已经进门\n本章开头：白晓晓趴在柜台上",
                "blocking": False,
            }
        ]
    }

    accepted, rejected = _evidenced_repair_issues(
        review, "白晓晓趴在柜台上。", "陆景关上客栈大门。"
    )

    assert accepted == []
    assert [issue["id"] for issue in rejected] == ["invented-transition"]


@pytest.mark.asyncio
async def test_unresolved_cross_chapter_transition_blocks_publication(monkeypatch) -> None:
    from app.engine.quality import evaluate_quality_gates

    class Scalars:
        def all(self):
            return []

    class Db:
        async def scalar(self, _query):
            return type("Outline", (), {"meta": {"goal": "承接追兵破门并应战"}})()

        async def scalars(self, _query):
            return Scalars()

    monkeypatch.setattr(
        "app.engine.quality.get_settings",
        lambda: type("Settings", (), {"content_red_line_keywords": []})(),
    )
    project = type(
        "Project",
        (),
        {
            "id": __import__("uuid").uuid4(),
            "protagonist_name": "陆景",
            "style_profile": {},
        },
    )()
    issue = {"id": "transition-reset", "category": "consciousness_continuity"}

    gates = await evaluate_quality_gates(
        Db(),
        project,
        2,
        "正文" * 1600,
        {"goal": "承接追兵破门并应战", "beats": [{"event": "伤员破门而入引来杀手"}, {"event": "陆景出手解决杀手并检查令牌"}]},
        {"passed": True, "failures": []},
        [],
        unresolved_cross_chapter_issues=[issue],
    )

    gate = next(item for item in gates if item.name == "cross_chapter_transition")
    assert gate.blocking is True
    assert gate.passed is False


def test_architect_contract_carries_consciousness_across_every_scene() -> None:
    context = context_pack()
    result = mock_node("novel-architect", {"context_pack": context})

    validated = validate_node_output("novel-architect", result)

    assert len(validated["consciousness_thread"]["scene_threads"]) == len(validated["beats"])
    assert all(item["residue"] for item in validated["consciousness_thread"]["scene_threads"])


def test_architect_continuity_must_include_authored_carry_in_and_aftertaste() -> None:
    output = mock_node("novel-architect", {"context_pack": context_pack()})
    assert _architect_authored_continuity(output) is True

    output["consciousness_thread"]["chapter_aftertaste"] = {}
    assert _architect_authored_continuity(output) is False


def test_state_changes_require_an_exact_chapter_quote() -> None:
    changes = [
        {"dimension": "knowledge", "entity_key": "林川", "field": "线索", "evidence": {"quote": "林川认出了旧印"}},
        {"dimension": "timeline", "entity_key": "故事", "field": "进度", "evidence": {"quote": "并不存在的句子"}},
    ]
    accepted, rejected = keep_evidenced_changes(changes, "雨里，林川认出了旧印，随后把信收好。")
    assert len(accepted) == 1
    assert len(rejected) == 1


def test_three_scene_outline_satisfies_outline_contract() -> None:
    beats = [{"event": "沈越核对现场材料并拍下灯具铭牌"}] * 3
    assert outline_is_concrete(beats, "核对收据与现场灯具是否对应") is True


def test_rewrite_uses_existing_chapter_as_editorial_source() -> None:
    chapter = type("Chapter", (), {"summary": "原摘要"})()
    context = {"rewrite": {"source_content": "需要保留并修订的正文"}}

    assert _rewrite_draft(context, chapter) == {"content": "需要保留并修订的正文", "summary": "原摘要"}


def test_editorial_score_is_diagnostic_only() -> None:
    assert _review_score({"score": "83"}) == 83


def test_critic_normalizes_common_model_variants() -> None:
    normalized = normalize_node_output(
        "novel-critic-final",
        {
            "passed": "通过",
            "score": "8.2",
            "dimensions": [{"name": "opening_hook", "score": 78}],
            "issues": {},
            "strengths": {"one": "人物选择清楚"},
            "rewrite_brief": {},
        },
        {},
    )

    assert normalized["passed"] is True
    assert normalized["score"] == 82
    assert normalized["dimensions"] == {"opening_hook": 78}
    validate_node_output("novel-critic", normalized)


def test_critic_normalizes_single_text_strength() -> None:
    normalized = normalize_node_output(
        "novel-critic",
        {
            "passed": True,
            "score": 86,
            "dimensions": {},
            "issues": [],
            "strengths": "人物行动可信",
            "rewrite_brief": None,
        },
        {},
    )

    assert normalized["strengths"] == ["人物行动可信"]
    assert normalized["rewrite_brief"] == []


def test_mock_writer_produces_publishable_length() -> None:
    context = context_pack()
    beat_sheet = mock_node("novel-architect", {"context_pack": context})
    result = mock_node("novel-writer", {"context_pack": context, "beat_sheet": beat_sheet})
    word_count = len(result["content"].replace("\n", ""))
    assert 2800 <= word_count <= 5500
    assert result["summary"]


@pytest.mark.asyncio
async def test_humanizer_keeps_source_when_polish_overcompresses(monkeypatch) -> None:
    source = "原稿中的动作、对话与关系余波必须完整保留。" * 100

    async def compressed(*_args, **_kwargs):
        return "被压成摘要。" * 20

    monkeypatch.setattr("app.engine.humanizer.llm_client.complete", compressed)
    monkeypatch.setattr(
        "app.engine.humanizer.get_settings",
        lambda: type("Settings", (), {"llm_backend": "openai_compatible", "generation_max_tokens_prose": 8192})(),
    )

    content, _metrics = await humanize_text(source)

    assert content == source


@pytest.mark.asyncio
async def test_remote_writer_accepts_naturally_long_text(monkeypatch) -> None:
    context = context_pack()
    beat_sheet = mock_node("novel-architect", {"context_pack": context})
    responses = ["甲" * 6000 + "\n===SUMMARY===\n偏长但完整"]
    calls: list[str] = []

    async def remote(_system_prompt, user_prompt, **_kwargs):
        calls.append(user_prompt)
        return responses[len(calls) - 1]

    monkeypatch.setattr(
        "app.engine.runtime.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "llm_backend": "openai_compatible",
                "generation_max_tokens_prose": 8192,
                "generation_max_tokens_structured": 4096,
            },
        )(),
    )
    monkeypatch.setattr("app.engine.runtime.llm_client.complete", remote)

    result = await run_agent_node(
        "novel-writer",
        {
            "context_pack": context,
            "beat_sheet": beat_sheet,
            "requirements": {"target_length": [3400, 4200], "hard_length_range": [2800, 5500]},
        },
        "test",
    )

    assert len(calls) == 1
    assert len(result["content"]) == 6000
    assert result["summary"] == "偏长但完整"


@pytest.mark.asyncio
async def test_structured_node_falls_back_when_primary_returns_non_json(monkeypatch) -> None:
    context = context_pack()
    calls: list[str | None] = []

    async def remote(_system_prompt, _user_prompt, **kwargs):
        calls.append(kwargs.get("model"))
        if len(calls) == 1:
            return "我先解释一下，不返回 JSON。"
        return json.dumps(mock_node("world-simulator", {"context_pack": context}), ensure_ascii=False)

    monkeypatch.setattr(
        "app.engine.runtime.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "llm_backend": "openai_compatible",
                "llm_model": "gemini-primary",
                "llm_fallback_models": [],
                "llm_fallback_model": None,
                "llm_planning_model": "gemini-planning",
                "llm_planning_fallback_models": [],
                "llm_planning_fallback_model": None,
                "llm_aliyun_model": "qwen-plus",
                "llm_aliyun_planning_model": None,
                "llm_deepseek_model": None,
                "generation_max_tokens_prose": 8192,
                "generation_max_tokens_structured": 4096,
            },
        )(),
    )
    monkeypatch.setattr("app.engine.runtime.llm_client.complete", remote)

    result = await run_agent_node("world-simulator", {"context_pack": context}, "test")

    assert result["simulation_id"]
    assert calls == ["aliyun:qwen-plus", "gemini-planning"]


def test_guardian_has_ten_deterministic_checks() -> None:
    context = context_pack()
    beat_sheet = mock_node("novel-architect", {"context_pack": context})
    result = run_guardian_checks(context, beat_sheet)
    assert result["passed"] is True
    assert len(result["checks"]) == 10


def test_dialogue_attribution_accepts_named_character_actions() -> None:
    content = "\n".join(
        [
            "“不信可以搜。”陆景摊手。",
            "“当真？”崔一刀皱眉。",
            "“请便。”陆景让开柜台。",
        ]
    )

    assert max_consecutive_undirected_dialogue(content, {"陆景", "崔一刀"}) == 0


def test_dialogue_attribution_still_rejects_three_unidentified_lines() -> None:
    content = "\n".join(["“不信可以搜。”", "“当真？”", "“请便。”"])

    assert max_consecutive_undirected_dialogue(content, {"陆景", "崔一刀"}) == 3


def test_guardian_accepts_concise_event_names_with_complete_scene_causality() -> None:
    context = context_pack()
    beat_sheet = mock_node("novel-architect", {"context_pack": context})
    beat_sheet["beats"] = [
        {
            "segment": "一",
            "event": "睁眼认身",
            "immediate_goal": "确认身份与所在",
            "obstacle": "身体陌生且门外有人催促",
            "turn": "来人叫出主角的新身份",
            "outcome": "主角决定先隐藏异常",
        },
        {
            "segment": "二",
            "event": "接规矩",
            "immediate_goal": "不在来人面前露出破绽",
            "obstacle": "对方不断试探主角的反应",
            "turn": "主角反客为主压住试探",
            "outcome": "对方暂时相信主角一切正常",
        },
    ]

    result = run_guardian_checks(context, beat_sheet)

    concrete_events = next(item for item in result["checks"] if item["name"] == "concrete_events")
    assert concrete_events["passed"] is True
    assert result["passed"] is True


def test_guardian_rejects_concise_event_names_without_scene_causality() -> None:
    context = context_pack()
    beat_sheet = mock_node("novel-architect", {"context_pack": context})
    beat_sheet["beats"] = [{"segment": "一", "event": "醒来"}, {"segment": "二", "event": "出门"}]

    result = run_guardian_checks(context, beat_sheet)

    concrete_events = next(item for item in result["checks"] if item["name"] == "concrete_events")
    assert concrete_events["passed"] is False
    assert result["passed"] is False


def test_observer_merge_records_disagreement() -> None:
    first = {"changes": {"character_state": [{"name": "林川", "field": "位置", "new": "城东", "confidence": 0.7}]}}
    second = {"changes": {"character_state": [{"name": "林川", "field": "位置", "new": "城东", "confidence": 0.8}]}}
    third = {"changes": {"character_state": [{"name": "林川", "field": "位置", "new": "城西", "confidence": 0.6}]}}
    merged, issues = merge_extractions([first, second, third])
    assert merged[0]["new_value"] == {"value": "城东"}
    assert merged[0]["confidence"] >= 0.8
    assert len(issues) == 1


def test_environment_changes_use_distinct_evidence_entities() -> None:
    extraction = {
        "changes": {
            "location_state": [
                {"field": "场景状态", "new": "楼道昏暗", "evidence": {"location": "三号楼楼道"}},
                {"field": "场景状态", "new": "办公室亮灯", "evidence": {"location": "调解办公室"}},
            ],
            "item_state": [
                {"field": "存在状态", "new": "已记录", "evidence": {"item": "厂家电话便签"}},
                {"field": "存在状态", "new": "已归档", "evidence": {"item": "待补材料文件袋"}},
            ],
        }
    }
    merged, issues = merge_extractions([extraction])
    assert {item["entity_key"] for item in merged} == {
        "三号楼楼道",
        "调解办公室",
        "厂家电话便签",
        "待补材料文件袋",
    }
    assert issues == []


def test_change_normalization_accepts_model_evidence_lists() -> None:
    change = normalize_change(
        "character_state",
        {
            "entity_key": "沈晚烟",
            "field": "处境",
            "new": "暂时稳住身份",
            "evidence": ["压住老鸨试探", "楼内无人起疑"],
        },
    )

    assert change["evidence"] == {"details": ["压住老鸨试探", "楼内无人起疑"]}


def test_verifier_rejection_removes_overinterpreted_observer_change() -> None:
    extraction = {
        "changes": {
            "character_state": [
                {
                    "entity_key": "沈越",
                    "field": "冲突处理方式",
                    "new": "第一次没有用私下垫钱的方式把疑点压过去",
                    "confidence": 0.7,
                }
            ]
        }
    }
    verifier = {
        "changes": {},
        "conflicts": [
            {
                "entity_key": "沈越",
                "field": "冲突处理方式",
                "observer_claim": "第一次没有用私下垫钱的方式把疑点压过去",
            }
        ],
    }
    merged, issues = merge_extractions([extraction], verifier)
    assert merged == []
    assert issues == []


def test_pov_check_allows_visible_hedged_inference() -> None:
    content = "方国良又说了一遍，语气轻了一些，像是觉得这事已经过去了。"
    assert find_pov_violations(content, "沈越", {"沈越", "方国良"}) == []


def test_pov_check_rejects_direct_access_to_another_characters_thoughts() -> None:
    content = "方国良觉得这事已经过去了，心里终于松了口气。"
    assert find_pov_violations(content, "沈越", {"沈越", "方国良"})


def test_wikilinks_are_normalized_and_deduplicated() -> None:
    assert extract_wikilinks("[[林川]] 与 [[青云城|城里]]，再次提到 [[林川]]") == ["林川", "青云城"]


def test_node_contract_rejects_incomplete_architect_output() -> None:
    with pytest.raises(NodeContractError, match="1 至 8 个连续情节段"):
        validate_node_output("novel-architect", {"pov_character": "林川", "beats": []})


def test_architect_contract_accepts_a_single_slow_burn_beat() -> None:
    output = normalize_node_output(
        "novel-architect",
        {
            "pov_character": "林川",
            "characters": ["林川"],
            "beats": [{"segment": "雨夜等人", "event": "林川守在药铺后门等一个迟迟没来的送信人"}],
        },
        {"context_pack": {"chapter_sequence": 1, "project": {"protagonist": "林川"}, "chapter_outline": {}}},
    )

    validate_node_output("novel-architect", output)
    assert len(output["beats"]) == 1


def test_architect_normalizes_confirmed_chapter_plan() -> None:
    payload = {
        "context_pack": {
            "chapter_sequence": 1,
            "project": {"protagonist": "陈恪"},
            "chapter_outline": {
                "characters": ["陈恪"],
                "beats": [
                    {"segment": "情节1", "event": "客栈醒来"},
                    {"segment": "情节2", "event": "出门探访"},
                    {"segment": "情节3", "event": "精准预言"},
                    {"segment": "情节4", "event": "察觉跟踪"},
                    {"segment": "情节5", "event": "危险逼近"},
                ],
            },
        }
    }

    result = normalize_node_output("novel-architect", {"beats": []}, payload)

    assert [item["segment"] for item in result["beats"]] == ["情节1", "情节2", "情节3", "情节4", "情节5"]
    assert result["beats"][1]["event"] == "出门探访"
    assert result["beats"][2]["event"] == "精准预言"
    validate_node_output("novel-architect", result)


def test_architect_converts_legacy_opening_scene_contract() -> None:
    payload = {
        "context_pack": {
            "chapter_sequence": 1,
            "project": {"protagonist": "苏清雪"},
            "chapter_outline": {
                "viewpoint": "苏清雪",
                "starting_state": "她刚在陌生房间醒来",
                "immediate_goal": "弄清身份和眼前危险",
                "resistance": "记忆缺失且有人即将进门",
                "next_promise": "门外的人掌握她的处境",
                "scenes": [
                    {"place": "闺房", "present_characters": "苏清雪", "perception": "她发现身体陌生", "action_and_response": "她检查房间与铜镜", "consequence": "确认自己已换了身份"},
                    {"place": "门边", "present_characters": "苏清雪、柳如烟", "perception": "脚步停在门外", "action_and_response": "她压下慌乱回应来人", "consequence": "得知今晚必须见客"},
                ],
            },
        }
    }

    result = normalize_node_output("novel-architect", {"beats": []}, payload)

    assert len(result["beats"]) == 2
    assert result["beats"][0]["location"] == "闺房"
    assert "确认自己已换了身份" in result["beats"][0]["event"]
    validate_node_output("novel-architect", result)


def test_architect_preserves_authorial_scene_design() -> None:
    scene = {
        "segment": "酒肆试探",
        "event": "陈恪用一句模糊预言试探邻桌官吏",
        "immediate_goal": "让消息传进目标圈子",
        "obstacle": "对方怀疑他是套话的骗子",
        "turn": "老者反问他的籍贯与师承",
        "outcome": "陈恪暴露口音，同时换来一次邀约",
    }
    payload = {
        "context_pack": {
            "chapter_sequence": 1,
            "project": {"protagonist": "陈恪"},
            "chapter_outline": {
                "reader_experience": "看见一次言语试探如何同时带来机会与危险",
                "style_direction": {"dialogue": "用称谓和回避体现身份差"},
                "beats": [scene, {**scene, "segment": "归途跟踪", "event": "陈恪发现有人跟踪"}],
            },
        }
    }

    result = normalize_node_output("novel-architect", {}, payload)

    assert result["reader_experience"].startswith("看见")
    assert result["style_direction"]["dialogue"].startswith("用称谓")
    assert result["beats"][0]["outcome"].endswith("邀约")


def test_genres_receive_different_executable_writing_contracts() -> None:
    history = get_genre_writing_contract("历史")
    romance = get_genre_writing_contract("言情")

    assert "礼法" in history["prose_texture"]
    assert "身体感受" in romance["narrative_distance"]
    assert history["scene_engine"] != romance["scene_engine"]


def test_world_simulator_fills_missing_identity() -> None:
    payload = {"context_pack": {"chapter_sequence": 3, "project": {"protagonist": "陈恪"}}}

    result = normalize_node_output(
        "world-simulator",
        {"character_decisions": [{"character": "陈恪", "decision": "追查线索"}]},
        payload,
    )

    assert result["simulation_id"] == "simulation-3"
    validate_node_output("world-simulator", result)


def test_world_simulator_rejects_empty_character_decisions() -> None:
    payload = {"context_pack": {"chapter_sequence": 3, "project": {"protagonist": "陈恪"}}}
    result = normalize_node_output("world-simulator", {}, payload)

    with pytest.raises(ValueError, match="不能为空"):
        validate_node_output("world-simulator", result)


def test_world_simulator_missing_character_check_accepts_null_decisions() -> None:
    from app.engine.runtime import _missing_simulated_characters

    missing = _missing_simulated_characters(
        {"character_decisions": None},
        {"context_pack": {"scene_entities": ["陈恪", "周宁"]}},
    )

    assert missing == ["陈恪", "周宁"]


@pytest.mark.asyncio
async def test_confirmed_plan_and_rule_checks_do_not_call_remote_model(monkeypatch) -> None:
    context = context_pack()
    context["chapter_outline"]["beats"] = [
        {"segment": f"情节{index}", "event": event}
        for index, event in enumerate(
            ["主角发现关键线索", "主角沿街追查真相", "追查途中遭遇阻拦", "证据出现意外反转", "危险逼近留下悬念"],
            start=1,
        )
    ]

    async def fail_remote(*_args, **_kwargs):
        raise AssertionError("不应调用远程模型")

    monkeypatch.setattr("app.engine.runtime.llm_client.complete", fail_remote)
    beat_sheet = await run_agent_node("novel-architect", {"context_pack": context}, "test")
    guardian = await run_agent_node(
        "novel-guardian",
        {"context_pack": context, "world_simulation": {}, "beat_sheet": beat_sheet},
        "test",
    )

    assert guardian["passed"] is True
    assert [beat["segment"] for beat in beat_sheet["beats"]] == ["情节1", "情节2", "情节3", "情节4", "情节5"]


@pytest.mark.asyncio
async def test_supporting_analysis_uses_remote_model_in_production(monkeypatch) -> None:
    context = context_pack()
    calls: list[str] = []
    node_names = ["observer-social", "observer-environment", "observer-narrative", "novel-verifier", "novel-editor"]
    current_payload: dict = {}

    async def remote(system_prompt, user_prompt, response_format="text", **_kwargs):
        import json as _json
        name = next((n for n in node_names if n in str(system_prompt)), None)
        calls.append(name or "unknown")
        if name is None:
            return "{}"
        return _json.dumps(mock_node(name, current_payload), ensure_ascii=False)

    monkeypatch.setattr(
        "app.engine.runtime.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "llm_backend": "openai_compatible",
                "generation_max_tokens_prose": 8192,
                "generation_max_tokens_structured": 4096,
            },
        )(),
    )
    monkeypatch.setattr("app.engine.runtime.llm_client.complete", remote)
    payload = {
        "context_pack": context,
        "beat_sheet": mock_node("novel-architect", {"context_pack": context}),
        "content": "林川沿着线索继续追查。",
        "summary": "林川继续追查。",
    }
    current_payload = payload

    observers = [
        await run_agent_node(name, payload, "test")
        for name in ["observer-social", "observer-environment", "observer-narrative"]
    ]
    verifier = await run_agent_node(
        "novel-verifier",
        {**payload, "observer_extractions": observers},
        "test",
    )

    assert all("changes" in result for result in observers)
    assert verifier["conflicts"] == []

    current_payload = {
        "context_pack": context,
        "beat_sheet": payload["beat_sheet"],
        "draft": {"content": payload["content"], "summary": payload["summary"]},
    }
    edited = await run_agent_node("novel-editor", current_payload, "test")
    assert edited["content"] == payload["content"]
    assert calls == [
        "observer-social",
        "observer-environment",
        "observer-narrative",
        "novel-verifier",
        "novel-editor",
    ]
