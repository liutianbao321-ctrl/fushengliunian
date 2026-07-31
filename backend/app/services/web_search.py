from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_MARKDOWN_LINK = re.compile(r"\[([^\]]{1,300})\]\((https?://[^\s)]+)\)")
_PLAIN_URL = re.compile(r"https?://[^\s\]\[<>()\"']+")


class WebSearchUnavailable(RuntimeError):
    """The optional external research provider is unavailable."""


def web_search_configured(settings: Settings | None = None) -> bool:
    value = settings or get_settings()
    return bool(
        value.web_search_enabled
        and value.web_search_base_url
        and value.web_search_api_key
        and value.web_search_mcp_url
    )


def _safe_url(value: Any) -> str | None:
    url = str(value or "").strip().rstrip(".,;，。；")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url[:2000]


def _walk_values(value: Any):
    yield value
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_values(nested)
    elif isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            yield from _walk_values(json.loads(value))
        except json.JSONDecodeError:
            pass


def _response_text(payload: dict[str, Any]) -> str:
    direct = str(payload.get("output_text") or "").strip()
    if direct:
        return direct
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict):
                text = str(content.get("text") or content.get("output_text") or "").strip()
                if text:
                    parts.append(text)
    return "\n".join(parts).strip()


def _response_sources(payload: dict[str, Any], limit: int) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for value in _walk_values(payload):
        if isinstance(value, dict):
            url = _safe_url(value.get("url") or value.get("link") or value.get("source_url"))
            if url:
                candidates.append({
                    "title": str(value.get("title") or value.get("name") or urlparse(url).netloc)[:300],
                    "url": url,
                    "snippet": str(value.get("snippet") or value.get("summary") or "")[:1000],
                })
        elif isinstance(value, str):
            for title, raw_url in _MARKDOWN_LINK.findall(value):
                if url := _safe_url(raw_url):
                    candidates.append({"title": title.strip()[:300] or urlparse(url).netloc, "url": url, "snippet": ""})
            for raw_url in _PLAIN_URL.findall(value):
                if url := _safe_url(raw_url):
                    candidates.append({"title": urlparse(url).netloc, "url": url, "snippet": ""})
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in candidates:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        result.append(item)
        if len(result) >= limit:
            break
    return result


def parse_research_response(payload: dict[str, Any], *, max_sources: int = 8) -> dict[str, Any]:
    error = payload.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise WebSearchUnavailable(f"联网研究服务返回错误：{message or 'unknown'}")
    if payload.get("status") not in {None, "completed"}:
        raise WebSearchUnavailable(f"联网研究没有完成：{payload.get('status')}")
    memo = _response_text(payload)
    if not memo:
        raise WebSearchUnavailable("联网研究没有返回可用摘要")
    return {
        "status": "completed",
        "memo": memo[:12_000],
        "sources": _response_sources(payload, max_sources),
        "warning": None,
    }


def _source_digest(sources: list[dict[str, str]]) -> str:
    lines = [
        "本次联网检索返回了以下可核对资料。生成故事时仅将其作为外部事实线索，具体结论仍需以原文为准："
    ]
    for item in sources:
        detail = item.get("snippet") or "检索结果未提供摘要，请打开来源核对。"
        lines.append(f"- {item['title']}：{detail}（{item['url']}）")
    return "\n".join(lines)[:12_000]


def _research_query(idea_payload: dict[str, Any], synthesis: dict[str, Any]) -> str:
    pillars = synthesis.get("pillars") if synthesis.get("kind") == "pillar_synthesis" else [synthesis]
    pillar_lines = []
    for item in pillars or []:
        if not isinstance(item, dict):
            continue
        pillar_lines.append(f"- {item.get('title') or ''}：{str(item.get('logline') or '')[:300]}")
    return (
        f"小说题材：{str(idea_payload.get('idea') or '')[:1500]}\n"
        f"类型：{idea_payload.get('genres') or idea_payload.get('genre') or '未限定'}\n"
        f"创作支柱：\n{'\n'.join(pillar_lines)}\n"
        "请搜索其中最关键的两类现实事实：职业/制度流程，以及地域/历史/技术细节。"
        "优先中国政府、专业机构和主流媒体来源，不要搜索其他小说。"
    )[:4000]


async def _summarize_sources(
    client: httpx.AsyncClient,
    config: Settings,
    query: str,
    sources: list[dict[str, str]],
) -> str:
    response = await client.post(
        f"{str(config.web_search_base_url).rstrip('/')}/responses",
        headers={"Authorization": f"Bearer {config.web_search_api_key}"},
        json={
            "model": config.web_search_model,
            "instructions": (
                "你是小说事实研究编辑。仅根据给出的检索来源整理中文备忘录，不得补造资料。"
                "分为：可用事实、容易写错、可转化的场景细节、仍需作者决定。每项保留来源 URL，"
                "并明确这些资料不是本书 Canon。"
            ),
            "input": json.dumps({"research_question": query, "sources": sources}, ensure_ascii=False),
            "max_output_tokens": 1400,
        },
    )
    response.raise_for_status()
    payload = response.json()
    memo = _response_text(payload)
    if payload.get("error") or not memo:
        raise WebSearchUnavailable("联网资料整理没有返回可用摘要")
    return memo[:12_000]


async def research_story_material(
    idea_payload: dict[str, Any], synthesis: dict[str, Any], *, settings: Settings | None = None
) -> dict[str, Any]:
    config = settings or get_settings()
    if not web_search_configured(config):
        raise WebSearchUnavailable("联网研究尚未配置")
    query = _research_query(idea_payload, synthesis)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(config.web_search_timeout_seconds, connect=20)) as client:
            response = await client.post(
                config.web_search_mcp_url,
                headers={
                    "Authorization": f"Bearer {config.web_search_api_key}",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": "story-research",
                    "method": "tools/call",
                    "params": {
                        "name": "bailian_web_search",
                        "arguments": {"query": query, "count": config.web_search_max_sources},
                    },
                },
            )
            response.raise_for_status()
            response_payload = response.json()
            rpc_error = response_payload.get("error")
            rpc_result = response_payload.get("result") or {}
            if rpc_error or rpc_result.get("isError"):
                raise WebSearchUnavailable("联网搜索工具返回错误")
            sources = _response_sources(response_payload, config.web_search_max_sources)
            if not sources:
                raise WebSearchUnavailable("联网搜索没有返回可用来源")
            try:
                memo = await _summarize_sources(client, config, query, sources)
            except (httpx.HTTPError, ValueError, json.JSONDecodeError, WebSearchUnavailable) as summary_exc:
                logger.warning(
                    "[web-research] source summarization unavailable (%s): %s",
                    type(summary_exc).__name__,
                    summary_exc,
                )
                memo = _source_digest(sources)
            result = {
                "status": "completed",
                "memo": memo,
                "sources": sources,
                "warning": None,
            }
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("[web-research] provider unavailable (%s): %s", type(exc).__name__, exc)
        raise WebSearchUnavailable("联网研究服务暂时不可用") from exc
    result["query"] = query[:4000]
    return result
