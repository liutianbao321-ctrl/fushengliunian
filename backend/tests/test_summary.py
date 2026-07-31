from types import SimpleNamespace

from app.engine.summary import (
    _join_milestones,
    _join_recent,
    _milestones,
    _trim_preserving_ends,
)


def test_join_recent_keeps_newest_summaries_in_story_order() -> None:
    summaries = ["第一章", "第二章", "第三章很长"]

    assert _join_recent(summaries, 10) == "第二章\n第三章很长"


def test_milestones_keep_first_last_and_evenly_spaced_history() -> None:
    items = [SimpleNamespace(chapter_sequence=index) for index in range(1, 22)]

    selected = _milestones(items)

    assert [item.chapter_sequence for item in selected] == [1, 6, 11, 16, 21]


def test_join_milestones_preserves_book_origin_and_newest_volumes() -> None:
    summaries = [f"第{index}卷-" + ("x" * 20) for index in range(1, 8)]

    result = _join_milestones(summaries, 80)

    assert "第1卷" in result
    assert "第7卷" in result
    assert len(result) <= 80


def test_long_range_trim_preserves_beginning_and_latest_consequence() -> None:
    value = "开篇承诺" + ("中段" * 200) + "最新不可逆后果"

    result = _trim_preserving_ends(value, 100)

    assert result.startswith("开篇承诺")
    assert result.endswith("最新不可逆后果")
    assert len(result) == 100
