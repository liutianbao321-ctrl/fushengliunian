from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.engine.humanizer import calculate_anti_ai_scores
from app.models import OutlineNode, PlotLedger, Project, StoryWiki


@dataclass(slots=True)
class GateEvidence:
    name: str
    passed: bool
    blocking: bool
    score: float | None
    evidence: dict[str, Any]


def _gate(
    name: str, passed: bool, evidence: dict[str, Any], score: float | None = None, blocking: bool = True
) -> GateEvidence:
    return GateEvidence(name=name, passed=passed, blocking=blocking, score=score, evidence=evidence)


def outline_is_concrete(beats: Any, outline_goal: Any) -> bool:
    if not isinstance(beats, list) or not str(outline_goal).strip():
        return False
    concrete_beats = [beat for beat in beats if isinstance(beat, dict) and len(str(beat.get("event", ""))) >= 6]
    return 1 <= len(concrete_beats) <= 8


DIALOGUE_ATTR_VERBS = (
    "说", "道", "问", "答", "喊", "叫", "低声", "冷笑", "喃喃", "叹", "笑",
    "怒", "骂", "嘟囔", "回应", "应道", "回道", "接口", "打断",
)


def max_consecutive_undirected_dialogue(content: str, known_names: set[str] | None = None) -> int:
    """A 级阻塞项：连续 >=3 段带引号对白却无任何说话人指示（人物身份混乱）。

    正文允许潜台词与动作承担关系史，但不允许读者分不清谁在说话。
    """
    paragraphs = [p for p in content.split("\n") if p.strip()]
    run = 0
    best = 0
    for para in paragraphs:
        has_quote = "“" in para or "”" in para or '"' in para
        has_named_actor = any(name in para for name in (known_names or set()))
        has_attr = any(verb in para for verb in DIALOGUE_ATTR_VERBS) or has_named_actor
        if has_quote and not has_attr:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def find_pov_violations(content: str, pov: str, known_names: set[str]) -> list[str]:
    violations: list[str] = []
    for name in sorted(known_names):
        if name == pov or name not in content:
            continue
        pattern = re.compile(rf"{re.escape(name)}[^。！？]{{0,20}}(?:心想|暗道|意识到|觉得|内心)")
        match = pattern.search(content)
        if match and not re.search(r"(?:像是|似乎|仿佛|好像)(?:觉得|意识到)", match.group(0)):
            violations.append(match.group(0))
    return violations


