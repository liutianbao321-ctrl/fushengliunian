from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import Settings
from app.services.web_search import (
    WebSearchUnavailable,
    parse_research_response,
    research_story_material,
    web_search_configured,
)


def web_settings(**overrides) -> Settings:
    values = {
        "web_search_base_url": "https://workspace.example/compatible-mode/v1",
        "web_search_api_key": "search-secret",
        "web_search_mcp_url": "https://workspace.example/api/v1/mcps/WebSearch/mcp",
        "web_search_model": "qwen3.6-plus",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_web_search_requires_the_complete_independent_configuration() -> None:
    assert web_search_configured(web_settings()) is True
    with pytest.raises(ValueError, match="BASE_URL、API_KEY 和 MCP_URL"):
        web_settings(web_search_api_key=None)


def test_research_response_extracts_and_deduplicates_sources() -> None:
    payload = {
        "status": "completed",
        "output": [
            {
                "type": "mcp_call",
                "output": '{"results":[{"title":"官方资料","url":"https://example.cn/a",'
                '"snippet":"可信摘要"}]}',
            },
            {
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": "研究结论。参考[官方资料](https://example.cn/a)和https://example.cn/b",
                }],
            },
        ],
    }

    result = parse_research_response(payload)

    assert result["memo"].startswith("研究结论")
    assert [item["url"] for item in result["sources"]] == [
        "https://example.cn/a",
        "https://example.cn/b",
    ]


@pytest.mark.asyncio
async def test_story_research_calls_mcp_then_summarizes_without_leaking_raw_payload(monkeypatch) -> None:
    search_response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://workspace.example/api/v1/mcps/WebSearch/mcp"),
        json={
            "jsonrpc": "2.0",
            "id": "story-research",
            "result": {"isError": False, "content": [{
                "type": "text",
                "text": '{"results":[{"title":"修复规范","url":"https://example.cn/clock",'
                '"snippet":"修复前应记录机芯编号。"}]}',
            }]},
        },
    )
    summary_response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://workspace.example/compatible-mode/v1/responses"),
        json={
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "钟表修复需要记录机芯编号。https://example.cn/clock"}],
            }],
        },
    )
    post = AsyncMock(side_effect=[search_response, summary_response])

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *args, **kwargs):
            return await post(*args, **kwargs)

    monkeypatch.setattr("app.services.web_search.httpx.AsyncClient", FakeClient)
    result = await research_story_material(
        {"idea": "修表师追查父亲失踪", "genres": ["都市"], "target_words": 1_000_000},
        {"kind": "pillar_synthesis", "pillars": []},
        settings=web_settings(),
    )

    assert result["status"] == "completed"
    assert result["sources"][0]["url"] == "https://example.cn/clock"
    assert post.await_count == 2
    search_call, summary_call = post.await_args_list
    assert search_call.args[0].endswith("/mcp")
    assert search_call.kwargs["json"]["method"] == "tools/call"
    assert search_call.kwargs["json"]["params"]["name"] == "bailian_web_search"
    assert summary_call.args[0].endswith("/responses")
    assert "tools" not in summary_call.kwargs["json"]


@pytest.mark.asyncio
async def test_story_research_keeps_source_digest_when_summarization_fails(monkeypatch) -> None:
    search_response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://workspace.example/compatible-mode/v1/responses"),
        json={
            "jsonrpc": "2.0",
            "id": "story-research",
            "result": {"isError": False, "content": [{
                "type": "text",
                "text": '{"results":[{"title":"应急规范","url":"https://example.cn/emergency",'
                '"snippet":"院前与院内需要完成标准化交接。"}]}',
            }]},
        },
    )
    summary_response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://workspace.example/compatible-mode/v1/responses"),
        json={
            "status": "completed",
            "output": [],
        },
    )
    post = AsyncMock(side_effect=[search_response, summary_response])

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *args, **kwargs):
            return await post(*args, **kwargs)

    monkeypatch.setattr("app.services.web_search.httpx.AsyncClient", FakeClient)
    result = await research_story_material(
        {"idea": "急诊医生参与灾害救援"},
        {"kind": "pillar_synthesis", "pillars": []},
        settings=web_settings(),
    )

    assert post.await_count == 2
    assert result["status"] == "completed"
    assert result["memo"].startswith("本次联网检索返回了以下可核对资料")
    assert result["sources"][0]["url"] == "https://example.cn/emergency"


@pytest.mark.asyncio
async def test_story_research_converts_provider_failures_to_recoverable_error(monkeypatch) -> None:
    class FailingClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.services.web_search.httpx.AsyncClient", FailingClient)

    with pytest.raises(WebSearchUnavailable, match="暂时不可用"):
        await research_story_material(
            {"idea": "现实职业故事"},
            {"kind": "pillar_synthesis", "pillars": []},
            settings=web_settings(),
        )
