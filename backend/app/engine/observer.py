from __future__ import annotations

from typing import Any


def extract_changes(project_title: str, protagonist: str, chapter_sequence: int, chapter_title: str) -> dict[str, Any]:
    return {
        "chapter_id": chapter_sequence,
        "changes": {
            "character_state": [
                {
                    "name": protagonist,
                    "field": "心境",
                    "old": "上一章余波",
                    "new": f"在《{chapter_title}》后获得新的行动决心",
                    "confidence": 0.9,
                    "evidence": "章节终点的情绪落点",
                }
            ],
            "foreshadowing": [
                {
                    "action": "plant",
                    "content": f"{project_title} 第{chapter_sequence}章留下的新异常线索",
                    "target_chapter": min(chapter_sequence + 12, chapter_sequence + 30),
                }
            ],
            "time_advance": {"amount": "半日", "current": f"故事推进至第{chapter_sequence}章结束"},
        },
    }
