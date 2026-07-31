from __future__ import annotations

from typing import Any


def _is_concrete_beat(beat: Any) -> bool:
    if not isinstance(beat, dict):
        return False
    event = str(beat.get("event") or "").strip()
    if len(event) >= 6:
        return True
    return bool(
        event
        and beat.get("immediate_goal")
        and beat.get("obstacle")
        and beat.get("turn")
        and beat.get("outcome")
    )


def run_guardian_checks(context_pack: dict[str, Any], beat_sheet: dict[str, Any]) -> dict[str, Any]:
    beats = beat_sheet.get("beats", [])
    beat_text = " ".join(str(beat.get("event", "")) for beat in beats if isinstance(beat, dict))
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: str) -> None:
        checks.append({"name": name, "passed": passed, "evidence": evidence})

    check("beat_count", 1 <= len(beats) <= 8, f"情节段数={len(beats)}，应为1至8段")
    check("concrete_events", bool(beats) and all(_is_concrete_beat(beat) for beat in beats), "每个 beat 必须是具体事件")
    check("outline_present", bool(context_pack.get("chapter_outline")), "章纲必须存在")
    check(
        "pov_present",
        bool(beat_sheet.get("pov_character") or context_pack["project"].get("protagonist")),
        "POV 必须明确",
    )
    check(
        "opening_continuity",
        bool(context_pack.get("recent_chapters")) or context_pack.get("chapter_sequence") == 1,
        "非首章必须有前章承接",
    )

    dead_entities = {
        state["entity_key"]
        for state in context_pack.get("active_state", [])
        if state.get("field") in {"生死", "生命状态"} and "死亡" in str(state.get("value"))
    }
    check("dead_character", not any(name in beat_text for name in dead_entities), f"死亡实体={sorted(dead_entities)}")

    low_confidence = [
        state for state in context_pack.get("active_state", []) if float(state.get("confidence", 1)) < 0.6
    ]
    referenced_low = [state["entity_key"] for state in low_confidence if state["entity_key"] in beat_text]
    check("low_confidence_state", not referenced_low, f"低置信度引用={referenced_low}")

    due_foreshadows = [
        item["content"]
        for item in context_pack.get("foreshadowing", [])
        if item.get("target_chapter") and item["target_chapter"] <= context_pack.get("chapter_sequence", 0)
    ]
    check(
        "due_foreshadowing",
        not due_foreshadows or any(item in beat_text for item in due_foreshadows),
        f"到期伏笔={due_foreshadows}",
    )
    rich_scenes = [beat for beat in beats if isinstance(beat, dict) and beat.get("immediate_goal")]
    check(
        "scene_causality",
        not rich_scenes
        or all(beat.get("obstacle") and beat.get("turn") and beat.get("outcome") for beat in rich_scenes),
        "情节段必须有即时目标、阻力、转折和结果",
    )
    check(
        "ending_consequence",
        bool(
            beat_sheet.get("hook")
            or beat_sheet.get("ending_image")
            or (beats and (beats[-1].get("outcome") or beats[-1].get("event")))
        ),
        "结尾必须留下已经发生作用的结果或压力",
    )

    failures = [item for item in checks if not item["passed"]]
    return {
        "passed": not failures,
        "checks": checks,
        "failures": failures,
        "issues": [item["evidence"] for item in failures],
    }
