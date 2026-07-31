from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from json_repair import repair_json


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def payload_hash(value: Any) -> str:
    return sha256_text(canonical_json(value))


def parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型未返回 JSON 对象")
    candidate = text[start : end + 1]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        value = repair_json(candidate, return_objects=True)
    if not isinstance(value, dict):
        raise ValueError("模型返回值不是 JSON 对象")
    return value
