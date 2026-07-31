from app.engine.analyzer import _merge_batch_analysis, build_analysis_batches
from app.models import ImportedChapter


def _chapter(sequence: int, size: int) -> ImportedChapter:
    return ImportedChapter(
        chapter_sequence=sequence,
        title=f"第{sequence}章",
        content=str(sequence) * size,
        word_count=size,
    )


def test_analysis_batches_keep_chapters_whole_and_respect_limits() -> None:
    chapters = [_chapter(index, 1000) for index in range(1, 8)]

    batches = build_analysis_batches(chapters, max_characters=2600, max_chapters=3)

    assert [[chapter.chapter_sequence for chapter in batch] for batch in batches] == [
        [1, 2], [3, 4], [5, 6], [7],
    ]
    assert [chapter.chapter_sequence for batch in batches for chapter in batch] == list(range(1, 8))


def test_merge_batch_analysis_combines_cross_batch_evidence() -> None:
    merged = _merge_batch_analysis([
        {
            "batch_range": [1, 10],
            "batch_summary": "主角进入客栈。",
            "characters": [{
                "name": "陆景", "role": "掌柜", "desire": "守住客栈",
                "state_change": "负伤", "relationship_change": "", "evidence_chapters": [1, 8],
            }],
            "world_rules": [{"title": "店内禁斗", "content": "店内不能动武。", "evidence_chapters": [2]}],
            "foreshadowing": [{"content": "柜台下的血迹", "action": "planted", "chapter": 3, "importance": "A"}],
        },
        {
            "batch_range": [11, 20],
            "batch_summary": "主角追查血迹。",
            "characters": [{
                "name": "陆景", "role": "掌柜", "desire": "查清旧案",
                "state_change": "伤势好转", "relationship_change": "开始信任白晓晓", "evidence_chapters": [15],
            }],
            "world_rules": [{"title": "店内禁斗", "content": "违者会被客栈驱逐。", "evidence_chapters": [12]}],
            "foreshadowing": [{"content": "柜台下的血迹", "action": "resolved", "chapter": 18, "importance": "A"}],
        },
    ])

    character = merged["characters"][0]
    rule = merged["world_rules"][0]
    foreshadow = merged["foreshadowing"][0]
    assert character["evidence_chapters"] == [1, 8, 15]
    assert "守住客栈" in character["content"] and "查清旧案" in character["content"]
    assert "店内不能动武" in rule["content"] and "驱逐" in rule["content"]
    assert foreshadow["planted_chapter"] == 3
    assert foreshadow["last_chapter"] == 18
    assert foreshadow["status"] == "resolved"
