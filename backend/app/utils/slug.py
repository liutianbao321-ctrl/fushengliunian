import re


def slugify(value: str) -> str:
    normalized = re.sub(r"\s+", "-", value.strip().lower())
    normalized = re.sub(r"[^a-z0-9\-\u4e00-\u9fff]", "", normalized)
    return normalized or "untitled"
