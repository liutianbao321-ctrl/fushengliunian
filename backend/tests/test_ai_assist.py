import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.api.ai_assist import _run_story_seed_task, _story_seed_results, _story_seed_tasks
from app.services.ai_assist import (
    _blueprint_rejection_reasons,
    _blueprint_review_passes,
    _cast_meets_genre_requirements,
    _chapter_plan_rejection_reasons,
    _chapter_plan_review_passes,
    _conflicts_with_reader_boundary,
    _direction_rejection_reasons,
    _foundation_rejection_reasons,
    _normalize_book_blueprint,
    _normalize_chapter_plan,
    _normalize_foundation_stage_ranges,
    _normalize_story_seeds,
    _seed_violates_boundaries,
    _unwrap_json_object,
    _volume_review_passes,
    generate_chapter_plan,
    generate_chapter_plan_window,
    generate_character_cast,
    generate_lazy_project,
    generate_light_chapter_edits,
    generate_opening_pilot,
    generate_reader_feedback,
    generate_story_foundation,
    generate_story_seeds,
    generate_world_engine,
    viability_blocking_reasons,
)
from app.services.llm_client import LLMClient, LLMResponseError, llm_client


class EmptyDatabase:
    async def scalar(self, _query):
        return None


class EmptyScalars:
    def all(self):
        return []


class StoryDatabase:
    async def get(self, _model, _track_id):
        return type(
            "Track",
            (),
            {
                "track_name": "医疗成长",
                "channel": "女频",
                "genre": "现代言情",
                "golden_formula": "病例推动成长",
                "benchmark_works": [],
            },
        )()

    async def scalars(self, _query):
        return EmptyScalars()


def creation_foundation_fixture() -> dict:
    functions = [
        "orient", "deepen", "attempt", "deepen", "attempt",
        "complicate", "attempt", "deepen", "complicate", "partial_payoff",
    ]
    directions = [
        {
            "sequence": sequence,
            "title": f"门前第{sequence}次来客",
            "function": functions[sequence - 1],
            "focus_character": "林砚",
            "location": "修表铺" if sequence <= 3 else "旧街商会办事处",
            "reader_orientation": "林砚守着父亲留下的修表铺，今天必须处理一笔具体旧债。",
            "immediate_goal": "弄清今天上门的债单为什么提前到期。",
            "obstacle": "债主代理只承认商会登记，不接受林家的旧收据。",
            "main_action": "林砚从一只待修旧表的转手记录核对债权日期。",
            "information_gain": f"读者只新增第{sequence}条与眼前债单有关的信息。",
            "relationship_movement": "林砚与债主代理从单纯对立变成互相试探。",
            "immediate_consequence": f"林砚获得一点线索，但今天的收铺压力仍未解除{sequence}。",
            "ending_beat": "下一步必须找到旧收据上那位仍住在旧街的见证人。",
        }
        for sequence in range(1, 11)
    ]
    return {
        "core": {
            "title_candidates": ["旧铺新债"],
            "premise": "一个守着旧铺的年轻人以揭开家族旧账为代价，对抗垄断契约的商会。",
            "reader_promise": "每一次解决债务都会改变一段关系并打开更大的交易规则。",
            "central_question": "他能否在不变成商会那类人的前提下赢得选择权？",
            "emotional_core": "人在亏欠与担当之间重新理解家。",
            "ending_direction": "主角取得改写规则的资格，但必须接受无法补偿所有人。",
        },
        "engine": {
            "engine_type": "契约与信誉交换",
            "primary_genre": "都市",
            "long_term_loop": "解决一笔债务会暴露另一笔被转嫁的代价。",
            "progression_dimensions": ["信誉", "人脉", "规则解释权"],
            "escalation_rule": "从街区旧债扩展到城市行业契约。",
        },
        "scale_plan": {
            "target_words": 1_000_000,
            "estimated_chapters": 303,
            "planned_volumes": 7,
            "average_chapters_per_volume": 43,
            "opening_window_chapters": 10,
            "progression_ladders": ["修表技能", "街坊信誉", "商会议价权"],
            "pacing_boundaries": ["前10章不离开旧街", "第一卷不揭开父亲真相", "每卷只跨一个竞争层级", "重大关系变化必须有铺垫"],
        },
        "world": {
            "core_rule": "公开登记的承诺可被商会折算为债权。",
            "social_order": "商会按信誉等级分配交易资格。",
            "scarce_resource": "不受商会担保的独立信用。",
            "cost": "每次调用他人承诺都要公开自己的等价秘密。",
            "opening_locality": "即将被收走的街角修表铺。",
            "visible_rules": ["街坊以信誉票据赊账", "失信者不能租用商会铺面"],
            "reserve": ["跨城担保规则"],
        },
        "protagonist": {
            "name": "林砚",
            "gender": "男",
            "starting_state": "独自守着父亲留下的亏损修表铺。",
            "desire": "保住旧铺并证明父亲没有骗走街坊的钱。",
            "fear": "发现父亲确实伤害过信任他的人。",
            "belief": "账目清楚就能分清谁对谁错。",
            "method": "修复旧物时追查每一次转手记录。",
            "bottom_line": "不拿无关者的秘密抵债。",
            "contradiction": "要求别人坦白，却不敢看父亲留下的最后一本账。",
        },
        "creative_brief": [
            {"title": "旧街如何运转", "content": "旧街的铺户靠商会信誉票据赊账，修表铺既是林砚的生计，也是父亲旧债唯一可追查的实物入口。"},
            {"title": "林砚与旧账", "content": "林砚今天先要阻止代理贴封条；他擅长从旧物转手痕迹查账，却害怕最后证明父亲确实辜负过街坊。"},
            {"title": "故事怎样持续生长", "content": "每解决一笔旧债就改变一段关系，并露出更高一层的担保规则；信誉、人脉与规则解释权轮流推进。"},
            {"title": "第一卷的兑现", "content": "第一卷只查明一笔债权被违规转手并暂时保住铺面，不提前洗清父亲，也不揭开全城债务链。"},
        ],
        "characters": [
            {"name": "周禾", "role": "债主代理", "desire": "拿到独立担保资格", "method": "制造可交换的人情", "leverage": "掌握旧账副本", "relationship": "既催债也暗中留路", "offstage_action": "向商会竞买旧铺债权"},
            {"name": "陈伯", "role": "街坊债权人", "desire": "追回养老钱", "method": "联合街坊施压", "leverage": "知道主角父亲最后见过谁", "relationship": "疼惜主角但不愿再相信林家", "offstage_action": "逐户收集当年收据"},
        ],
        "stages": [
            {"name": "守住旧街", "chapter_range": [1, 76], "starting_state": "主角没有交易资格", "goal": "取得街区信用", "pressure": "商会收债", "irreversible_choice": "承担街坊共同债务", "changed_state": "成为街区债务代理", "promise_payoff": "父亲旧案出现第一层答案"},
            {"name": "进入商会", "chapter_range": [77, 227], "starting_state": "主角承担街区债务", "goal": "取得规则解释权", "pressure": "商会分化债权人", "irreversible_choice": "放弃个人清白保护证人", "changed_state": "得到行业席位也成为被告", "promise_payoff": "关系与能力同步升级"},
            {"name": "改写契约", "chapter_range": [228, 303], "starting_state": "主角有席位但失去信誉", "goal": "废除债务转嫁", "pressure": "受益者拒绝改变", "irreversible_choice": "承认林家是规则共谋者", "changed_state": "新规则建立但旧铺不再属于他", "promise_payoff": "兑现选择权与家的主题"},
        ],
        "first_volume": {
            "sequence": 1,
            "title": "旧街债单",
            "chapter_range": [1, 44],
            "reader_promise": "看林砚用修表留下的微小痕迹，一点点赢回街坊的信任。",
            "starting_state": "修表铺即将被收走，街坊也不再相信林家。",
            "volume_goal": "在拍卖日前证明至少一笔旧债被违规转手。",
            "central_pressure": "商会规则合法，但每次申诉都会消耗林砚的街坊信誉。",
            "midpoint_change": "林砚发现债权转手合法，真正的问题在见证程序。",
            "climax_choice": "公开父亲参与见证的一页旧账，换取重审。",
            "ending_state": "铺面暂时保住，林砚成为旧街共同债务的代理人。",
            "progression_gain": "取得查阅街区债权登记的有限资格。",
            "relationship_change": "周禾从催债者变成有条件提供线索的竞争者。",
            "protected_reveals": ["父亲当年为何签字", "商会最高层的真实目的", "全城债务转嫁链"],
        },
        "opening_window": {
            "title": "封条上门",
            "chapter_range": [1, 10],
            "purpose": "让读者认住林砚、修表铺和眼前债单，并看懂他解决问题的方法。",
            "reader_anchor": "林砚在熟悉的修表铺里处理今天就要贴下的封条。",
            "local_goal": "查清债单提前到期的直接手续，并争取几天缓期。",
            "scope_boundary": "不证明父亲清白，不解决整条旧债，不离开旧街。",
            "ending_change": "林砚争取到七天缓期，同时确认旧收据上的见证人仍在旧街。",
            "introduced_characters": ["林砚", "周禾", "陈伯"],
            "introduced_rules": ["商会登记决定债权效力", "公开承诺可以折算成信誉"],
            "chapter_directions": directions,
        },
    }


