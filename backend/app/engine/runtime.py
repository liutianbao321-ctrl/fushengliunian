from __future__ import annotations

import asyncio
import json
from typing import Any

from app.config import get_settings
from app.engine.context import context_for_node
from app.engine.contracts import validate_node_output
from app.engine.guardian import run_guardian_checks
from app.engine.humanizer import humanize_text
from app.services.llm_client import llm_client
from app.utils.canonical import parse_json_object


def canonical_node_name(node_name: str) -> str:
    if node_name.startswith("novel-critic"):
        return "novel-critic"
    if node_name.startswith("novel-editor"):
        return "novel-editor"
    if node_name == "novel-state-extractor":
        return "novel-state-extractor"
    return node_name


def _prose_length(value: Any) -> int:
    return len("".join(str(value or "").split()))


def _validate_editor_completeness(output: dict[str, Any], payload: dict[str, Any]) -> None:
    source_length = _prose_length(payload.get("draft", {}).get("content"))
    if source_length < 1000:
        return
    edited_length = _prose_length(output.get("content"))
    minimum_length = max(3200, int(source_length * 0.65))
    if edited_length < minimum_length:
        raise ValueError(
            f"编辑稿被过度压缩：正文仅 {edited_length} 字，至少应为 {minimum_length} 字；"
            "必须保留完整事件链并重写问题场景，不能摘要化"
        )


def _prose_hard_range(payload: dict[str, Any]) -> tuple[int, int]:
    value = payload.get("requirements", {}).get("hard_length_range")
    if isinstance(value, list) and len(value) == 2 and all(isinstance(item, int) for item in value):
        return int(value[0]), int(value[1])
    return 2800, 5500


def _architect_authored_continuity(output: dict[str, Any]) -> bool:
    nested = output.get("beat_sheet") if isinstance(output.get("beat_sheet"), dict) else output
    beats = nested.get("beats") if isinstance(nested, dict) else None
    continuity = nested.get("consciousness_thread") if isinstance(nested, dict) else None
    threads = continuity.get("scene_threads") if isinstance(continuity, dict) else None
    carry_in = continuity.get("carry_in") if isinstance(continuity, dict) else None
    aftertaste = continuity.get("chapter_aftertaste") if isinstance(continuity, dict) else None
    return bool(
        isinstance(beats, list)
        and isinstance(carry_in, dict)
        and carry_in
        and isinstance(threads, list)
        and len(beats) == len(threads)
        and all(
            isinstance(item, dict)
            and item.get("attention_shift")
            and item.get("action_cause")
            and item.get("residue")
            for item in threads
        )
        and isinstance(aftertaste, dict)
        and aftertaste
    )


