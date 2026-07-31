from app.services.feedback import manuscript_diff


def test_manuscript_diff_records_bounded_author_changes() -> None:
    result = manuscript_diff("他推门进来。", "他在门外停了一会儿，才推门进来。")

    assert result["inserted_characters"] > 0
    assert result["change_ratio"] > 0
    assert result["edits"]
    assert result["edits"][0]["after_span"][1] > result["edits"][0]["after_span"][0]


def test_manuscript_diff_does_not_store_unbounded_passages() -> None:
    result = manuscript_diff("甲" * 800, "乙" * 800)

    assert len(result["edits"][0]["before"]) == 500
    assert len(result["edits"][0]["after"]) == 500