@pytest.mark.asyncio
async def test_reader_audit_discards_issues_without_exact_quotes(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "verdict": "needs_revision",
        "summary": "检查完成",
        "checks": [
            {"category": "因果连续", "status": "fail", "finding": "动作无因", "quote": "他忽然拔刀", "reason": "缺少触发", "suggestion": "补触发", "blocking": True},
            {"category": "人物主动性", "status": "warning", "finding": "虚构问题", "quote": "正文里不存在", "reason": "无", "suggestion": "无", "blocking": False},
        ],
    }
    monkeypatch.setattr(llm_client, "complete", AsyncMock(return_value=json.dumps(response, ensure_ascii=False)))

    result = await generate_reader_feedback("门外一响，他忽然拔刀。", "", chapter_plan={})

    assert result["verdict"] == "needs_revision"
    assert len(result["checks"]) == 1
    assert result["checks"][0]["quote"] == "他忽然拔刀"


@pytest.mark.asyncio
async def test_reader_audit_recovers_from_non_json_model_output(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "verdict": "pass",
        "summary": "未发现阻断性问题",
        "checks": [{"category": "因果连续", "status": "pass", "finding": "连续", "blocking": False}],
    }
    complete = AsyncMock(side_effect=["I cannot comply with JSON mode", f"```json\n{json.dumps(response, ensure_ascii=False)}\n```"])
    monkeypatch.setattr(llm_client, "complete", complete)

    result = await generate_reader_feedback("门外一响，他忽然拔刀。", "", chapter_plan={})

    assert result["verdict"] == "pass"
    assert complete.await_count == 2
    assert complete.await_args_list[1].kwargs["temperature"] == 0.1


@pytest.mark.asyncio
async def test_reader_audit_does_not_treat_observable_reactions_as_pov_violations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quote = "她想喊掌柜的，嘴巴张开了，嗓子眼却像被什么堵死，一点声音都挤不出来。"
    response = {
        "verdict": "needs_revision",
        "summary": "存在视角硬伤",
        "checks": [{
            "category": "视角与知识边界",
            "status": "fail",
            "finding": "进入了非视角人物内心",
            "quote": quote,
            "reason": "这是他人反应",
            "suggestion": "删除",
            "blocking": True,
        }],
    }
    monkeypatch.setattr(llm_client, "complete", AsyncMock(return_value=json.dumps(response, ensure_ascii=False)))

    result = await generate_reader_feedback(quote, "", chapter_plan={"pov_character": "陆景"})

    assert result["verdict"] == "pass"
    assert result["checks"] == []
    assert result["summary"] == "未发现阻断性问题。"


