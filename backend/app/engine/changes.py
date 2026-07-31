from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.engine.retrieval import embed_texts, embedding_configured
from app.models import ChapterRevision, CurrentState, StateEvent
from app.utils.canonical import payload_hash

DIMENSION_TO_ENTITY = {
    "character_state": "character",
    "relationship": "relationship",
    "location_state": "location",
    "faction_state": "faction",
    "item_state": "item",
    "knowledge": "knowledge",
    "foreshadowing": "foreshadowing",
    "timeline": "timeline",
    "conflict": "conflict",
    "world_rule": "canon_rule",
    "narrative_residue": "narrative_memory",
}


@dataclass(slots=True)
class MergeIssue:
    dimension: str
    entity_key: str
    field: str
    values: list[Any]


def normalize_confidence(value: Any, default: float = 0.6) -> float:
    if isinstance(value, str):
        normalized = value.strip().lower()
        labels = {
            "high": 0.9,
            "medium": 0.7,
            "low": 0.4,
            "高": 0.9,
            "中": 0.7,
            "低": 0.4,
        }
        if normalized in labels:
            return labels[normalized]
        if normalized.endswith("%"):
            try:
                return max(0.0, min(1.0, float(normalized[:-1]) / 100))
            except ValueError:
                return default
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return default
    if confidence > 1 and confidence <= 100:
        confidence /= 100
    return max(0.0, min(1.0, confidence))


def normalize_change(dimension: str, item: dict[str, Any]) -> dict[str, Any]:
    evidence = item.get("evidence", {})
    evidence_values = evidence if isinstance(evidence, dict) else {}
    entity_fields = (
        "entity_key",
        "name",
        "character",
        "location",
        "place",
        "item",
        "object",
        "target",
        "content",
    )
    entity_key = str(
        next(
            (
                value
                for field in entity_fields
                if (value := item.get(field) or evidence_values.get(field))
            ),
            "global",
        )
    ).strip()
    if entity_key == "global" and dimension in {"location_state", "item_state"}:
        identity_evidence = evidence if evidence else {"field": item.get("field"), "new": item.get("new")}
        entity_key = f"unresolved:{dimension}:{payload_hash(identity_evidence)[:12]}"
    field = str(item.get("field") or item.get("action") or dimension).strip()
    operation = str(item.get("operation") or ("create" if item.get("action") == "plant" else "set"))
    new_value = item.get("new_value", item.get("new", item.get("value", item.get("content"))))
    old_value = item.get("old_value", item.get("old"))
    if isinstance(evidence, str):
        evidence = {"quote": evidence}
    elif not isinstance(evidence, dict):
        evidence = {"details": evidence}
    return {
        "dimension": dimension,
        "entity_type": DIMENSION_TO_ENTITY.get(dimension, dimension),
        "entity_key": entity_key,
        "field": field,
        "operation": operation,
        "old_value": {"value": old_value} if old_value is not None else None,
        "new_value": {"value": new_value} if new_value is not None else None,
        "evidence": evidence,
        "confidence": normalize_confidence(item.get("confidence")),
        "source": str(item.get("source", "observer")),
    }


def merge_extractions(
    extractions: list[dict[str, Any]], verifier: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], list[MergeIssue]]:
    candidates: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for extraction in extractions:
        changes = extraction.get("changes", extraction)
        if not isinstance(changes, dict):
            continue
        for dimension, items in changes.items():
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                continue
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                item = normalize_change(dimension, raw)
                key = (item["dimension"], item["entity_key"], item["field"])
                candidates.setdefault(key, []).append(item)

    rejected_claims = [
        item
        for item in (verifier or {}).get("conflicts", [])
        if isinstance(item, dict) and item.get("entity_key") and item.get("observer_claim")
    ]

    def rejected(item: dict[str, Any]) -> bool:
        value = str((item.get("new_value") or {}).get("value") or "")
        return any(
            str(conflict["entity_key"]) == item["entity_key"]
            and str(conflict.get("field") or item["field"]) == item["field"]
            and (
                str(conflict["observer_claim"]) in value
                or value in str(conflict["observer_claim"])
            )
            for conflict in rejected_claims
        )

    for key, options in list(candidates.items()):
        candidates[key] = [item for item in options if not rejected(item)]
        if not candidates[key]:
            del candidates[key]

    verifier_changes = (verifier or {}).get("changes", {})
    if isinstance(verifier_changes, dict):
        for dimension, items in verifier_changes.items():
            for raw in items if isinstance(items, list) else []:
                if isinstance(raw, dict):
                    item = normalize_change(dimension, {**raw, "source": "verifier"})
                    if not rejected(item):
                        candidates.setdefault((dimension, item["entity_key"], item["field"]), []).append(item)

    merged: list[dict[str, Any]] = []
    issues: list[MergeIssue] = []
    for (dimension, entity_key, field), options in candidates.items():
        values: dict[str, list[dict[str, Any]]] = {}
        for option in options:
            values.setdefault(payload_hash(option.get("new_value")), []).append(option)
        winner_group = max(values.values(), key=lambda group: (len(group), max(item["confidence"] for item in group)))
        winner = max(winner_group, key=lambda item: item["confidence"])
        agreement = len(winner_group)
        winner["confidence"] = min(0.99, max(winner["confidence"], 0.5 + agreement * 0.15))
        winner["evidence"] = {
            **winner.get("evidence", {}),
            "extractor_agreement": agreement,
            "candidate_count": len(options),
        }
        if len(values) > 1:
            issues.append(MergeIssue(dimension, entity_key, field, [item.get("new_value") for item in options]))
        merged.append(winner)
    return merged, issues


