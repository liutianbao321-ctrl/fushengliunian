from __future__ import annotations

from typing import Any


class NodeContractError(ValueError):
    pass


def _require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NodeContractError(f"{path} 必须是 JSON object")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise NodeContractError(f"{path} 必须是 JSON array")
    return value


def _require_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NodeContractError(f"{path} 必须是非空字符串")
    return value


def validate_node_output(node_name: str, output: Any) -> dict[str, Any]:
    result = _require_object(output, node_name)
    if node_name == "world-simulator":
        _require_text(result.get("simulation_id"), "world-simulator.simulation_id")
        decisions = _require_list(result.get("character_decisions"), "world-simulator.character_decisions")
        if not decisions:
            raise NodeContractError("world-simulator.character_decisions 不能为空")
        for index, decision in enumerate(decisions):
            decision = _require_object(decision, f"world-simulator.character_decisions[{index}]")
            _require_text(decision.get("character"), f"character_decisions[{index}].character")
            _require_text(decision.get("decision"), f"character_decisions[{index}].decision")
        _require_object(result.get("protagonist_projection"), "world-simulator.protagonist_projection")
    elif node_name == "novel-architect":
        beats = _require_list(result.get("beats"), "novel-architect.beats")
        if not 1 <= len(beats) <= 8:
            raise NodeContractError("novel-architect.beats 必须包含 1 至 8 个连续情节段")
        for index, beat in enumerate(beats):
            _require_text(
                _require_object(beat, f"novel-architect.beats[{index}]").get("event"), f"beats[{index}].event"
            )
        _require_text(result.get("pov_character"), "novel-architect.pov_character")
        continuity = _require_object(
            result.get("consciousness_thread"), "novel-architect.consciousness_thread"
        )
        _require_object(continuity.get("carry_in"), "consciousness_thread.carry_in")
        threads = _require_list(continuity.get("scene_threads"), "consciousness_thread.scene_threads")
        if len(threads) != len(beats):
            raise NodeContractError("consciousness_thread.scene_threads 必须与 beats 一一对应")
        for index, thread in enumerate(threads):
            thread = _require_object(thread, f"consciousness_thread.scene_threads[{index}]")
            _require_text(thread.get("attention_shift"), f"scene_threads[{index}].attention_shift")
            _require_text(thread.get("action_cause"), f"scene_threads[{index}].action_cause")
            _require_text(thread.get("residue"), f"scene_threads[{index}].residue")
        _require_object(continuity.get("chapter_aftertaste"), "consciousness_thread.chapter_aftertaste")
    elif node_name == "novel-guardian":
        if not isinstance(result.get("passed"), bool):
            raise NodeContractError("novel-guardian.passed 必须是 boolean")
        _require_list(result.get("checks"), "novel-guardian.checks")
        _require_list(result.get("failures"), "novel-guardian.failures")
    elif node_name == "novel-writer":
        _require_text(result.get("content"), "novel-writer.content")
        _require_text(result.get("summary"), "novel-writer.summary")
    elif node_name == "novel-editor":
        _require_text(result.get("content"), "novel-editor.content")
        _require_text(result.get("summary"), "novel-editor.summary")
        _require_list(result.get("edits"), "novel-editor.edits")
    elif node_name == "novel-critic":
        if not isinstance(result.get("passed"), bool):
            raise NodeContractError("novel-critic.passed 必须是 boolean")
        if not isinstance(result.get("score"), int | float):
            raise NodeContractError("novel-critic.score 必须是数字")
        _require_object(result.get("dimensions"), "novel-critic.dimensions")
        _require_list(result.get("issues"), "novel-critic.issues")
        _require_list(result.get("strengths"), "novel-critic.strengths")
        _require_list(result.get("rewrite_brief"), "novel-critic.rewrite_brief")
    elif node_name == "novel-humanizer":
        _require_text(result.get("content"), "novel-humanizer.content")
        _require_object(result.get("metrics"), "novel-humanizer.metrics")
        _require_list(result.get("semantic_issues"), "novel-humanizer.semantic_issues")
    elif node_name.startswith("observer-") or node_name == "novel-state-extractor":
        changes = _require_object(result.get("changes"), f"{node_name}.changes")
        for dimension, items in changes.items():
            _require_list(items, f"{node_name}.changes.{dimension}")
    elif node_name == "novel-verifier":
        _require_object(result.get("changes"), "novel-verifier.changes")
        _require_list(result.get("omissions"), "novel-verifier.omissions")
        _require_list(result.get("conflicts"), "novel-verifier.conflicts")
    elif node_name == "novel-pageindex":
        _require_list(result.get("ranked_node_ids"), "novel-pageindex.ranked_node_ids")
    else:
        raise NodeContractError(f"没有注册节点契约: {node_name}")
    return result