@pytest.mark.asyncio
async def test_reader_audit_downgrades_explicit_interior_pov_to_a_suggestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quote = "白晓晓心里确信，陆景永远不会发现那封信。"
    response = {
        "verdict": "needs_revision",
        "summary": "存在视角硬伤",
        "checks": [{
            "category": "POV稳定性",
            "status": "fail",
            "finding": "短暂进入非视角人物内心",
            "quote": quote,
            "reason": "直接断言未表达的想法",
            "suggestion": "改为陆景可观察到的表现",
            "blocking": True,
        }],
    }
    monkeypatch.setattr(llm_client, "complete", AsyncMock(return_value=json.dumps(response, ensure_ascii=False)))

    result = await generate_reader_feedback(quote, "", chapter_plan={"pov_character": "陆景"})

    assert result["verdict"] == "pass"
    assert result["checks"][0]["status"] == "warning"
    assert result["checks"][0]["blocking"] is False
    assert result["summary"] == "未发现阻断性问题；有 1 项可选建议。"


@pytest.mark.asyncio
async def test_light_chapter_edits_only_accept_exact_local_replacements(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "edits": [
            {"find": "他忽然拔刀。", "replace": "他听见门外一响，立即拔刀。", "reason": "补足动作触发"},
            {"find": "正文里不存在", "replace": "不能应用", "reason": "无效引文"},
        ]
    }
    monkeypatch.setattr(llm_client, "complete", AsyncMock(return_value=json.dumps(response, ensure_ascii=False)))

    edits = await generate_light_chapter_edits("门外一响。他忽然拔刀。", "补清动作原因")

    assert edits == [response["edits"][0]]


