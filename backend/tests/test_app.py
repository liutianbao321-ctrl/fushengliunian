import pytest
from fastapi import FastAPI

from app.api.projects import _source_inheritance
from app.main import app
from app.schemas import CreationDirectionSelectRequest, ProjectCreate


def test_application_imports_with_all_routes() -> None:
    assert isinstance(app, FastAPI)
    paths = {route.path for route in app.routes}
    assert "/api/immersive/{session_id}" in paths
    assert "/api/imported-works/{work_id}" in paths
    assert "/api/imported-works/external-analysis-prompt" in paths
    assert "/api/imported-works/external-analysis" in paths
    assert "/api/imported-works/{work_id}/retry" in paths
    assert "/api/imported-works/{work_id}/codex" in paths
    assert "/api/imported-works/{work_id}/codex/{entry_id}" in paths
    assert "/api/projects/{project_id}/charter" in paths
    assert "/api/projects/{project_id}/volumes/{volume_sequence}/generate-plan" in paths
    assert "/api/projects/{project_id}/chapters/{chapter_sequence}/creation-brief" in paths
    assert "/api/projects/{project_id}/chapters/{chapter_sequence}/optimize-light" in paths
    assert "/api/projects/{project_id}/chapter-directory" in paths
    assert "/api/ai/creation-v2/foundation/start" in paths
    assert "/api/ai/creation-v2/foundation/{job_id}" in paths
    assert "/api/ai/creation-v2/pilot/start" in paths
    assert "/api/ai/creation-v2/pilot/task/{job_id}" in paths
    assert "/api/ai/creation-studio/sessions" in paths
    assert "/api/ai/creation-studio/sessions/{session_id}/direction" in paths
    assert "/api/ai/creation-studio/sessions/{session_id}/review" in paths
    assert "/api/ai/creation-studio/sessions/{session_id}/confirm" in paths


def _project_payload(**overrides) -> ProjectCreate:
    data = {
        "title": "测试新书",
        "genre": "玄幻",
        "one_sentence": "这是一个用于验证创建流程的长篇故事种子。",
        "protagonist_name": "陆景",
        "protagonist_gender": "男",
        "protagonist_personality": "谨慎但会主动承担代价",
        "target_words": 1_000_000,
    }
    data.update(overrides)
    return ProjectCreate(**data)


def test_project_create_accepts_super_long_target_words() -> None:
    payload = _project_payload(target_words=8_000_000)

    assert payload.target_words == 8_000_000


def test_creation_studio_combines_multiple_pillars() -> None:
    payload = CreationDirectionSelectRequest(selected_indices=[0, 1, 3], primary_index=1)

    assert payload.selected_indices == [0, 1, 3]
    assert payload.primary_index == 1


def test_creation_studio_rejects_a_single_pillar() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CreationDirectionSelectRequest(selected_indices=[0], primary_index=0)


def test_imported_source_inheritance_separates_fanfic_from_continuation() -> None:
    source_id = "11111111-1111-1111-1111-111111111111"

    continuation = _project_payload(
        creation_mode="continuation",
        source_work_id=source_id,
        intent_brief={"source_derivative": {"mode": "continuation"}},
    )
    fanfic = _project_payload(
        creation_mode="fanfic",
        source_work_id=source_id,
        intent_brief={"source_derivative": {"mode": "fanfic", "fanfic_type": "what_if"}},
    )
    fanfic_continuation = _project_payload(
        creation_mode="fanfic",
        source_work_id=source_id,
        intent_brief={"source_derivative": {"mode": "fanfic", "fanfic_type": "fanfic_continuation"}},
    )

    assert _source_inheritance(continuation) == (True, True)
    assert _source_inheritance(fanfic) == (True, False)
    assert _source_inheritance(fanfic_continuation) == (True, True)
