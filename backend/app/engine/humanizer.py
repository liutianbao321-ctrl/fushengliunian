from __future__ import annotations

import re
from statistics import mean, pstdev

from app.config import get_settings
from app.services.llm_client import llm_client

STRUCTURE_FINGERPRINTS = ["首先", "其次", "最后", "因此", "然而", "不过", "总之", "由此可见"]


async def humanize_text(text: str, context_pack: dict | None = None) -> tuple[str, dict]:
    """LLM 润色节点：输入草稿与（可选的）风格上下文，输出更自然、更像真人写的润色稿。

    保留原函数契约（text -> (content, metrics)），内部改为调用 LLM 改写，
    不再使用机械删词表（整词删除会留下残句、破坏语法，反而制造 AI 味）。
    """
    polished = await _llm_polish(text, context_pack)
    source_length = len("".join(text.split()))
    polished_length = len("".join(str(polished or "").split()))
    if not polished or not polished.strip() or (source_length >= 1000 and polished_length < source_length * 0.85):
        polished = text
    return polished, calculate_anti_ai_scores(polished)


async def _llm_polish(text: str, context_pack: dict | None = None) -> str:
    settings = get_settings()
    # mock 模式无真实模型，原样返回以保证测试稳定
    if settings.llm_backend == "mock":
        return text
    style_hint = ""
    if isinstance(context_pack, dict):
        contract = (context_pack.get("style_profile") or {}).get("writing_contract")
        if isinstance(contract, dict):
            style_hint = "本书写作合同要点：" + "；".join(str(v) for v in contract.values() if v)[:200]
    system_prompt = (
        "你是有经验的文字润色编辑。下面是一段 AI 初稿，请在不改变事实、情节、"
        "人物与对话内容的前提下，把它改写得更有真人小说的自然感：\n"
        "- 去掉论文腔、模板化过渡词与抽象情绪标签；\n"
        "- 用动作、感官与潜台词替代直白解释；\n"
        "- 长短句服务于场景压力，避免连续排比与强行升华；\n"
        "- 保留所有专有名词、对话与情节，不要删改事件。\n"
        "- 保持原稿完整长度，改写后不得少于原稿的90%；不要把场景压缩成摘要。\n"
        "直接输出润色后的纯文本，不要输出 JSON、代码块或任何说明。"
        + (f"\n\n风格参考：{style_hint}" if style_hint else "")
    )
    raw = await llm_client.complete(
        system_prompt,
        text,
        response_format="text",
        stream=True,
        max_tokens=settings.generation_max_tokens_prose,
        temperature=0.85,
    )
    return raw.strip()


def calculate_anti_ai_scores(text: str) -> dict:
    sentences = [segment.strip() for segment in re.split(r"[。！？!?]\s*", text) if segment.strip()]
    sentence_lengths = [len(sentence) for sentence in sentences] or [1]
    burstiness = (pstdev(sentence_lengths) / mean(sentence_lengths)) if len(sentence_lengths) > 1 else 0.0
    unique_chars = len(set(text))
    ttr = unique_chars / max(len(text), 1)

    functions = []
    for sentence in sentences:
        if "“" in sentence or "”" in sentence:
            functions.append("dialogue")
        elif any(token in sentence for token in ["想", "记得", "忽然明白", "意识到"]):
            functions.append("inner")
        elif any(token in sentence for token in ["走", "抬", "拔", "撞", "退", "扑"]):
            functions.append("action")
        else:
            functions.append("description")
    repeated = 0
    for index in range(1, len(functions)):
        if functions[index] == functions[index - 1]:
            repeated += 1
    semantic_repeat_ratio = repeated / max(len(functions) - 1, 1)
    structure_density = sum(text.count(token) for token in STRUCTURE_FINGERPRINTS) / max(len(text), 1)

    return {
        "burstiness": round(burstiness, 3),
        "ttr": round(ttr, 3),
        "semantic_repeat_ratio": round(semantic_repeat_ratio, 3),
        "structure_density": round(structure_density, 4),
    }