@pytest.mark.asyncio
async def test_creation_foundation_retries_an_overfast_chapter_window(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid = creation_foundation_fixture()
    invalid["opening_window"]["chapter_directions"][0]["function"] = "partial_payoff"
    valid = creation_foundation_fixture()
    complete = AsyncMock(side_effect=[
        json.dumps(invalid, ensure_ascii=False),
        json.dumps({"opening_window": {**invalid["opening_window"], "chapter_directions": invalid["opening_window"]["chapter_directions"][:5]}}, ensure_ascii=False),
        json.dumps({"chapter_directions": invalid["opening_window"]["chapter_directions"][5:]}, ensure_ascii=False),
        json.dumps(valid, ensure_ascii=False),
        json.dumps({"opening_window": {**valid["opening_window"], "chapter_directions": valid["opening_window"]["chapter_directions"][:5]}}, ensure_ascii=False),
        json.dumps({"chapter_directions": valid["opening_window"]["chapter_directions"][5:]}, ensure_ascii=False),
    ])
    monkeypatch.setattr(llm_client, "complete", complete)

    result = await generate_story_foundation(
        {"idea": "我想写一个年轻人守住父亲旧铺，却必须面对家族旧债的长篇故事。", "genre": "都市"},
        [{"title": "因果场景", "principle": "选择必须改变局势"}],
    )

    assert result["opening_window"]["chapter_directions"][0]["function"] == "orient"
    assert complete.await_count == 6
    assert "第一章必须先完成读者定位" in complete.await_args_list[3].args[1]


@pytest.mark.asyncio
async def test_creation_foundation_repairs_short_pacing_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    value = creation_foundation_fixture()
    value["scale_plan"]["pacing_boundaries"] = ["前10章立足", "第一卷不揭终局", "关系变化要铺垫"]
    complete = AsyncMock(return_value=json.dumps(value, ensure_ascii=False))
    monkeypatch.setattr(llm_client, "complete", complete)

    result = await generate_story_foundation(
        {"idea": "我想写一个年轻人守住父亲旧铺，却必须面对家族旧债的长篇故事。", "genre": "都市"},
        [],
        scope="core",
    )

    assert len(result["scale_plan"]["pacing_boundaries"]) >= 4
    assert result["opening_window"]["chapter_directions"] == []


@pytest.mark.asyncio
async def test_creation_foundation_does_not_return_template_fallback_when_model_never_returns_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.ai_assist._planning_models", lambda: ["broken-model"])
    monkeypatch.setattr(llm_client, "complete", AsyncMock(return_value="我无法输出这个 JSON。"))

    with pytest.raises(RuntimeError, match="故事蓝图生成失败"):
        await generate_story_foundation(
            {"idea": "我想写一个主角在旧城里一步步查清家族旧债的长篇故事。", "genre": "都市"},
            [],
            scope="core",
        )


def test_creation_foundation_rejects_a_short_story_scale_for_a_million_words() -> None:
    value = creation_foundation_fixture()
    value["scale_plan"]["estimated_chapters"] = 80

    reasons = _foundation_rejection_reasons(value, 1_000_000)

    assert any("estimated_chapters必须为303" in reason for reason in reasons)


def test_creation_foundation_does_not_reject_subject_matter_by_keyword() -> None:
    value = creation_foundation_fixture()
    value["world"]["core_rule"] = "系统发布反派任务，完成任务就获得力量。"

    from app.services.ai_assist import _foundation_quality_rejection_reasons

    reasons = _foundation_quality_rejection_reasons(
        value,
        {"idea": "我想写一个普通人被迫进入江湖后一步步求生的长篇故事。"},
    )

    assert reasons == []


def test_creation_foundation_allows_concrete_reader_friendly_blueprint() -> None:
    from app.services.ai_assist import _foundation_quality_rejection_reasons

    reasons = _foundation_quality_rejection_reasons(
        creation_foundation_fixture(),
        {"idea": "我想写一个年轻人守住父亲旧铺，却必须面对家族旧债的长篇故事。"},
    )

    assert reasons == []


def test_foundation_stage_ranges_scale_proportionally_to_three_million_words() -> None:
    value = creation_foundation_fixture()

    _normalize_foundation_stage_ranges(value, 909)

    assert [stage["chapter_range"] for stage in value["stages"]] == [
        [1, 228],
        [229, 681],
        [682, 909],
    ]


def test_normalized_foundation_stages_pass_exact_coverage_checks() -> None:
    value = creation_foundation_fixture()
    value["scale_plan"].update(
        {
            "target_words": 3_000_000,
            "estimated_chapters": 909,
            "planned_volumes": 12,
            "average_chapters_per_volume": 76,
        }
    )
    value["first_volume"]["chapter_range"] = [1, 76]
    _normalize_foundation_stage_ranges(value, 909)

    reasons = _foundation_rejection_reasons(value, 3_000_000)

    assert "长线阶段必须从第1章连续覆盖到全书预计末章" not in reasons
    assert "长线阶段的章节范围必须连续且不重叠" not in reasons


@pytest.mark.asyncio
async def test_opening_pilot_builds_contract_before_writing_prose(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = {
        "title": "封条上门",
        "summary": "林砚公开一页旧账保住铺面，却让父亲的嫌疑第一次坐实。",
        "scene_contract": {
            "viewpoint": "林砚",
            "starting_state": "林砚还能拖到月底再交铺。",
            "immediate_goal": "阻止代理今天贴上封条。",
            "resistance": "代理持有一份签名无误的提前收铺条款。",
            "action": "林砚从待修旧表中找出债权转手记录。",
            "decision": "暂时不争辩父亲是否清白，先核对债权日期。",
            "immediate_consequence": "周禾同意在见证人到场前暂缓贴封条。",
            "changed_state": "封条暂缓，但林家伪造账目的嫌疑公开。",
            "next_promise": "账页上的见证人正是最维护林父的陈伯。",
            "scenes": [
                {"place": "修表铺", "present_characters": "林砚、周禾", "perception": "门框被封条量过", "intention": "拖住贴封条", "action_and_response": "林砚查表壳，周禾叫来见证人", "consequence": "拖延办法失效"},
                {"place": "铺门口", "present_characters": "林砚、周禾、陈伯", "perception": "街坊围拢", "intention": "证明债权转手违规", "action_and_response": "林砚公开旧账，陈伯认出签名", "consequence": "铺面保住但父亲嫌疑坐实"},
            ],
        },
    }
    prose = "门框上的漆昨夜才补过。" + "林砚没有去看周禾手里的封条，只把那只停了二十年的旧表翻过来。" * 120
    complete = AsyncMock(side_effect=[json.dumps(contract, ensure_ascii=False), prose])
    monkeypatch.setattr(llm_client, "complete", complete)

    result = await generate_opening_pilot(creation_foundation_fixture(), [], author_note="不要解释规则")

    assert result["title"] == "封条上门"
    assert result["content"].startswith("门框上的漆")
    assert complete.await_count == 2
    assert "已确认场景契约" in complete.await_args_list[1].args[1]
    assert complete.await_args_list[1].kwargs["stream"] is True


@pytest.mark.asyncio
async def test_opening_pilot_accepts_complete_chapter_above_old_upper_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = {
        "title": "封条上门",
        "summary": "林砚用旧表记录拖住封条。",
        "scene_contract": {
            "viewpoint": "林砚",
            "starting_state": "林砚正在守铺。",
            "immediate_goal": "阻止代理今天贴封条。",
            "resistance": "债权手续看似齐全。",
            "action": "林砚核对旧表转手记录。",
            "decision": "先查债权日期。",
            "immediate_consequence": "封条暂缓。",
            "changed_state": "林砚争取到几天时间。",
            "next_promise": "见证人仍在旧街。",
            "scenes": [
                {
                    "place": "修表铺",
                    "present_characters": "林砚、周禾",
                    "perception": "封条压在柜台边",
                    "intention": "拖住贴封条",
                    "action_and_response": "林砚查旧表，周禾催促",
                    "consequence": "周禾同意等见证人",
                }
            ],
        },
    }
    prose = "甲" * 5940
    complete = AsyncMock(side_effect=[json.dumps(contract, ensure_ascii=False), prose])
    monkeypatch.setattr(llm_client, "complete", complete)

    result = await generate_opening_pilot(creation_foundation_fixture(), [])

    assert len(result["content"]) == 5940
    assert complete.await_count == 2


def test_json_object_parser_accepts_a_fenced_model_response() -> None:
    assert _unwrap_json_object("这里是结果：\n```json\n{\"title\": \"第一章\"}\n```", "data") == {"title": "第一章"}


@pytest.mark.asyncio
async def test_opening_pilot_uses_a_causal_fallback_contract_when_planners_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.ai_assist._planning_models", lambda: ["planner-a", "planner-b"])
    prose = "门外的封条贴歪了一寸。" + "林砚低头拆开旧表，听见街坊在门外交换眼色。" * 150
    complete = AsyncMock(side_effect=["", "not json", prose])
    monkeypatch.setattr(llm_client, "complete", complete)

    result = await generate_opening_pilot(creation_foundation_fixture(), [])

    assert result["scene_contract"]["immediate_goal"].startswith("弄清今天上门")
    assert result["scene_contract"]["changed_state"].startswith("林砚获得一点线索")
    assert result["content"].startswith("门外的封条")
    assert complete.await_args_list[2].kwargs["stream"] is True


@pytest.mark.asyncio
async def test_plan_window_requires_consecutive_writeable_chapters(monkeypatch: pytest.MonkeyPatch) -> None:
    chapters = []
    for sequence in (4, 5):
        chapters.append({
            "chapter_sequence": sequence,
            "title": f"第{sequence}章章名",
            "goal": "主角必须作出会改变处境的决定",
            "conflict": "对手阻止主角完成眼前目标",
            "characters": ["主角"],
            "beats": [
                {"segment": "开场", "event": "主角来到议事厅提出要求，却被对手当众拒绝", "obstacle": "遭到拒绝", "outcome": "主角改变策略"},
                {"segment": "选择", "event": "主角拿出代价换取支持，使双方关系发生不可逆变化", "obstacle": "必须付出代价", "outcome": "下一章必须处理后果"},
            ],
            "hook": "代价立即引出新的局面",
        })
    monkeypatch.setattr(llm_client, "complete", AsyncMock(return_value=json.dumps({"chapters": chapters}, ensure_ascii=False)))

    result = await generate_chapter_plan_window(
        book_title="测试书",
        premise="主角争取生存空间",
        start_sequence=4,
        count=2,
        previous_summary="",
        story_context="",
        volume_context="",
    )

    assert [item["chapter_sequence"] for item in result] == [4, 5]
    assert result[0]["plan"]["title_candidates"] == ["第4章章名"]


@pytest.mark.asyncio
async def test_single_chapter_plan_accepts_fenced_json(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = {
        "title_candidates": ["门外来客", "旧账重提"],
        "reader_experience": "看懂主角眼前的困境，并在一次试探中加深担心。",
        "goal": "林砚要确认来客手里的债单从何而来。",
        "conflict": "来客只肯展示盖章页，不肯交出完整债单。",
        "characters": ["林砚", "周禾"],
        "opening": {"situation": "修表铺刚开门", "pressure": "来客准备贴封条", "first_action": "林砚先检查盖章日期"},
        "beats": [
            {"segment": "来客", "location": "修表铺", "characters": ["林砚", "周禾"], "event": "周禾进门展示债单盖章页，林砚从纸张折痕判断它刚从完整文件中拆下。", "obstacle": "周禾拒绝交出其余页面", "outcome": "林砚改为核对盖章日期"},
            {"segment": "核对", "location": "修表铺", "characters": ["林砚", "周禾"], "event": "林砚拿旧收据比对日期，迫使周禾承认债单昨夜才被转交给她。", "obstacle": "旧收据没有商会登记号", "outcome": "林砚得到追查上一持有人的方向"},
        ],
        "hook": "债单的上一持有人正是熟悉旧铺的人。",
        "ending_image": "封条仍压在柜台边。",
        "must_avoid": ["本章不得查清全部旧债"],
    }
    complete = AsyncMock(return_value=f"```json\n{json.dumps(plan, ensure_ascii=False)}\n```")
    monkeypatch.setattr(llm_client, "complete", complete)

    result = await generate_chapter_plan(
        book_title="旧铺新债",
        premise="林砚守住旧铺并追查旧债。",
        chapter_sequence=2,
        previous_summary="债主第一次上门。",
    )

    assert result["title_candidates"][0] == "门外来客"
    assert len(result["beats"]) == 2
    assert complete.await_count == 1
    assert complete.await_args.kwargs["timeout_seconds"] == 60
    assert complete.await_args.kwargs["request_attempts"] == 1


@pytest.mark.asyncio
async def test_story_seed_request_is_coalesced_and_cached() -> None:
    _story_seed_tasks.clear()
    _story_seed_results.clear()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def generate() -> list[dict[str, str]]:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return [{"title": "同一个结果"}]

    first = asyncio.create_task(_run_story_seed_task(("user", "request"), generate))
    await started.wait()
    second = asyncio.create_task(_run_story_seed_task(("user", "request"), generate))
    release.set()

    assert await first == await second
    assert await _run_story_seed_task(("user", "request"), generate) == [{"title": "同一个结果"}]
    assert calls == 1


@pytest.mark.asyncio
async def test_lazy_generation_does_not_disguise_model_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_client, "complete", AsyncMock(side_effect=RuntimeError("model unavailable")))

    with pytest.raises(RuntimeError, match="AI 暂时没有生成成功"):
        await generate_lazy_project(EmptyDatabase())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_incomplete_non_mock_configuration_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = LLMClient()
    monkeypatch.setattr(client.settings, "llm_backend", "openai_compatible")
    monkeypatch.setattr(client.settings, "llm_base_url", None)
    monkeypatch.setattr(client.settings, "llm_api_key", None)

    with pytest.raises(RuntimeError, match="配置不完整"):
        await client.complete("secret system prompt", "secret user prompt")


@pytest.mark.asyncio
async def test_llm_client_can_route_short_tasks_to_a_faster_model(monkeypatch: pytest.MonkeyPatch) -> None:
    client = LLMClient()
    monkeypatch.setattr(client.settings, "llm_backend", "openai_compatible")
    monkeypatch.setattr(client.settings, "llm_base_url", "https://llm.example/v1")
    monkeypatch.setattr(client.settings, "llm_api_key", "test-key")
    request = AsyncMock(return_value="{}")
    monkeypatch.setattr(client, "_request", request)

    await client.complete("system", "user", "json", model="fast-planner", max_tokens=3000)

    payload = request.await_args.args[0]
    assert payload["model"] == "fast-planner"
    assert payload["max_tokens"] == 3000
    assert payload["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_explicit_model_does_not_expand_the_global_fallback_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    client = LLMClient()
    monkeypatch.setattr(client.settings, "llm_backend", "openai_compatible")
    monkeypatch.setattr(client.settings, "llm_base_url", "https://llm.example/v1")
    monkeypatch.setattr(client.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(client.settings, "llm_deepseek_model", "deepseek-v4-pro")
    monkeypatch.setattr(client.settings, "llm_aliyun_model", "qwen-plus")
    request = AsyncMock(side_effect=LLMResponseError("HTTP 401"))
    monkeypatch.setattr(client, "_request", request)

    with pytest.raises(RuntimeError, match="selected-planner"):
        await client.complete("system", "user", model="selected-planner")

    assert request.await_count == 1
    assert request.await_args.args[0]["model"] == "selected-planner"


@pytest.mark.asyncio
async def test_llm_client_forwards_per_request_latency_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    client = LLMClient()
    monkeypatch.setattr(client.settings, "llm_backend", "openai_compatible")
    monkeypatch.setattr(client.settings, "llm_base_url", "https://llm.example/v1")
    monkeypatch.setattr(client.settings, "llm_api_key", "test-key")
    request = AsyncMock(return_value="{}")
    monkeypatch.setattr(client, "_request", request)

    await client.complete(
        "system",
        "user",
        model="fast-planner",
        timeout_seconds=60,
        request_attempts=1,
    )

    payload = request.await_args.args[0]
    assert payload["__timeout_seconds"] == 60
    assert payload["__request_attempts"] == 1


@pytest.mark.asyncio
async def test_llm_client_falls_back_after_transient_primary_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = LLMClient()
    monkeypatch.setattr(client.settings, "llm_backend", "openai_compatible")
    monkeypatch.setattr(client.settings, "llm_base_url", "https://llm.example/v1")
    monkeypatch.setattr(client.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(client.settings, "llm_model", "primary-model")
    monkeypatch.setattr(client.settings, "llm_fallback_model", "fallback-model")
    request = httpx.Request("POST", "https://llm.example/v1/chat/completions")
    response = httpx.Response(503, request=request)
    transient = httpx.HTTPStatusError("unavailable", request=request, response=response)
    stream_request = AsyncMock(side_effect=[transient, "备用模型正文"])
    monkeypatch.setattr(client, "_stream_request", stream_request)

    result = await client.complete("system", "prompt", stream=True)

    assert result == "备用模型正文"
    assert [call.args[0]["model"] for call in stream_request.await_args_list] == ["primary-model", "fallback-model"]


@pytest.mark.asyncio
async def test_llm_client_falls_back_after_an_empty_success_response(monkeypatch: pytest.MonkeyPatch) -> None:
    client = LLMClient()
    monkeypatch.setattr(client.settings, "llm_backend", "openai_compatible")
    monkeypatch.setattr(client.settings, "llm_base_url", "https://llm.example/v1")
    monkeypatch.setattr(client.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(client.settings, "llm_model", "empty-model")
    monkeypatch.setattr(client.settings, "llm_fallback_model", "working-model")
    request = AsyncMock(side_effect=["", "{\"ok\": true}"])
    monkeypatch.setattr(client, "_request", request)

    result = await client.complete("system", "prompt", "json")

    assert result == "{\"ok\": true}"
    assert [call.args[0]["model"] for call in request.await_args_list] == ["empty-model", "working-model"]


@pytest.mark.asyncio
async def test_llm_client_falls_back_when_a_model_is_not_available(monkeypatch: pytest.MonkeyPatch) -> None:
    client = LLMClient()
    monkeypatch.setattr(client.settings, "llm_backend", "openai_compatible")
    monkeypatch.setattr(client.settings, "llm_base_url", "https://llm.example/v1")
    monkeypatch.setattr(client.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(client.settings, "llm_model", "missing-model")
    monkeypatch.setattr(client.settings, "llm_fallback_model", "working-model")
    request = AsyncMock(side_effect=[LLMResponseError("HTTP 404"), "可用结果"])
    monkeypatch.setattr(client, "_request", request)

    assert await client.complete("system", "prompt") == "可用结果"


@pytest.mark.asyncio
async def test_story_generation_retries_an_incomplete_model_response(monkeypatch: pytest.MonkeyPatch) -> None:
    seed = {
        "title": "白衣新程",
        "one_sentence": "实习医生在一次次急诊中成长。",
        "protagonist_name": "苏宁",
        "protagonist_gender": "女",
        "protagonist_personality": "冷静坚韧",
        "hook": "第一天值班便遇到危重病人",
        "reader_promise": "每个病例带来一次成长",
        "opening_event": "主角独自面对突发急救",
        "story_engine": "病例、选择和职业晋升持续推动剧情",
        "long_term_growth": "从实习生成长为独立医生",
        "difference": "医疗判断必须承担真实代价",
        "risk_note": "避免病例重复",
        "genre": "现代言情",
    }
    monkeypatch.setattr(
        llm_client,
        "complete",
        AsyncMock(side_effect=[RuntimeError("truncated"), json.dumps([seed, seed, seed], ensure_ascii=False)]),
    )

    result = await generate_story_seeds([], count=3)

    assert len(result) == 3
    assert llm_client.complete.await_count == 2


@pytest.mark.asyncio
async def test_story_generation_accepts_wrapped_response_and_favorite_system_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = {
        "title": "兑换长街",
        "one_sentence": "主角借助系统在江湖中成长。",
        "protagonist_name": "沈照",
        "hook": "第一次任务改变命运",
        "opening_event": "系统发布首个任务",
        "story_engine": "完成选择并获取成长资源",
        "long_term_growth": "从无名之辈成长为一代宗师",
    }
    complete = AsyncMock(return_value=json.dumps({"response": [seed, seed, seed]}, ensure_ascii=False))
    monkeypatch.setattr(llm_client, "complete", complete)

    result = await generate_story_seeds(
        ["升级成长"], favorite_works="我喜欢系统流作品", count=3
    )

    assert len(result) == 3
    assert result[0]["protagonist_gender"] == ""
    assert complete.await_count == 1


def test_story_seed_normalizes_common_aliases() -> None:
    result = _normalize_story_seeds(
        [{
            "title": "长夜",
            "premise": "一名记者追查旧案。",
            "protagonist": "林深",
            "selling_point": "每条线索都会改变熟人关系",
            "inciting_incident": "收到失踪者寄来的信",
            "engine": "调查与关系代价交替推进",
            "growth_arc": "从旁观者变成承担真相的人",
        }]
    )

    assert result[0]["one_sentence"] == "一名记者追查旧案。"
    assert result[0]["protagonist_name"] == "林深"
    assert result[0]["risk_note"] == ""
    assert result[0]["story_question"] == ""


@pytest.mark.asyncio
async def test_world_generation_retries_until_pressure_tests_are_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incomplete = {"engine_name": "灵脉竞争"}
    complete = {
        "engine_name": "灵脉债务",
        "reader_promise": "每次变强都改变主角与宗门的债务关系",
        "core_rule": "借用灵脉力量会把等量损耗转移给契约地",
        "power_source": "与地域灵脉签订限时契约",
        "scarcity": "尚未枯竭且无人占有的灵脉",
        "social_order": "宗门凭契约范围分配身份和修炼资格",
        "progression_axes": ["契约精度", "资源", "身份", "地图"],
        "conflict_generators": ["灵脉枯竭", "契约争夺", "债务追索"],
        "limitations": ["离开契约地能力衰减", "透支会伤害契约地居民"],
        "core_cost": "变强会累积必须偿还的地域债务",
        "daily_life_effects": ["城镇按灵脉余量限水", "婚契包含灵脉债务继承"],
        "escalation_model": "从村镇契约进入宗门、王朝与跨域灵脉竞争",
        "opening_pressure": "主角必须借村中最后的灵气救人",
        "pressure_tests": [
            {"desire": "救人", "rule_pressure": "灵气即将枯竭", "costly_choice": "救一人并让全村断供"},
            {"desire": "取得弟子身份", "rule_pressure": "宗门只认有地契者", "costly_choice": "承认家族债务"},
            {"desire": "越境作战", "rule_pressure": "离开契约地衰减", "costly_choice": "暴露秘密借敌方灵脉"},
        ],
    }
    mocked = AsyncMock(
        side_effect=[json.dumps(incomplete, ensure_ascii=False), json.dumps(complete, ensure_ascii=False)]
    )
    monkeypatch.setattr(llm_client, "complete", mocked)

    result = await generate_world_engine({"genre": "玄幻", "reader_wish": "写资源与责任"}, [])

    assert result["core_rule"].startswith("借用灵脉")
    assert mocked.await_count == 2
    assert "压力测试" in mocked.await_args_list[1].args[1]


def test_blueprint_normalizes_three_named_stages() -> None:
    result = _normalize_book_blueprint({
        "major_arcs": {
            "stage_1_opening": {"title": "起势"},
            "stage_2_expansion": {"title": "扩张"},
            "stage_3_endgame": {"title": "终局"},
        }
    })

    assert [arc["title"] for arc in result["major_arcs"]] == ["起势", "扩张", "终局"]


@pytest.mark.asyncio
async def test_story_generation_retry_receives_exact_rejection_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    incomplete = [{"title": "缺页"}] * 3
    complete_seed = {
        "title": "归途",
        "one_sentence": "医生回乡重建诊所。",
        "protagonist_name": "苏宁",
        "hook": "旧病历牵出故人",
        "opening_event": "诊所迎来第一位急症病人",
        "story_engine": "病例与乡邻关系持续推进",
        "long_term_growth": "从逃避故乡到重建归属",
    }
    mocked = AsyncMock(side_effect=[
        json.dumps(incomplete, ensure_ascii=False),
        json.dumps([complete_seed] * 3, ensure_ascii=False),
    ])
    monkeypatch.setattr(llm_client, "complete", mocked)

    await generate_story_seeds([], count=3)

    retry_prompt = mocked.await_args_list[1].args[1]
    assert "缺少字段" in retry_prompt
    assert "one_sentence" in retry_prompt


@pytest.mark.asyncio
async def test_character_cast_normalizes_optional_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "complete",
        AsyncMock(return_value=json.dumps({"characters": [{"name": "林照", "role": "主角"}]})),
    )

    result = await generate_character_cast({"seed": {}, "primary_categories": ["都市"], "mode": "names"})

    assert result["characters"][0] == {
        "name": "林照",
        "gender": "",
        "role": "主角",
        "personality": "",
        "desire": "",
        "flaw": "",
        "relationship": "",
    }


def test_reality_boundary_rejects_supernatural_market_track() -> None:
    track = type(
        "Track",
        (),
        {
            "track_name": "诡异复苏·规则怪谈",
            "genre": "悬疑",
            "sub_genre": "规则怪谈",
            "golden_formula": "发现规则后利用超能力求生",
            "taste_tags": ["悬疑烧脑"],
        },
    )()

    assert _conflicts_with_reader_boundary(track, ["悬疑", "现实"], "社会派现实悬疑，无超能力")


def test_reality_boundary_rejects_apocalypse_market_track() -> None:
    track = type(
        "Track",
        (),
        {
            "track_name": "末日求生·废土流",
            "genre": "科幻",
            "sub_genre": "末日",
            "golden_formula": "灾变后建立据点对抗丧尸",
            "taste_tags": ["求生"],
        },
    )()

    assert _conflicts_with_reader_boundary(track, ["悬疑", "现实"], "熟人社会的现实悬疑")


def test_story_seed_cannot_smuggle_in_an_explicitly_avoided_element() -> None:
    seed = {"title": "旧楼", "story_engine": "逐层破解规则怪谈并获得异能"}

    assert _seed_violates_boundaries(seed, "现实悬疑，不要超能力和灵异")


def test_story_seed_allows_a_desired_system_element() -> None:
    seed = {"title": "新程", "story_engine": "完成系统任务获得成长资源"}

    assert not _seed_violates_boundaries(seed, "不要感情线")


def test_suspense_cast_rejects_cards_that_reveal_the_case_answer() -> None:
    characters = [
        {
            "name": "沈越",
            "role": "主角",
            "personality": "稳",
            "desire": "保住工作",
            "flaw": "怕冲突",
            "relationship": "母子",
        },
        {
            "name": "老杜",
            "role": "事件受害者",
            "personality": "要强",
            "desire": "修房",
            "flaw": "不求人",
            "relationship": "邻居",
        },
        {"name": "甲", "role": "邻居", "personality": "热心", "desire": "搬家", "flaw": "急躁", "relationship": "楼上"},
        {
            "name": "乙",
            "role": "遗属",
            "personality": "克制",
            "desire": "还债",
            "flaw": "隐瞒争吵",
            "relationship": "夫妻",
        },
        {
            "name": "丙",
            "role": "维修工",
            "personality": "谨慎",
            "desire": "接活",
            "flaw": "怕担责",
            "relationship": "供货",
        },
    ]

    assert not _cast_meets_genre_requirements(characters, ["悬疑", "现实"], "full")


def test_full_cast_requires_supporting_characters_for_every_genre() -> None:
    characters = [{
        "name": "苏晚棠",
        "role": "主角",
        "personality": "果断",
        "desire": "掌握命运",
        "flaw": "过于冒险",
        "relationship": "故事核心人物",
    }]

    assert not _cast_meets_genre_requirements(characters, ["武侠"], "full")


def test_suspense_blueprint_rejects_a_cost_free_ending_and_missing_evidence_chain() -> None:
    blueprint = {
        "title_candidates": ["人情账"],
        "synopsis": "一张收据带出旧事。",
        "protagonist_desire": "查清真相",
        "story_engine": "不断调查",
        "main_conflict": "真相与亲情冲突",
        "stakes": "母亲可能失去房子",
        "endgame": "找到不牵连母亲的突破路径",
        "major_arcs": [{"title": str(i), "goal": "查", "turn": "变", "result": "推进"} for i in range(3)],
    }

    reasons = _blueprint_rejection_reasons(blueprint, ["悬疑", "现实"])

    assert "主角长线欲望不能只是调查任务" in reasons
    assert "结局不能用两全办法逃掉核心代价" in reasons
    assert "证据链" in " ".join(reasons)


def test_blueprint_review_requires_score_and_no_blocking_issues() -> None:
    assert _blueprint_review_passes({"verdict": "pass", "score": 86, "blocking_issues": []})
    assert not _blueprint_review_passes({"verdict": "pass", "score": 81, "blocking_issues": []})
    assert not _blueprint_review_passes(
        {"verdict": "pass", "score": 90, "blocking_issues": [{"problem": "取证方式不成立"}]}
    )


def test_volume_review_requires_score_and_no_blocking_issues() -> None:
    assert _volume_review_passes({"verdict": "pass", "score": 88, "blocking_issues": []})
    assert not _volume_review_passes({"verdict": "pass", "score": 80, "blocking_issues": []})
    assert not _volume_review_passes(
        {"verdict": "pass", "score": 90, "blocking_issues": [{"problem": "卷末另开阴谋"}]}
    )


def test_chapter_plan_review_requires_score_and_no_blocking_issues() -> None:
    assert _chapter_plan_review_passes({"verdict": "pass", "score": 91, "blocking_issues": []})
    assert not _chapter_plan_review_passes({"verdict": "pass", "score": 79, "blocking_issues": []})
    assert not _chapter_plan_review_passes(
        {"verdict": "pass", "score": 90, "blocking_issues": [{"problem": "第一章提前泄底"}]}
    )


def test_chapter_plan_requires_readable_events_and_locations() -> None:
    plan = {
        "title_candidates": ["杀途初启", "血字面板", "第一道任务"],
        "reader_experience": "看主角弄清系统规则并面对第一次必须杀人的压力",
        "goal": "确认系统如何发布任务以及奖励怎样兑换",
        "conflict": "主角需要力量自保，却无法轻易接受杀人要求",
        "hook": "面板给出首个目标和不断减少的时限",
        "opening": {"situation": "主角独自在房中", "pressure": "体内异动加剧", "first_action": "关门检查异动"},
        "beats": [
            {
                "location": "沈晚烟卧房",
                "event": "沈晚烟锁门检查腹下异热，一块只有他能看见的血色面板在镜前展开",
                "immediate_goal": "弄清异动来源",
                "obstacle": "面板不回应追问，只显示陌生任务",
                "strategy": "逐项试探面板可以响应的操作",
                "turn": "首次触碰任务栏后出现兑换规则",
                "outcome": "他确认完成指定目标可以换取武功",
            },
            {
                "location": "沈晚烟卧房",
                "event": "沈晚烟试图关闭面板却触发倒计时，首个目标的身份轮廓随之浮现",
                "immediate_goal": "拒绝或拖延任务",
                "obstacle": "倒计时持续减少且没有取消入口",
                "strategy": "检查失败惩罚和目标信息",
                "turn": "目标特征指向即将进入花楼的人",
                "outcome": "他被迫在来人出现前决定是否接下任务",
            },
        ],
    }

    assert _chapter_plan_rejection_reasons(plan) == []
    plan["beats"][0]["event"] = "系统出现"
    assert any("事件过于简略" in reason for reason in _chapter_plan_rejection_reasons(plan))


def test_chapter_plan_fills_optional_authoring_details_from_story_events() -> None:
    plan = _normalize_chapter_plan({
        "title_candidates": ["首杀倒计时"],
        "beats": [
            {"event": "沈晚烟发现血色面板，并逐项查看任务与兑换规则", "obstacle": "她无法关闭面板"},
            {"event": "面板弹出首个目标的模糊轮廓，倒计时随即开始", "outcome": "她必须在来人出现前作出选择"},
        ],
    })

    assert _chapter_plan_rejection_reasons(plan) == []
    assert plan["goal"] == plan["beats"][0]["event"]
    assert plan["conflict"] == "她无法关闭面板"
    assert plan["hook"] == "她必须在来人出现前作出选择"
    assert plan["opening"]["first_action"] == plan["beats"][0]["event"]


def test_story_directions_reject_cosmetic_variants() -> None:
    directions = [
        {
            "key": f"direction-{index}",
            "title": f"方向{index}",
            "logline": "现代青年进入不同武侠世界，在原有故事变化后承担自己选择造成的后果。",
            "reader_payoff": "读者既能重逢熟悉人物，也能看到原剧情因主角介入发生真实而连续的变化。",
            "differentiation": "穿越不是观光，主角每次改变遗憾都会永久失去一种可以依赖的剧情先知优势。",
            "protagonist_engine": "主角想救下熟悉人物，但惯用的剧情知识不断失效，迫使他重新判断和选择。",
            "serial_engine": "进入世界、利用先知、蝴蝶效应扩大、关系迫使选择、携带代价离开。",
            "emotional_throughline": "他从把人物当剧情角色，逐渐学会承认他们拥有不受自己控制的人生。",
            "cost_and_risk": "最大的风险是每个世界重复同一套路，必须让离开后的关系和损失继续影响后续。",
        }
        for index in range(5)
    ]

    assert any("连载发动机" in reason for reason in _direction_rejection_reasons(directions))


def test_viability_gate_ignores_model_pass_without_longform_evidence() -> None:
    review = {
        "verdict": "pass",
        "evidence": {
            "reader_payoff": "每次介入原剧情，读者都能看到熟悉命运发生可追踪的变化与兑现。",
            "differentiation": "剧情先知会被主角自己的行动逐步摧毁，因此不能用全知轻易解决冲突。",
            "protagonist_engine": "主角必须在救人和保住回归资格之间选择，并承担关系上的持续损失。",
            "story_engine_variations": ["只有一种循环，尚未展开"],
            "relationship_engine": "被改变命运的人会主动追问主角的隐瞒，关系不会在副本结束时归零。",
            "antagonist_agency": "对手会根据主角泄露的异常信息改变计划，并争夺穿越机制背后的资源。",
            "escalation_capacity": "冲突从个人命运扩展到世界秩序，再扩展到不同世界能否继续独立存在。",
            "simulated_arcs": [],
            "promise_ledger": [],
            "opening_strategy": {"chapter_1": "先进入一个具体危机"},
            "endgame_direction": "最终必须选择恢复所有世界原状，还是承认改变并永久留在其中一个世界。",
        },
        "blocking_issues": [],
    }

    reasons = viability_blocking_reasons(review)

    assert "故事循环至少需要三种不同的冲突变体" in reasons
    assert any("三个" in reason and "故事弧" in reason for reason in reasons)
    assert any("承诺账本" in reason for reason in reasons)
    assert any("chapter_30" in reason for reason in reasons)