def _missing_simulated_characters(output: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    expected = payload.get("context_pack", {}).get("scene_entities") or []
    decisions = output.get("character_decisions") if isinstance(output, dict) else []
    decisions = decisions if isinstance(decisions, list) else []
    covered = {
        str(item.get("character") or "").strip()
        for item in decisions if isinstance(item, dict)
    }
    return [str(name) for name in expected if str(name).strip() and str(name).strip() not in covered]


def _normalize_change_groups(changes: Any) -> dict[str, list[dict[str, Any]]]:
    known_dimensions = {
        "character_state",
        "relationship",
        "knowledge",
        "location_state",
        "item_state",
        "timeline",
    }
    source_groups = changes.items() if isinstance(changes, dict) else [("other", changes)]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for source_dimension, items in source_groups:
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            dimension = str(item.get("dimension") or item.get("type") or source_dimension or "other")
            if dimension == "other" and item.get("field") in known_dimensions:
                dimension = str(item["field"])
            grouped.setdefault(dimension, []).append(item)
    return grouped


def normalize_node_output(node_name: str, output: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    node_name = canonical_node_name(node_name)
    context = payload.get("context_pack", {})
    protagonist = context.get("project", {}).get("protagonist") or "主角"
    chapter = context.get("chapter_sequence", 1)
    if node_name == "world-simulator":
        result = dict(output)
        result.setdefault("simulation_id", f"simulation-{chapter}")
        result.setdefault("character_decisions", [])
        result.setdefault(
            "protagonist_projection",
            {
                "protagonist": protagonist,
                "observable_effects": [],
                "hidden_pressures": [],
                "chosen_decision": "按本章章纲推进故事",
                "decision_reason": "承接当前冲突",
                "causal_chain": [],
            },
        )
        return result
    if node_name == "novel-editor":
        result = dict(output)
        if isinstance(result.get("edits"), dict):
            result["edits"] = list(result["edits"].values())
        return result
    if node_name == "novel-critic":
        result = dict(output)
        if isinstance(result.get("passed"), str):
            result["passed"] = result["passed"].strip().lower() in {"true", "yes", "pass", "passed", "通过"}
        for field in ("issues", "strengths", "rewrite_brief"):
            value = result.get(field)
            if isinstance(value, dict):
                result[field] = list(value.values())
            elif not isinstance(value, list):
                result[field] = [] if value in (None, "") else [str(value)]
        score = result.get("score")
        if isinstance(score, str):
            try:
                result["score"] = float(score.removesuffix("分"))
            except ValueError:
                pass
        if isinstance(result.get("score"), int | float) and result["score"] <= 10:
            result["score"] = round(float(result["score"]) * 10, 1)
        dimensions = result.get("dimensions")
        if isinstance(dimensions, list):
            result["dimensions"] = {
                str(item.get("name") or item.get("category") or index): item.get("score", 0)
                for index, item in enumerate(dimensions)
                if isinstance(item, dict)
            }
        return result
    if node_name.startswith("observer-") or node_name == "novel-state-extractor":
        result = dict(output)
        changes = result.get("changes")
        if isinstance(changes, dict | list):
            result["changes"] = _normalize_change_groups(changes)
        return result
    if node_name == "novel-verifier":
        result = dict(output)
        changes = result.get("changes")
        if isinstance(changes, dict | list):
            result["changes"] = _normalize_change_groups(changes)
        for field in ("omissions", "conflicts"):
            value = result.get(field)
            if isinstance(value, dict):
                result[field] = list(value.values())
            elif not isinstance(value, list):
                normalized = str(value or "").strip().lower()
                no_findings = normalized in {
                    "",
                    "无",
                    "无遗漏",
                    "无冲突",
                    "none",
                    "null",
                    "未发现",
                } or normalized.startswith(("未发现遗漏", "未发现冲突", "没有遗漏", "没有冲突"))
                no_findings = no_findings or (
                    normalized.startswith("未发现") and normalized.endswith(("遗漏", "冲突"))
                )
                result[field] = [] if no_findings else [str(value)]
        return result
    if node_name != "novel-architect":
        return output

    result = dict(output)
    nested = output.get("beat_sheet") if isinstance(output.get("beat_sheet"), dict) else {}
    candidate_beats = output.get("beats") or nested.get("beats")
    outline = context.get("chapter_outline", {})
    if not isinstance(candidate_beats, list) or len(candidate_beats) < 1:
        candidate_beats = outline.get("beats", [])
    if not isinstance(candidate_beats, list) or len(candidate_beats) < 1:
        from app.services.project_bootstrap import scene_contract_to_chapter_plan

        legacy_plan = scene_contract_to_chapter_plan(
            outline,
            title=str((outline.get("title_candidates") or [f"第{chapter}章"])[0]),
            protagonist=protagonist,
        )
        candidate_beats = legacy_plan["beats"]
        for field, value in legacy_plan.items():
            result.setdefault(field, value)
    result["beats"] = [
        {**item, "segment": str(item.get("segment") or f"scene-{index + 1}")}
        for index, item in enumerate(candidate_beats)
        if isinstance(item, dict) and str(item.get("event", "")).strip()
    ]
    outline_fields = (
        "title_candidates",
        "goal",
        "conflict",
        "reader_experience",
        "protagonist_change",
        "opening",
        "style_direction",
        "hook",
        "ending_image",
        "must_avoid",
    )
    for field in outline_fields:
        if field in outline:
            result[field] = outline[field]
    result.setdefault("chapter_sequence", chapter)
    result["pov_character"] = result.get("pov_character") or protagonist
    result["characters"] = (
        result.get("characters")
        or outline.get("characters")
        or context.get("scene_entities")
        or [protagonist]
    )
    continuity = result.get("consciousness_thread")
    if not isinstance(continuity, dict):
        continuity = {}
    carry_in = continuity.get("carry_in")
    if not isinstance(carry_in, dict):
        memory = context.get("living_memory", {})
        carry_in = {
            "previous_residue": memory.get("carried_residue", []),
            "unfinished_moment": memory.get("previous_ending", ""),
            "active_intention": outline.get("goal") or "承接眼前尚未完成的事",
        }
    raw_threads = continuity.get("scene_threads")
    raw_threads = raw_threads if isinstance(raw_threads, list) else []
    scene_threads: list[dict[str, Any]] = []
    for index, beat in enumerate(result["beats"]):
        candidate = raw_threads[index] if index < len(raw_threads) and isinstance(raw_threads[index], dict) else {}
        previous = result["beats"][index - 1] if index else None
        scene_threads.append(
            {
                **candidate,
                "attention_shift": str(
                    candidate.get("attention_shift")
                    or (previous or {}).get("outcome")
                    or beat.get("obstacle")
                    or beat["event"]
                ),
                "action_cause": str(
                    candidate.get("action_cause")
                    or beat.get("strategy")
                    or beat.get("immediate_goal")
                    or beat["event"]
                ),
                "residue": str(
                    candidate.get("residue") or beat.get("outcome") or beat.get("turn") or beat["event"]
                ),
            }
        )
    aftertaste = continuity.get("chapter_aftertaste")
    if not isinstance(aftertaste, dict):
        last = result["beats"][-1]
        aftertaste = {
            "internal_shift": result.get("protagonist_change") or last.get("outcome") or last["event"],
            "left_unsaid": result.get("hook") or "眼前后果尚未被人物说透",
            "echo": result.get("ending_image") or last.get("sensory_anchor") or last["event"],
        }
    result["consciousness_thread"] = {
        "carry_in": carry_in,
        "scene_threads": scene_threads,
        "chapter_aftertaste": aftertaste,
    }
    return result


def _mock_prose(payload: dict[str, Any]) -> dict[str, Any]:
    context = payload["context_pack"]
    beat_sheet = payload["beat_sheet"]
    protagonist = context["project"]["protagonist"]
    chapter = context["chapter_sequence"]
    beats = beat_sheet["beats"]
    paragraphs: list[str] = []
    for index in range(44):
        beat = beats[index % len(beats)]
        pressure = (
            "脚步越过门槛时，屋里的声音忽然低了下去" if index % 3 == 0 else "风从窄巷里钻进来，卷动墙角尚未干透的纸"
        )
        action = (
            "他没有立即回答，只把掌心压在桌沿，先看清每个人站的位置"
            if index % 2 == 0
            else "他向前挪了半步，让来人的视线不得不跟着偏转"
        )
        consequence = f"这一步没有解决问题，却让第{index + 1}个细节显出真正的分量"
        if index % 5 == 0:
            paragraph = f"“你确定还要往前？”有人问。{protagonist}听完才抬眼。{pressure}。{action}。{consequence}。"
        elif index % 4 == 0:
            paragraph = (
                f"{pressure}。{protagonist}记住了那道停顿，没有急着解释。"
                f"{beat['event']}。{action}，随后把代价留给对方选择。{consequence}。"
            )
        else:
            paragraph = (
                f"{protagonist}沿着眼前的线索继续推进。{pressure}。{action}。"
                f"事情因此改变了方向：{beat['event']}。{consequence}，新的压力也顺势落到他肩上。"
            )
        paragraphs.append(paragraph)
    content = "\n\n".join(paragraphs)
    return {
        "content": content,
        "summary": f"{protagonist}在第{chapter}章承接前章压力，完成一次有代价的选择，并从逆转中发现新的行动方向。",
    }


def mock_node(node_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    context = payload.get("context_pack", {})
    protagonist = context.get("project", {}).get("protagonist", "主角")
    chapter = context.get("chapter_sequence", 1)
    if node_name == "world-simulator":
        characters = context.get("scene_entities") or [protagonist]
        return {
            "simulation_id": f"simulation-{chapter}",
            "character_decisions": [
                {
                    "character": name,
                    "current_goal": "推动本章目标",
                    "knowledge_boundary": "仅依据已知事实行动",
                    "decision": "承担当前选择",
                    "decision_reason": "外部压力已经抵达",
                    "action": "进入本章因果链",
                    "action_duration": "半日",
                    "completion_state": "in_progress",
                    "butterfly_effects": [],
                }
                for name in characters
            ],
            "protagonist_projection": {
                "protagonist": protagonist,
                "observable_effects": ["外部压力抵达现场"],
                "hidden_pressures": [],
                "chosen_decision": "主动查明异常",
                "decision_reason": "退让会失去主动权",
                "causal_chain": ["异常出现", "主角行动", "局势逆转"],
            },
        }
    if node_name == "novel-architect":
        goal = context.get("chapter_outline", {}).get("goal", "冲突进一步升级")
        confirmed_beats = context.get("chapter_outline", {}).get("beats")
        beats = confirmed_beats if isinstance(confirmed_beats, list) and 1 <= len(confirmed_beats) <= 8 else [
            {"segment": "scene-1", "event": "前章余波抵达现场，主角以具体行动接住异常。"},
            {"segment": "scene-2", "event": goal},
            {"segment": "scene-3", "event": "选择产生明确代价，并留下下一步必须处理的新压力。"},
        ]
        return normalize_node_output("novel-architect", {
            "chapter_sequence": chapter,
            "pov_character": protagonist,
            "characters": context.get("scene_entities", [protagonist]),
            "beats": beats,
        }, payload)
    if node_name == "novel-guardian":
        return run_guardian_checks(context, payload["beat_sheet"])
    if node_name == "novel-writer":
        return _mock_prose(payload)
    if node_name == "novel-editor":
        return {"content": payload["draft"]["content"], "summary": payload["draft"]["summary"], "edits": []}
    if node_name == "novel-humanizer":
        # humanizer 在 run_agent_node 中作为 LLM 润色节点处理；此处仅作无法到达的兜底
        return {"content": payload.get("content", ""), "metrics": {}, "semantic_issues": []}
    if node_name == "observer-social":
        return {
            "changes": {
                "character_state": [
                    {
                        "name": protagonist,
                        "field": "行动状态",
                        "old": "承接前章余波",
                        "new": f"第{chapter}章后承担新的选择",
                        "confidence": 0.82,
                        "evidence": {"quote": f"{protagonist}沿着眼前的线索继续推进"},
                    }
                ]
            }
        }
    if node_name == "observer-environment":
        return {"changes": {"timeline": [{"name": "故事进度", "field": "当前章节", "new": chapter, "confidence": 0.9}]}}
    if node_name == "observer-narrative":
        return {
            "changes": {
                "foreshadowing": [
                    {
                        "name": f"第{chapter}章新压力",
                        "action": "plant",
                        "new": "尚未揭示来源的新压力",
                        "confidence": 0.78,
                        "evidence": {
                            "target_chapter": chapter + 12,
                            "importance": "B",
                            "related_entities": [protagonist],
                        },
                    }
                ]
            }
        }
    if node_name == "novel-state-extractor":
        content = str(payload.get("content") or "")
        quote = content[:40].strip()
        return {
            "changes": {
                "timeline": [
                    {
                        "entity_key": "故事进度",
                        "field": "当前章节",
                        "operation": "set",
                        "old": chapter - 1,
                        "new": chapter,
                        "confidence": 0.9,
                        "evidence": {"quote": quote},
                    }
                ] if len(quote) >= 4 else []
            }
        }
    if node_name == "novel-verifier":
        return {"changes": {}, "omissions": [], "conflicts": []}
    raise ValueError(f"未知 mock node: {node_name}")


PROSE_NODES = {"novel-writer", "novel-humanizer", "novel-editor"}
SUMMARY_SEPARATOR = "===SUMMARY==="


def _scene_temperature(node_name: str) -> float:
    """按调用场景分温度：正文创作类高温度保留文学生成力，结构化任务低温度保稳定。"""
    if node_name in ("novel-writer", "novel-humanizer"):
        return 0.85
    if node_name in ("novel-editor", "novel-editor-repair"):
        return 0.6
    return 0.3


def _split_prose_and_summary(raw: str) -> tuple[str, str]:
    """正文节点走纯文本通道：正文后另起一行以分隔符引出摘要；缺省时用首段兜底。"""
    if SUMMARY_SEPARATOR in raw:
        prose, _, summary = raw.partition(SUMMARY_SEPARATOR)
        return prose.strip(), summary.strip()
    content = raw.strip()
    return content, content[:60].replace("\n", " ")


def _structured_model_candidates(settings: Any) -> list[str]:
    aliyun_planning_model = getattr(settings, "llm_aliyun_planning_model", None)
    aliyun_model = getattr(settings, "llm_aliyun_model", None)
    deepseek_model = getattr(settings, "llm_deepseek_model", None)
    candidates = [
        f"aliyun:{aliyun_planning_model or aliyun_model}" if aliyun_planning_model or aliyun_model else None,
        getattr(settings, "llm_planning_model", None),
        *list(getattr(settings, "llm_planning_fallback_models", []) or []),
        getattr(settings, "llm_planning_fallback_model", None),
        getattr(settings, "llm_model", None) or "default",
        *list(getattr(settings, "llm_fallback_models", []) or []),
        getattr(settings, "llm_fallback_model", None),
        f"deepseek:{deepseek_model}" if deepseek_model else None,
    ]
    return list(dict.fromkeys(str(candidate) for candidate in candidates if candidate))


async def _complete_json_once(
    *,
    model: str,
    system_prompt: str,
    payload: dict[str, Any],
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    raw = await llm_client.complete(
        system_prompt,
        json.dumps(payload, ensure_ascii=False),
        response_format="json",
        stream=True,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_seconds=90,
        request_attempts=1,
    )
    return parse_json_object(raw)


async def _complete_structured_node(
    skill_name: str,
    system_prompt: str,
    model_payload: dict[str, Any],
    payload: dict[str, Any],
    settings: Any,
) -> dict[str, Any]:
    candidates = _structured_model_candidates(settings)
    if not candidates:
        raise RuntimeError("结构化生成模型未配置")
    max_tokens = int(getattr(settings, "generation_max_tokens_structured", 4096))
    temperature = _scene_temperature(skill_name)
    failures: list[str] = []
    for candidate in candidates:
        try:
            output = await _complete_json_once(
                model=candidate,
                system_prompt=system_prompt,
                payload=model_payload,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if skill_name == "world-simulator":
                missing_characters = _missing_simulated_characters(output, model_payload)
                if missing_characters:
                    repair_prompt = (
                        system_prompt
                        + "\n\n上一轮人物模拟不完整。重新输出完整 JSON；character_decisions 必须逐一覆盖"
                        + " scene_entities 中的每个实名角色，不得省略，且每项必须包含非空 character 与 decision。"
                    )
                    output = await _complete_json_once(
                        model=candidate,
                        system_prompt=repair_prompt,
                        payload={
                            "input": model_payload,
                            "missing_characters": missing_characters,
                            "incomplete_previous_output": output,
                        },
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    still_missing = _missing_simulated_characters(output, model_payload)
                    if still_missing:
                        raise ValueError("世界模拟仍遗漏本章角色：" + "、".join(still_missing))
            if skill_name == "novel-architect" and not _architect_authored_continuity(output):
                repair_prompt = (
                    system_prompt
                    + "\n\n上一轮遗漏了 consciousness_thread。重新输出完整 JSON，不得只返回 beats。"
                    + " consciousness_thread 必须包含 carry_in、与 beats 等长的 scene_threads，"
                    + "每个 scene_thread 必须有 attention_shift、action_cause、residue，最后包含 chapter_aftertaste。"
                )
                output = await _complete_json_once(
                    model=candidate,
                    system_prompt=repair_prompt,
                    payload={"input": model_payload, "incomplete_previous_output": output},
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            output = normalize_node_output(skill_name, output, payload)
            if skill_name == "novel-editor":
                _validate_editor_completeness(output, payload)
            return validate_node_output(skill_name, output)
        except Exception as exc:
            failures.append(f"{candidate}: {exc}")
            continue
    raise RuntimeError("结构化节点未返回可用 JSON，已尝试：" + "；".join(failures[-4:]))


async def run_agent_node(node_name: str, payload: dict[str, Any], thread_id: str) -> dict[str, Any]:
    skill_name = canonical_node_name(node_name)
    if node_name == "novel-guardian":
        output = run_guardian_checks(payload["context_pack"], payload["beat_sheet"])
        return validate_node_output(node_name, output)
    if node_name == "novel-humanizer":
        content, metrics = await humanize_text(payload.get("content", ""), payload.get("context_pack", {}))
        output = {"content": content, "metrics": metrics, "semantic_issues": []}
        return validate_node_output(node_name, output)
    settings = get_settings()
    if settings.llm_backend == "mock":
        await asyncio.sleep(0)
        if skill_name == "novel-critic":
            output = {
                "passed": True,
                "score": 82,
                "dimensions": {
                    name: 82
                    for name in (
                        "author_intent_delivery",
                        "reader_orientation",
                        "reader_experience_delivery",
                        "opening_hook",
                        "character_agency",
                        "conflict_progression",
                        "information_control",
                        "dialogue_subtext",
                        "pov_immersion",
                        "prose_naturalness",
                        "consciousness_continuity",
                        "character_specificity",
                        "chapter_hook",
                    )
                },
                "issues": [],
                "strengths": ["章纲事件完整"],
                "rewrite_brief": [],
            }
        else:
            output = mock_node(skill_name, payload)
        return validate_node_output(skill_name, normalize_node_output(skill_name, output, payload))
    from app.services.skill_loader import load_skill_prompt

    skill_prompt = load_skill_prompt(skill_name)
    settings = get_settings()
    model_payload = dict(payload)
    if isinstance(payload.get("context_pack"), dict):
        model_payload["context_pack"] = context_for_node(payload["context_pack"], skill_name)
    if skill_name in PROSE_NODES:
        # 正文生成节点走纯文本通道：不要求 JSON，避免正文被 JSON 转义分心
        system_prompt = (
            f"{skill_prompt}\n\n---\n你正在执行小说正文生成节点 {skill_name}。"
            "请直接输出纯文本正文，不要输出 JSON、代码块或任何字段名。"
            f"正文写完后另起一行，写分隔符 {SUMMARY_SEPARATOR}，"
            "其后再写一句中文章节摘要（不超过 60 字，概括本章核心事件）。"
            if skill_prompt
            else f"你正在执行小说正文生成节点 {skill_name}。请直接输出纯文本正文，不要输出 JSON。"
        )
        if skill_name == "novel-writer":
            minimum, maximum = _prose_hard_range(payload)
            target = payload.get("requirements", {}).get("target_length") or [3400, 4200]
            system_prompt += (
                f"\n本次正文建议目标为 {target[0]}-{target[1]} 汉字，低于 {minimum} 字通常视为疑似未写完整；"
                f"{maximum} 字仅作节奏参考，不得为了压到上限删掉必要事件链、人物动机、关系余波和结尾钩子。"
                "输出前必须自行删减重复解释。"
            )
        elif skill_name == "novel-editor":
            source_length = _prose_length(payload.get("draft", {}).get("content"))
            minimum = max(3200, int(source_length * 0.65)) if source_length >= 1000 else 0
            system_prompt += (
                f"\n底稿约 {source_length} 字，修订稿不得少于 {minimum} 字。"
                "必须输出从开头到结尾的完整修订正文，不得概述、节选或只输出改动段落；"
                "未被明确指出有硬问题的段落应原样或近乎原样保留。"
            )
        raw = await llm_client.complete(
            system_prompt,
            json.dumps(model_payload, ensure_ascii=False),
            response_format="text",
            stream=True,
            max_tokens=settings.generation_max_tokens_prose,
            temperature=_scene_temperature(skill_name),
        )
        legacy_editor_output: dict[str, Any] | None = None
        if skill_name == "novel-editor" and raw.lstrip().startswith("{"):
            try:
                legacy_editor_output = parse_json_object(raw)
            except (TypeError, ValueError):
                legacy_editor_output = None
        if legacy_editor_output and legacy_editor_output.get("content"):
            content = str(legacy_editor_output["content"])
            summary = str(legacy_editor_output.get("summary") or content[:60]).strip()
        else:
            content, summary = _split_prose_and_summary(raw)
        if skill_name == "novel-writer":
            minimum, maximum = _prose_hard_range(payload)
            length = _prose_length(content)
            if length < minimum:
                repair_prompt = (
                    system_prompt
                    + f"\n上一稿正文为 {length} 字，低于 {minimum} 字，疑似事件链未写完整。"
                    + "请补足必要的动作、反应与后果，保留完整事件链、人物动机、关系余波和结尾钩子。"
                )
                raw = await llm_client.complete(
                    repair_prompt,
                    json.dumps(
                        {
                            "draft": content,
                            "beat_sheet": payload.get("beat_sheet", {}),
                            "requirements": payload.get("requirements", {}),
                        },
                        ensure_ascii=False,
                    ),
                    response_format="text",
                    stream=True,
                    max_tokens=settings.generation_max_tokens_prose,
                    temperature=0.45,
                )
                content, summary = _split_prose_and_summary(raw)
                final_length = _prose_length(content)
                if final_length < minimum:
                    raise ValueError(
                        f"正文长度疑似未完成：{final_length} 字，至少应为 {minimum} 字"
                    )
        output = {"content": content, "summary": summary}
        if skill_name == "novel-editor":
            output["edits"] = (legacy_editor_output or {}).get("edits", [])
            _validate_editor_completeness(output, payload)
        output = normalize_node_output(skill_name, output, payload)
        return validate_node_output(skill_name, output)
    # 结构化节点保留 JSON 输出；JSON 解析或契约失败时由这里切换候选模型。
    system_prompt = (
        f"{skill_prompt}\n\n---\n你正在执行小说生产节点 {skill_name}。只输出符合该节点契约的 JSON 对象。"
        if skill_prompt
        else f"你正在执行小说生产节点 {skill_name}。只输出符合该节点契约的 JSON 对象。"
    )
    return await _complete_structured_node(skill_name, system_prompt, model_payload, payload, settings)