async def evaluate_quality_gates(
    db: AsyncSession,
    project: Project,
    chapter_sequence: int,
    content: str,
    beat_sheet: dict[str, Any],
    guardian: dict[str, Any],
    changes: list[dict[str, Any]],
    editorial_review: dict[str, Any] | None = None,
    change_conflicts: int = 0,
    unresolved_cross_chapter_issues: list[dict[str, Any]] | None = None,
) -> list[GateEvidence]:
    outline_node = await db.scalar(
        select(OutlineNode).where(
            OutlineNode.project_id == project.id,
            OutlineNode.layer == "L5",
            OutlineNode.seq == chapter_sequence,
        )
    )
    beats = beat_sheet.get("beats", [])
    outline_goal = (outline_node.meta if outline_node else {}).get("goal", "")
    concrete_beats = [beat for beat in beats if isinstance(beat, dict) and len(str(beat.get("event", ""))) >= 6]
    gate1_passed = outline_is_concrete(beats, outline_goal)

    gate2_passed = bool(guardian.get("passed")) and not guardian.get("failures") and not guardian.get("issues")
    word_count = len(re.sub(r"\s+", "", content))
    gate3_passed = 2800 <= word_count <= 5500

    wiki_pages = list((await db.scalars(select(StoryWiki).where(StoryWiki.project_id == project.id))).all())
    known_names = {alias for page in wiki_pages for alias in [page.title, *page.aliases] if len(alias) >= 2}
    declared_new = {
        change["entity_key"]
        for change in changes
        if change.get("operation") == "create" or change.get("dimension") == "new_entity"
    }
    planned_entities = set(beat_sheet.get("characters", []))
    unknown = sorted(name for name in planned_entities if name not in known_names and name not in declared_new)
    gate4_passed = len(unknown) <= 3

    pov = str(beat_sheet.get("pov_character") or project.protagonist_name)
    pov_violations = find_pov_violations(content, pov, known_names)
    gate5_passed = not pov_violations

    active_foreshadows = list(
        (
            await db.scalars(
                select(PlotLedger).where(
                    PlotLedger.project_id == project.id,
                    PlotLedger.status.in_(["open", "reminded"]),
                )
            )
        ).all()
    )
    known_foreshadows = {item.description for item in active_foreshadows}
    invalid_foreshadows = [
        change["entity_key"]
        for change in changes
        if change.get("dimension") == "foreshadowing"
        and change.get("operation") in {"resolve", "advance"}
        and change["entity_key"] not in known_foreshadows
    ]
    gate6_passed = not invalid_foreshadows

    canon_pages = [page for page in wiki_pages if page.category in {"canon_rule", "worldview"}]
    hard_rules = [
        line.removeprefix("-").strip()
        for page in canon_pages
        for line in page.content.splitlines()
        if line.strip().startswith("- 禁止")
    ]
    rule_violations = [rule for rule in hard_rules if rule.removeprefix("禁止").strip() in content]
    gate7_passed = not rule_violations

    anti_ai = calculate_anti_ai_scores(content)
    banned = ["总之", "综上所述", "值得一提的是", "由此可见", "不难发现"]
    banned_count = sum(content.count(term) for term in banned)
    gate8_passed = anti_ai["structure_density"] < 0.008 and banned_count <= 3

    fingerprint = project.style_profile.get("fingerprint") if isinstance(project.style_profile, dict) else None
    style_score = None
    style_evidence: dict[str, Any]
    if not fingerprint:
        style_passed = True
        style_evidence = {"calibrated": False, "reason": "项目尚未上传风格参考，门控不伪造相似度"}
    else:
        expected_dialogue = float(fingerprint.get("dialogue_ratio", 0.3))
        dialogue_chars = sum(len(value) for value in re.findall(r"[“\"]([^”\"]+)[”\"]", content))
        actual_dialogue = dialogue_chars / max(word_count, 1)
        style_score = max(0.0, 1.0 - abs(expected_dialogue - actual_dialogue) * 2)
        style_passed = style_score >= 0.75
        style_evidence = {"calibrated": True, "dialogue_ratio": actual_dialogue, "expected": expected_dialogue}

    review = editorial_review or {}
    editorial_score = float(review.get("score") or 0) if editorial_review is not None else None
    story_quality_passed = editorial_review is None or (
        bool(review.get("passed")) and editorial_score is not None and editorial_score >= 82
    )
    dimensions = review.get("dimensions", {}) if isinstance(review.get("dimensions"), dict) else {}
    reader_orientation_score = float(dimensions.get("reader_orientation") or 0) if editorial_review else None
    reader_experience_score = (
        float(dimensions.get("reader_experience_delivery") or 0) if editorial_review else None
    )
    has_author_constitution = bool(
        isinstance(project.style_profile, dict) and project.style_profile.get("author_constitution")
    )
    author_intent_score = float(dimensions.get("author_intent_delivery") or 0) if editorial_review else None
    author_intent_passed = (
        not has_author_constitution
        or (editorial_review is not None and author_intent_score is not None and author_intent_score >= 72)
    )
    reader_clarity_passed = editorial_review is None or (
        reader_orientation_score is not None
        and reader_orientation_score >= 72
        and reader_experience_score is not None
        and reader_experience_score >= 72
    )
    hard_categories = {
        "canon_contradiction",
        "knowledge_boundary",
        "missing_required_scene",
        "broken_causality",
        "character_betrayal",
        "author_non_negotiable",
    }
    hard_issues = [
        issue
        for issue in (review.get("issues") or [])
        if isinstance(issue, dict)
        and (
            issue.get("blocking") is True
            or str(issue.get("hard_category") or issue.get("category") or "") in hard_categories
        )
        and len(str(issue.get("evidence") or "").strip()) >= 4
    ]

    undirected_dialogue = max_consecutive_undirected_dialogue(content, known_names)

    # 三级负面清单：A级阻塞 / B级警告 / C级风格
    a_blocking_gates = [
        _gate(
            "cross_chapter_transition",
            not unresolved_cross_chapter_issues,
            {"issues": unresolved_cross_chapter_issues or []},
            blocking=True,
        ),
        _gate("narrative_hard_failures", not hard_issues,
              {"issues": hard_issues, "allowed_categories": sorted(hard_categories)},
              blocking=True),
        _gate("dialogue_attribution", undirected_dialogue < 3,
              {"max_consecutive_undirected_dialogue": undirected_dialogue}, blocking=True),
        _gate("continuity", gate2_passed, guardian, blocking=True),
        _gate("world_rules_heuristic", gate7_passed, {"violations": rule_violations}, blocking=True),
    ]
    b_warning_gates = [
        _gate("story_quality", story_quality_passed,
              {"score": editorial_score, "issues": review.get("issues", []),
               "dimensions": review.get("dimensions", {})},
              editorial_score, blocking=False),
        _gate("outline_compliance", gate1_passed,
              {"outline_goal": outline_goal, "concrete_beats": len(concrete_beats)}, blocking=False),
        _gate("word_count", gate3_passed,
              {"word_count": word_count, "recommended_range": [2800, 5500]},
              word_count / 4000, blocking=False),
        _gate("entity_references", gate4_passed, {"unknown_entities": unknown}, blocking=False),
        _gate("pov_boundary_heuristic", gate5_passed, {"pov": pov, "violations": pov_violations}, blocking=False),
        _gate("foreshadowing", gate6_passed, {"invalid_operations": invalid_foreshadows}, blocking=False),
        _gate("anti_ai", gate8_passed, {"metrics": anti_ai, "banned_count": banned_count}, blocking=False),
        _gate("style_consistency", style_passed, style_evidence, style_score, blocking=False),
        _gate("change_conflicts", change_conflicts == 0, {"count": change_conflicts}, blocking=False),
    ]
    c_style_gates = [
        _gate("reader_clarity", reader_clarity_passed,
              {"orientation": reader_orientation_score,
               "experience_delivery": reader_experience_score},
              min(reader_orientation_score or 0, reader_experience_score or 0) if editorial_review else None,
              blocking=False),
        _gate("author_intent", author_intent_passed,
              {"score": author_intent_score, "constitution_present": has_author_constitution},
              author_intent_score, blocking=False),
    ]
    return [*a_blocking_gates, *b_warning_gates, *c_style_gates]


def all_blocking_gates_pass(gates: list[GateEvidence]) -> bool:
    return all(gate.passed or not gate.blocking for gate in gates)


async def lint_plot_ledger(db: AsyncSession, project_id: uuid.UUID, current_chapter: int) -> GateEvidence:
    """非阻塞伏笔 lint：扫描 plot_ledger，将 open 且 due_chapter < 当前章的条目标记为 expired，并输出告警。

    在章节完成后调用；只写状态、不阻断发布。
    """
    rows = list(
        (
            await db.scalars(
                select(PlotLedger).where(PlotLedger.project_id == project_id, PlotLedger.status == "open")
            )
        ).all()
    )
    expired: list[uuid.UUID] = []
    for row in rows:
        if row.due_chapter is not None and row.due_chapter < current_chapter:
            row.status = "expired"
            row.updated_at = datetime.now(UTC)
            expired.append(row.id)
    if expired:
        await db.commit()
    return _gate(
        "foreshadowing_ledger",
        True,
        {"expired_count": len(expired), "expired_ids": [str(x) for x in expired]},
        blocking=False,
    )
