from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

# 本地执行的节点：SKILL.md 存在但没有对应的 LLM 调用路径，保持同步仅为文档
_LOCAL_ONLY = {"world-simulator", "novel-architect", "novel-guardian", "novel-humanizer"}


@lru_cache(maxsize=32)
def load_skill_prompt(skill_name: str) -> str:
    """读取 backend/skills/<name>/SKILL.md，去掉 frontmatter，作为 system prompt。"""
    if skill_name in _LOCAL_ONLY:
        return ""
    path = SKILLS_DIR / skill_name / "SKILL.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    # 去掉 YAML frontmatter
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    return text.strip()
