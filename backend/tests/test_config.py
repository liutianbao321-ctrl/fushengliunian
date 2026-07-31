from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.llm_client import LLMClient


def production_settings(**overrides) -> Settings:
    values = {
        "env": "production",
        "secret_key": "a" * 48,
        "llm_backend": "openai_compatible",
        "llm_base_url": "https://llm.internal/v1",
        "llm_api_key": "k" * 32,
        "cors_origins": ["https://novel.example.com"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_rejects_mock_backend() -> None:
    with pytest.raises(ValidationError, match="LLM_BACKEND=mock"):
        production_settings(llm_backend="mock")


def test_production_rejects_default_secret() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        production_settings(secret_key="change-this-in-production")


def test_production_settings_accept_direct_llm() -> None:
    settings = production_settings(llm_model="deepseek-chat", llm_fallback_models=["qwen-plus", "deepseek-chat"])
    assert settings.llm_backend == "openai_compatible"
    assert settings.llm_base_url == "https://llm.internal/v1"
    assert settings.expected_schema_revision == "0013"
    assert settings.import_worker_enabled is True
    assert settings.llm_fallback_models == ["qwen-plus", "deepseek-chat"]


def test_embedding_configuration_requires_database_vector_dimensions() -> None:
    with pytest.raises(ValidationError, match="EMBEDDING_DIMENSIONS=1024"):
        Settings(_env_file=None, embedding_api_key="secret", embedding_dimensions=768)


def test_aliyun_embedding_configuration_is_supported() -> None:
    settings = Settings(
        _env_file=None,
        embedding_provider="aliyun_dashscope",
        embedding_api_key="secret",
        embedding_model="qwen3.7-text-embedding",
        embedding_dimensions=1024,
    )
    assert settings.embedding_provider == "aliyun_dashscope"


def test_web_search_configuration_is_independent_from_generation_model() -> None:
    settings = Settings(
        _env_file=None,
        web_search_base_url="https://workspace.example/compatible-mode/v1",
        web_search_api_key="web-key",
        web_search_mcp_url="https://workspace.example/api/v1/mcps/WebSearch/mcp",
    )

    assert settings.web_search_api_key == "web-key"
    assert settings.llm_aliyun_api_key is None


@pytest.mark.asyncio
async def test_llm_client_uses_ordered_fallback_models() -> None:
    client = LLMClient()
    client.settings = Settings(
        _env_file=None,
        llm_backend="openai_compatible",
        llm_base_url="https://llm.example/v1",
        llm_api_key="secret",
        llm_model="primary",
        llm_fallback_models=["backup-a", "backup-b", "backup-a"],
    )
    response = httpx.Response(503, request=httpx.Request("POST", "https://llm.example/v1/chat/completions"))
    client._request = AsyncMock(
        side_effect=[
            httpx.HTTPStatusError("unavailable", request=response.request, response=response),
            "fallback result",
        ]
    )

    result = await client.complete("system", "user")

    assert result == "fallback result"
    assert [call.args[0]["model"] for call in client._request.await_args_list] == ["primary", "backup-a"]


@pytest.mark.asyncio
async def test_llm_client_routes_to_independent_aliyun_provider() -> None:
    client = LLMClient()
    client.settings = Settings(
        _env_file=None,
        llm_backend="openai_compatible",
        llm_base_url="https://primary.example/v1",
        llm_api_key="primary-key",
        llm_model="primary",
        llm_aliyun_base_url="https://dashscope.example/v1",
        llm_aliyun_api_key="aliyun-key",
        llm_aliyun_model="qwen-plus",
    )
    response = httpx.Response(503, request=httpx.Request("POST", "https://primary.example/v1/chat/completions"))
    client._request = AsyncMock(
        side_effect=[
            httpx.HTTPStatusError("unavailable", request=response.request, response=response),
            "aliyun result",
        ]
    )

    result = await client.complete("system", "user")

    assert result == "aliyun result"
    first, second = [call.args[0] for call in client._request.await_args_list]
    assert first["model"] == "primary"
    assert second["model"] == "qwen-plus"
    assert second["__base_url"] == "https://dashscope.example/v1"
    assert second["__api_key"] == "aliyun-key"


@pytest.mark.asyncio
async def test_llm_client_routes_to_independent_deepseek_before_aliyun() -> None:
    client = LLMClient()
    client.settings = Settings(
        _env_file=None,
        llm_backend="openai_compatible",
        llm_base_url="https://primary.example/v1",
        llm_api_key="primary-key",
        llm_model="primary",
        llm_deepseek_base_url="https://api.deepseek.example",
        llm_deepseek_api_key="deepseek-key",
        llm_deepseek_model="deepseek-v4-pro",
        llm_aliyun_base_url="https://dashscope.example/v1",
        llm_aliyun_api_key="aliyun-key",
        llm_aliyun_model="qwen-plus",
    )
    response = httpx.Response(503, request=httpx.Request("POST", "https://primary.example/v1/chat/completions"))
    client._request = AsyncMock(
        side_effect=[
            httpx.HTTPStatusError("unavailable", request=response.request, response=response),
            "deepseek result",
        ]
    )

    assert await client.complete("system", "user") == "deepseek result"
    first, second = [call.args[0] for call in client._request.await_args_list]
    assert first["model"] == "primary"
    assert second["model"] == "deepseek-v4-pro"
    assert second["__base_url"] == "https://api.deepseek.example"


@pytest.mark.asyncio
async def test_llm_client_skips_other_models_on_an_open_provider_circuit() -> None:
    client = LLMClient()
    client.settings = Settings(
        _env_file=None,
        llm_backend="openai_compatible",
        llm_base_url="https://primary.example/v1",
        llm_api_key="primary-key",
        llm_model="primary-a",
        llm_fallback_models=["primary-b"],
        llm_aliyun_base_url="https://dashscope.example/v1",
        llm_aliyun_api_key="aliyun-key",
        llm_aliyun_model="qwen-plus",
    )
    response = httpx.Response(503, request=httpx.Request("POST", "https://primary.example/v1/chat/completions"))
    client._request = AsyncMock(
        side_effect=[
            httpx.HTTPStatusError("unavailable", request=response.request, response=response),
            "aliyun result",
        ]
    )

    assert await client.complete("system", "user") == "aliyun result"
    assert [call.args[0]["model"] for call in client._request.await_args_list] == ["primary-a", "qwen-plus"]


@pytest.mark.asyncio
async def test_llm_client_reports_when_every_provider_is_circuit_broken() -> None:
    import time

    client = LLMClient()
    client.settings = Settings(
        _env_file=None,
        llm_backend="openai_compatible",
        llm_base_url="https://primary.example/v1",
        llm_api_key="primary-key",
        llm_model="primary",
        llm_aliyun_base_url="https://dashscope.example/v1",
        llm_aliyun_api_key="aliyun-key",
        llm_aliyun_model="qwen-plus",
    )
    client._provider_unavailable_until = {
        "https://primary.example/v1": time.monotonic() + 30,
        "https://dashscope.example/v1": time.monotonic() + 30,
    }

    with pytest.raises(RuntimeError, match="短暂熔断"):
        await client.complete("system", "user")
