from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMResponseError(RuntimeError):
    """The upstream request succeeded, but its response cannot be consumed."""


def _require_text(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, list):
        parts = [
            str(item.get("text") or "")
            for item in value
            if isinstance(item, dict) and item.get("type") in {None, "text"}
        ]
        joined = "".join(parts)
        if joined.strip():
            return joined
    raise LLMResponseError("模型返回了空内容")


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._provider_unavailable_until: dict[str, float] = {}

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: str = "text",
        *,
        stream: bool = False,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
        request_attempts: int | None = None,
    ) -> str:
        if self.settings.llm_backend == "mock":
            return self._mock_complete(system_prompt, user_prompt, response_format)

        if not self.settings.llm_base_url or not self.settings.llm_api_key:
            raise RuntimeError("LLM 服务配置不完整")

        primary_model = model or self.settings.llm_model
        models = [primary_model]
        # Explicit model selection means the caller owns provider routing. Several
        # planning flows already iterate candidates; nesting fallbacks here turned
        # one click into repeated multi-minute requests.
        if model is None:
            models.extend(self.settings.llm_fallback_models)
            if self.settings.llm_fallback_model:
                models.append(self.settings.llm_fallback_model)
            if self.settings.llm_deepseek_model:
                models.append(f"deepseek:{self.settings.llm_deepseek_model}")
            if self.settings.llm_aliyun_model:
                models.append(f"aliyun:{self.settings.llm_aliyun_model}")
        models = list(dict.fromkeys(candidate for candidate in models if candidate))
        # 温度由调用方按场景显式传入；未指定时结构化（JSON）用低温、纯文本用较高温兜底
        if temperature is None:
            temperature = 0.3 if response_format == "json" else 0.75
        payload: dict[str, Any] = {
            "model": primary_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if timeout_seconds is not None:
            payload["__timeout_seconds"] = max(float(timeout_seconds), 1.0)
        if request_attempts is not None:
            payload["__request_attempts"] = max(int(request_attempts), 1)
        last_error: Exception | None = None
        skipped_providers: set[str] = set()
        provider_circuit_enabled = bool(self.settings.llm_aliyun_model or self.settings.llm_deepseek_model)
        # 流式优先：长 JSON 生成耗时久，非流式易触发代理 503 超时。
        # 若模型不支持流式（HTTP 400），下方已有自动降级非流式逻辑。
        use_stream = bool(stream)
        for candidate in models:
            provider_key = ""
            try:
                candidate_model, base_url, api_key = self._resolve_candidate(candidate)
                provider_key = base_url.rstrip("/")
                if (
                    provider_circuit_enabled
                    and self._provider_unavailable_until.get(provider_key, 0) > time.monotonic()
                ):
                    logger.info("[llm_complete] 跳过熔断中的供应商: %s", provider_key)
                    skipped_providers.add(provider_key)
                    continue
                candidate_payload = {
                    **payload,
                    "model": candidate_model,
                    "__base_url": base_url,
                    "__api_key": api_key,
                }
                if use_stream:
                    try:
                        result = await self._stream_request(candidate_payload)
                        self._provider_unavailable_until.pop(provider_key, None)
                        return _require_text(result)
                    except LLMResponseError as stream_err:
                        # 某些模型（如 deepseek-v4-pro）不支持流式请求（HTTP 400），
                        # 自动降级为非流式重试，而非直接放弃该候选模型
                        err_msg = str(stream_err)
                        if "HTTP 400" in err_msg or "拒绝流式" in err_msg:
                            logger.warning("[llm_complete] 候选模型 %s 不支持流式，降级为非流式请求", candidate)
                            result = await self._request(candidate_payload)
                            self._provider_unavailable_until.pop(provider_key, None)
                            return _require_text(result)
                        raise
                    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
                        # 网络故障和 5xx 直接切换下一个供应商/模型，避免在同一故障端点重复等待。
                        raise
                else:
                    result = await self._request(candidate_payload)
                    self._provider_unavailable_until.pop(provider_key, None)
                    return _require_text(result)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, LLMResponseError) as exc:
                last_error = exc
                if (
                    provider_circuit_enabled
                    and provider_key
                    and (
                        isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500
                        or isinstance(exc, LLMResponseError) and any(
                            marker in str(exc) for marker in ("HTTP 401", "HTTP 403")
                        )
                    )
                ):
                    auth_failure = isinstance(exc, LLMResponseError) and any(
                        marker in str(exc) for marker in ("HTTP 401", "HTTP 403")
                    )
                    self._provider_unavailable_until[provider_key] = time.monotonic() + (300 if auth_failure else 45)
                logger.warning("[llm_complete] 候选模型 %s 失败: %s: %s", candidate, type(exc).__name__, exc)
        if last_error:
            attempted = "、".join(models)
            status_code = (
                last_error.response.status_code
                if isinstance(last_error, httpx.HTTPStatusError) and last_error.response is not None
                else None
            )
            suffix = f"（HTTP {status_code}）" if status_code else ""
            if isinstance(last_error, LLMResponseError):
                raise RuntimeError(f"模型返回不可用，已自动尝试：{attempted}") from last_error
            raise RuntimeError(f"模型服务暂时不可用{suffix}，已尝试：{attempted}") from last_error
        if skipped_providers:
            raise RuntimeError("模型供应商正在短暂熔断，请稍后重试；本次没有丢失已生成内容")
        raise RuntimeError("模型服务没有返回可用内容，请稍后重试")

    def _resolve_candidate(self, candidate: str) -> tuple[str, str, str]:
        if candidate.startswith("deepseek:"):
            if not self.settings.llm_deepseek_base_url or not self.settings.llm_deepseek_api_key:
                raise LLMResponseError("DeepSeek 文本模型配置不完整")
            return (
                candidate.removeprefix("deepseek:"),
                self.settings.llm_deepseek_base_url,
                self.settings.llm_deepseek_api_key,
            )
        if candidate.startswith("aliyun:"):
            if not self.settings.llm_aliyun_base_url or not self.settings.llm_aliyun_api_key:
                raise LLMResponseError("阿里云文本模型配置不完整")
            return (
                candidate.removeprefix("aliyun:"),
                self.settings.llm_aliyun_base_url,
                self.settings.llm_aliyun_api_key,
            )
        return candidate, self.settings.llm_base_url or "", self.settings.llm_api_key or ""

    async def _stream_request(self, payload: dict[str, Any]) -> str:
        """用 OpenAI SSE 流持续接收长正文，避免代理等待完整响应时 504。"""
        retryer = retry(
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
            stop=stop_after_attempt(int(payload.get("__request_attempts") or self.settings.llm_max_retries)),
            wait=wait_exponential(multiplier=2, min=3, max=30),
            reraise=True,
        )

        @retryer
        async def send() -> str:
            base_url = str(payload.get("__base_url") or "")
            api_key = str(payload.get("__api_key") or "")
            request_payload = {key: value for key, value in payload.items() if not key.startswith("__")}
            request_payload["stream"] = True
            timeout_seconds = float(payload.get("__timeout_seconds") or self.settings.llm_timeout_seconds)
            timeout = httpx.Timeout(timeout_seconds, connect=20)
            parts: list[str] = []
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=request_payload,
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        if response.status_code == 429 or response.status_code >= 500:
                            raise httpx.HTTPStatusError(
                                f"LLM 流式请求失败: HTTP {response.status_code}: {body}",
                                request=response.request,
                                response=response,
                            )
                        raise LLMResponseError(f"模型拒绝流式请求（HTTP {response.status_code}）")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if isinstance(content, str):
                            parts.append(content)
            if not parts:
                logger.error(
                    "[llm_stream] 流式响应无正文内容！model=%s, payload keys=%s",
                    request_payload.get("model"),
                    list(request_payload.keys()),
                )
                raise LLMResponseError("模型流式响应没有正文内容")
            result = "".join(parts)
            logger.debug("[llm_stream] 流式完成，model=%s, 总长度=%d", request_payload.get("model"), len(result))
            return result

        return await send()

    async def _request(self, payload: dict[str, Any]) -> str:
        retryer = retry(
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
            stop=stop_after_attempt(int(payload.get("__request_attempts") or self.settings.llm_max_retries)),
            wait=wait_exponential(multiplier=2, min=3, max=30),
            reraise=True,
        )

        @retryer
        async def send() -> str:
            base_url = str(payload.get("__base_url") or "")
            api_key = str(payload.get("__api_key") or "")
            request_payload = {key: value for key, value in payload.items() if not key.startswith("__")}
            timeout_seconds = float(payload.get("__timeout_seconds") or self.settings.llm_timeout_seconds)
            timeout = httpx.Timeout(timeout_seconds, connect=20)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=request_payload,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                if response.status_code >= 400:
                    raise LLMResponseError(f"模型拒绝请求（HTTP {response.status_code}）")
                try:
                    data = response.json()
                    choices = data.get("choices") or []
                    message = choices[0].get("message") if choices else None
                    if not isinstance(message, dict):
                        raise LLMResponseError("模型响应缺少 message")
                    return _require_text(message.get("content"))
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise LLMResponseError("模型响应格式不兼容") from exc

        return await send()

    def _mock_complete(self, system_prompt: str, user_prompt: str, response_format: str) -> str:
        return f"[MOCK:{response_format}] {system_prompt[:60]} :: {user_prompt[:240]}"

    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        """逐块产出 LLM 输出，供 SSE 端点实时转发给前端。"""
        if self.settings.llm_backend == "mock":
            yield self._mock_complete(system_prompt, user_prompt, "text")
            return
        if not self.settings.llm_base_url or not self.settings.llm_api_key:
            raise RuntimeError("LLM 服务配置不完整")

        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.6,
            "stream": True,
        }
        timeout = httpx.Timeout(self.settings.llm_timeout_seconds, connect=20)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                    raise RuntimeError(f"LLM 流式请求失败: HTTP {response.status_code}: {body}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield content


llm_client = LLMClient()