def keep_evidenced_changes(
    changes: list[dict[str, Any]], content: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Only durable state claims backed by an exact quote may enter Canon state."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    compact_content = "".join(content.split())
    for change in changes:
        evidence = change.get("evidence") if isinstance(change.get("evidence"), dict) else {}
        quote = str(evidence.get("quote") or "").strip()
        if len("".join(quote.split())) < 4 or "".join(quote.split()) not in compact_content:
            rejected.append({
                "dimension": change.get("dimension"),
                "entity_key": change.get("entity_key"),
                "field": change.get("field"),
                "reason": "正文中找不到逐字证据",
                "quote": quote[:120],
            })
            continue
        accepted.append(change)
    return accepted, rejected


async def persist_state_events(
    db: AsyncSession,
    revision: ChapterRevision,
    changes: list[dict[str, Any]],
) -> list[StateEvent]:
    events: list[StateEvent] = []
    for index, change in enumerate(changes):
        event_key = f"{revision.id}:{change['dimension']}:{change['entity_key']}:{change['field']}:{index}"
        event = await db.scalar(
            select(StateEvent).where(
                StateEvent.project_id == revision.project_id,
                StateEvent.event_key == event_key,
            )
        )
        values = {
            "event_type": change["dimension"],
            "operation": change["operation"],
            "entity_type": change["entity_type"],
            "entity_key": change["entity_key"],
            "field": change["field"],
            "old_value": change.get("old_value"),
            "new_value": change.get("new_value"),
            "evidence": change.get("evidence", {}),
            "confidence": change["confidence"],
            "source": change["source"],
        }
        if event is None:
            event = StateEvent(
                project_id=revision.project_id,
                chapter_revision_id=revision.id,
                chapter_sequence=revision.chapter_sequence,
                chapter_revision=revision.revision,
                event_key=event_key,
                **values,
            )
            db.add(event)
        else:
            for field, value in values.items():
                setattr(event, field, value)
        events.append(event)
    await db.flush()

    for event in events:
        if event.operation in {"delete", "resolve", "abandon"} or event.new_value is None:
            continue
        statement = insert(CurrentState).values(
            project_id=event.project_id,
            entity_type=event.entity_type,
            entity_key=event.entity_key,
            field=event.field,
            value=event.new_value,
            source_event_id=event.id,
            confidence=event.confidence,
            temperature="hot",
            last_chapter_sequence=event.chapter_sequence,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_current_state_field",
            set_={
                "value": statement.excluded.value,
                "source_event_id": statement.excluded.source_event_id,
                "confidence": statement.excluded.confidence,
                "temperature": "hot",
                "last_chapter_sequence": statement.excluded.last_chapter_sequence,
            },
        )
        await db.execute(statement)
    return events


async def rebuild_current_states(db: AsyncSession, project_id: Any) -> int:
    await db.execute(delete(CurrentState).where(CurrentState.project_id == project_id))
    events = list(
        (
            await db.scalars(
                select(StateEvent)
                .join(ChapterRevision, ChapterRevision.id == StateEvent.chapter_revision_id)
                .where(
                    StateEvent.project_id == project_id,
                    ChapterRevision.status == "published",
                )
                .order_by(
                    StateEvent.chapter_sequence.asc(),
                    StateEvent.chapter_revision.asc(),
                    StateEvent.created_at.asc(),
                    StateEvent.id.asc(),
                )
            )
        ).all()
    )
    latest: dict[tuple[str, str, str], StateEvent] = {}
    for event in events:
        key = (event.entity_type, event.entity_key, event.field)
        if event.operation in {"delete", "resolve", "abandon"} or event.new_value is None:
            latest.pop(key, None)
        else:
            latest[key] = event
    state_value_texts: list[str] = []
    for event in latest.values():
        normalized = (
            (event.new_value or {}).get("text")
            or event.new_value.get("summary")
            or json.dumps(event.new_value, ensure_ascii=False)
        )
        state_value_texts.append(f"{event.entity_key} {event.field}: {normalized}")
    if state_value_texts and embedding_configured():
        try:
            embeddings = await embed_texts(state_value_texts)
        except Exception:
            embeddings = [None] * len(state_value_texts)
    else:
        embeddings = [None] * len(state_value_texts)
    settings = get_settings()
    for event, emb in zip(latest.values(), embeddings, strict=True):
        db.add(
            CurrentState(
                project_id=event.project_id,
                entity_type=event.entity_type,
                entity_key=event.entity_key,
                field=event.field,
                value=event.new_value,
                source_event_id=event.id,
                confidence=event.confidence,
                temperature="hot",
                last_chapter_sequence=event.chapter_sequence,
                embedding=emb,
                embedding_model=settings.embedding_model if emb else None,
                embedding_dimensions=settings.embedding_dimensions if emb else None,
            )
        )
    await db.flush()
    return len(latest)
