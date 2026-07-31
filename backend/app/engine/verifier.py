from __future__ import annotations

from typing import Any


def verify_changes(observer_changes: dict[str, Any]) -> dict[str, Any]:
    changes = observer_changes.copy()
    for change in changes.get("changes", {}).get("character_state", []):
        change["confidence"] = max(change.get("confidence", 0.5), 0.9)
    return changes
