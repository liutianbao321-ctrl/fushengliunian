from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.changes import merge_extractions
from app.engine.runtime import run_agent_node
from app.models import ImportedChapter, ImportedWork, NarrativeDna, WorkCodexEntry
from app.services.llm_client import llm_client
from app.config import get_settings
from app.utils.canonical import parse_json_object


def split_chapters(raw_text: str) -> list[dict[str, str]]:
    """Split raw novel text into chapters by common Chinese chapter heading patterns."""
    # Match patterns like: 第一章, 第1章, 第001章, Chapter 1, etc.
    pattern = r'(?:^|\n)\s*(第[零一二三四五六七八九十百千万\d]+[章节回][\s：:]*[^\n]*)'
    splits = re.split(pattern, raw_text)

    chapters = []
    if len(splits) < 2:
        # No chapter headings found - split by length (roughly 3000 chars each)
        chunk_size = 3000
        for i in range(0, len(raw_text), chunk_size):
            chapters.append({
                "title": f"第{len(chapters) + 1}章",
                "content": raw_text[i:i + chunk_size].strip(),
            })
        return chapters if chapters else [{"title": "第1章", "content": raw_text.strip()}]

    # First element is text before any chapter heading (prologue or empty)
    if splits[0].strip():
        chapters.append({"title": "序章", "content": splits[0].strip()})

    # Pair up title + content
    for i in range(1, len(splits), 2):
        title = splits[i].strip()
        content = splits[i + 1].strip() if i + 1 < len(splits) else ""
        if content:
            chapters.append({"title": title, "content": content})

    return chapters


async def analyze_chapter(
    work_id: str,
    chapter_seq: int,
    chapter_content: str,
    chapter_title: str,
    context_summary: str,
) -> dict[str, Any]:
    """Run 3 observers + verifier on a single imported chapter."""
    payload = {
        "context_pack": {
            "schema_version": "import-analysis.v1",
            "chapter_sequence": chapter_seq,
            "chapter_title": chapter_title,
            "content": chapter_content,
            "preceding_summary": context_summary,
        },
        "beat_sheet": {},
        "content": chapter_content,
        "summary": "",
    }

    thread_prefix = f"import-{work_id}-{chapter_seq}"

    # Run 3 observers in parallel
    results = await asyncio.gather(
        run_agent_node("observer-social", payload, f"{thread_prefix}-social"),
        run_agent_node("observer-environment", payload, f"{thread_prefix}-env"),
        run_agent_node("observer-narrative", payload, f"{thread_prefix}-narrative"),
        return_exceptions=True,
    )

    extractions = []
    for r in results:
        if isinstance(r, Exception):
            extractions.append({"changes": {}})
        else:
            extractions.append(r)

    # Verify
    try:
        verifier = await run_agent_node(
            "novel-verifier",
            {**payload, "observer_extractions": extractions},
            f"{thread_prefix}-verify",
        )
    except Exception:
        verifier = {"changes": {}, "omissions": [], "conflicts": []}

    merged, _ = merge_extractions(extractions, verifier)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in merged:
        dim = item.get("dimension", "unknown")
        grouped.setdefault(dim, []).append(item)
    return grouped


async def analyze_style(chapters_sample: list[str]) -> dict[str, Any]:
    """Extract style fingerprint from sample chapters using LLM."""
    combined = "\n\n---\n\n".join(chapters_sample[:5])
    prompt = (
        "分析以下小说文本的写作风格，输出 JSON：\n"
        '{"sentence_length_avg": number, "dialogue_ratio": number (0-1), '
        '"description_ratio": number (0-1), "pov_style": "第一人称"|"第三人称"|"全知", '
        '"tone_keywords": [string], "rhythm": "快"|"中"|"慢"|"多变", '
        '"emotional_density": "高"|"中"|"低", '
        '"signature_patterns": [string], '
        '"sample_passages": [string]}\n\n'
        f"文本：\n{combined[:8000]}"
    )
    try:
        raw = await llm_client.complete("你是一个小说文风分析专家。", prompt, "json")
        return json.loads(raw)
    except Exception:
        return {}


async def analyze_breakpoint(
    last_chapters: list[str],
    wiki_summary: str,
    foreshadowing_list: list[dict],
) -> dict[str, Any]:
    """Analyze where a novel stopped and suggest continuation directions."""
    last_text = "\n\n---\n\n".join(last_chapters[-5:])
    foreshadow_text = "\n".join(
        f"- {f.get('content', '')} (埋于第{f.get('planted_chapter', '?')}章, 重要度{f.get('importance', '?')})"
        for f in foreshadowing_list
    )

    prompt = (
        "分析这本断更小说的断点，输出 JSON：\n"
        '{"breakpoint_chapter": number, "main_arc_stage": string, '
        '"unresolved_mysteries": [{"content": string, "planted_chapter": number, "importance": "A"|"B"|"C"}], '
        '"suggested_directions": [{"strategy": string, "description": string, '
        '"first_chapter_hook": string, "estimated_remaining_chapters": number}], '
        '"discontinuation_guess": string}\n\n'
        f"最后几章内容：\n{last_text[:6000]}\n\n"
        f"世界观摘要：\n{wiki_summary[:2000]}\n\n"
        f"未收伏笔：\n{foreshadow_text[:2000]}"
    )
    try:
        raw = await llm_client.complete("你是一个资深小说编辑，擅长分析小说结构。", prompt, "json")
        return json.loads(raw)
    except Exception:
        return {}


def build_analysis_batches(
    chapters: list[ImportedChapter],
    *,
    max_characters: int,
    max_chapters: int,
) -> list[list[ImportedChapter]]:
    """Group complete chapters into model-sized windows without cutting chapter text."""
    batches: list[list[ImportedChapter]] = []
    current: list[ImportedChapter] = []
    current_characters = 0
    for chapter in chapters:
        chapter_characters = len(chapter.content) + len(chapter.title or "") + 32
        if current and (
            current_characters + chapter_characters > max_characters
            or len(current) >= max_chapters
        ):
            batches.append(current)
            current = []
            current_characters = 0
        current.append(chapter)
        current_characters += chapter_characters
    if current:
        batches.append(current)
    return batches


def _fallback_chapter_summary(content: str) -> str:
    compact = re.sub(r"\s+", "", content)
    if len(compact) <= 120:
        return compact
    return f"{compact[:70]}……{compact[-40:]}"


async def analyze_chapter_batch(work_id: str, batch: list[ImportedChapter]) -> dict[str, Any]:
    """Extract all reusable facts from one large, chapter-aligned reading window."""
    start = batch[0].chapter_sequence
    end = batch[-1].chapter_sequence
    text = "\n\n".join(
        f"### 第{chapter.chapter_sequence}章 {chapter.title or ''}\n{chapter.content}"
        for chapter in batch
    )
    prompt = (
        f"作品批次：第{start}章至第{end}章。以下原文必须作为一个连续阅读窗口分析。\n\n"
        f"{text}\n\n"
        "只输出一个完整JSON对象。不要逐段点评，不要复述原文，不确定就留空。"
        "chapter_summaries必须覆盖输入中的每一章，每章只用一句不超过70字的话说明人物行动、阻力和结果。"
        "人物只提取本批有明确证据的重要人物；世界规则必须写限制或代价；伏笔必须区分新埋、推进和回收。"
        "输出结构："
        '{"batch_summary":string,"chapter_summaries":[{"sequence":number,"summary":string}],'
        '"characters":[{"name":string,"role":string,"desire":string,"state_change":string,'
        '"relationship_change":string,"evidence_chapters":[number]}],'
        '"world_rules":[{"title":string,"content":string,"evidence_chapters":[number]}],'
        '"foreshadowing":[{"content":string,"action":"planted"|"advanced"|"resolved",'
        '"chapter":number,"importance":"A"|"B"|"C"}],'
        '"plot_progression":[{"chapter_range":[number,number],"goal":string,"change":string}],'
        '"style_signals":{"pov":string,"rhythm":string,"dialogue":string,"signature_patterns":[string]}}'
    )
    raw = await llm_client.complete(
        "你是长篇小说资料分析器。以事实证据为先，把连续原文压缩成可供续写检索的结构化资料。",
        prompt,
        "json",
        max_tokens=7000,
        temperature=0.1,
        timeout_seconds=240,
        request_attempts=2,
        stream=True,
    )
    result = parse_json_object(raw)
    result["batch_range"] = [start, end]
    result["work_id"] = work_id
    return result


def _merge_batch_analysis(results: list[dict[str, Any]]) -> dict[str, Any]:
    characters: dict[str, dict[str, Any]] = {}
    world_rules: dict[str, dict[str, Any]] = {}
    foreshadowing: dict[str, dict[str, Any]] = {}
    plot_progression: list[dict[str, Any]] = []
    batch_summaries: list[dict[str, Any]] = []

    for result in sorted(results, key=lambda item: (item.get("batch_range") or [0])[0]):
        batch_range = result.get("batch_range") or []
        batch_summaries.append({"chapter_range": batch_range, "summary": str(result.get("batch_summary") or "")})
        for item in result.get("characters") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            slug = name.lower().replace(" ", "-")
            current = characters.setdefault(
                slug,
                {"slug": slug, "title": name, "content": "", "category": "character", "evidence_chapters": []},
            )
            facts = [
                str(item.get(field) or "").strip()
                for field in ("role", "desire", "state_change", "relationship_change")
            ]
            additions = [fact for fact in facts if fact and fact not in current["content"]]
            if additions:
                current["content"] = "\n".join(filter(None, [current["content"], *additions]))[-6000:]
            current["evidence_chapters"] = sorted(set(
                current["evidence_chapters"] + [
                    int(value) for value in (item.get("evidence_chapters") or [])
                    if isinstance(value, int)
                ]
            ))[-40:]

        for item in result.get("world_rules") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            content = str(item.get("content") or "").strip()
            if not title or not content:
                continue
            slug = title.lower().replace(" ", "-")
            current = world_rules.setdefault(
                slug,
                {"slug": slug, "title": title, "content": "", "category": "worldview", "evidence_chapters": []},
            )
            if content not in current["content"]:
                current["content"] = "\n".join(filter(None, [current["content"], content]))[-6000:]
            current["evidence_chapters"] = sorted(set(
                current["evidence_chapters"] + [
                    int(value) for value in (item.get("evidence_chapters") or [])
                    if isinstance(value, int)
                ]
            ))[-40:]

        for item in result.get("foreshadowing") or []:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            key = re.sub(r"\s+", "", content)[:160]
            chapter = item.get("chapter") if isinstance(item.get("chapter"), int) else 0
            action = str(item.get("action") or "advanced")
            current = foreshadowing.get(key)
            if current is None:
                foreshadowing[key] = {
                    "content": content,
                    "planted_chapter": chapter,
                    "last_chapter": chapter,
                    "status": "resolved" if action == "resolved" else "open",
                    "importance": item.get("importance") or "B",
                }
            else:
                current["last_chapter"] = max(int(current.get("last_chapter") or 0), chapter)
                if action == "resolved":
                    current["status"] = "resolved"

        plot_progression.extend(
            item for item in (result.get("plot_progression") or []) if isinstance(item, dict)
        )

    return {
        "characters": list(characters.values()),
        "world_rules": list(world_rules.values()),
        "foreshadowing": list(foreshadowing.values()),
        "plot_progression": plot_progression,
        "batch_summaries": batch_summaries,
    }


async def run_full_analysis(db: AsyncSession, work: ImportedWork) -> None:
    """Analyze every character once in large parallel windows, then build global indexes."""
    chapters = list(
        (await db.scalars(
            select(ImportedChapter)
            .where(ImportedChapter.work_id == work.id)
            .order_by(ImportedChapter.chapter_sequence)
        )).all()
    )

    if not chapters:
        work.analysis_status = "failed"
        await db.commit()
        return

    work.analysis_status = "analyzing"
    work.total_chapters = len(chapters)
    work.total_words = sum(ch.word_count for ch in chapters)
    work.analysis_progress = 2.0
    for chapter in chapters:
        chapter.analysis_status = "pending"
    await db.commit()

    settings = get_settings()
    batches = build_analysis_batches(
        chapters,
        max_characters=settings.import_analysis_batch_characters,
        max_chapters=settings.import_analysis_batch_chapters,
    )
    semaphore = asyncio.Semaphore(settings.import_analysis_concurrency)

    async def analyze_one(index: int, batch: list[ImportedChapter]) -> tuple[int, list[ImportedChapter], dict[str, Any] | Exception]:
        async with semaphore:
            try:
                result = await analyze_chapter_batch(str(work.id), batch)
                return index, batch, result
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                return index, batch, exc

    tasks = [
        asyncio.create_task(analyze_one(index, batch), name=f"import-batch-{work.id}-{index}")
        for index, batch in enumerate(batches, start=1)
    ]
    batch_results: list[dict[str, Any]] = []
    failed_batches: list[dict[str, Any]] = []
    completed_batches = 0
    try:
        for future in asyncio.as_completed(tasks):
            index, batch, result = await future
            completed_batches += 1
            if isinstance(result, Exception):
                failed_batches.append({
                    "batch": index,
                    "chapter_range": [batch[0].chapter_sequence, batch[-1].chapter_sequence],
                    "error": type(result).__name__,
                })
                for chapter in batch:
                    chapter.analysis_status = "failed"
                    if not chapter.summary:
                        chapter.summary = _fallback_chapter_summary(chapter.content)
            else:
                batch_results.append(result)
                summaries = {
                    int(item.get("sequence")): str(item.get("summary") or "").strip()
                    for item in (result.get("chapter_summaries") or [])
                    if isinstance(item, dict) and isinstance(item.get("sequence"), int)
                }
                for chapter in batch:
                    chapter.summary = summaries.get(chapter.chapter_sequence) or _fallback_chapter_summary(chapter.content)
                    chapter.analysis_status = "completed"
            work.analysis_progress = round(5 + 80 * completed_batches / max(len(batches), 1), 2)
            await db.commit()
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    if not batch_results:
        raise RuntimeError("所有原文批次都未能完成分析")

    extracted = _merge_batch_analysis(batch_results)
    successful_ranges = {
        tuple(result.get("batch_range") or []) for result in batch_results
    }
    covered_characters = sum(
        len(chapter.content)
        for batch in batches
        if (batch[0].chapter_sequence, batch[-1].chapter_sequence) in successful_ranges
        for chapter in batch
    )
    extracted["analysis_meta"] = {
        "pipeline": "parallel-large-window.v2",
        "batch_characters": settings.import_analysis_batch_characters,
        "batch_count": len(batches),
        "successful_batches": len(batch_results),
        "failed_batches": failed_batches,
        "source_coverage": round(covered_characters / max(work.total_words, 1), 4),
    }
    work.extracted_data = extracted
    work.analysis_progress = 88.0
    await db.commit()

    context_summary = " ".join(
        str(item.get("summary") or "") for item in extracted.get("batch_summaries", [])
    )[-12000:]
    foreshadowing_list = list(extracted.get("foreshadowing", []))

    # Style analysis
    sample_indexes = sorted(set([0, len(chapters) // 4, len(chapters) // 2, len(chapters) * 3 // 4, len(chapters) - 1]))
    sample_contents = [chapters[index].content for index in sample_indexes]
    style = await analyze_style(sample_contents)
    work.style_profile = style
    work.analysis_progress = 92.0
    await db.commit()

    # Genre detection
    genre_prompt = (
        f"根据以下小说简要信息，判断其类型和子类型，输出JSON：\n"
        f'{{"genre": string, "sub_genre": string}}\n\n'
        f"书名：{work.title}\n"
        f"首章：{chapters[0].content[:1000]}"
    )
    try:
        genre_raw = await llm_client.complete("判断小说类型。", genre_prompt, "json")
        genre_data = json.loads(genre_raw)
        work.genre = genre_data.get("genre")
        work.sub_genre = genre_data.get("sub_genre")
    except Exception:
        pass
    work.analysis_progress = 95.0
    await db.commit()

    last_contents = [ch.content for ch in chapters[-5:]]
    breakpoint = await analyze_breakpoint(last_contents, context_summary, foreshadowing_list)
    work.breakpoint_analysis = breakpoint
    work.analysis_progress = 98.0
    await db.commit()

    await _rebuild_work_codex(db, work, chapters)

    work.analysis_status = "completed"
    work.analysis_progress = 100.0
    await db.commit()


async def _rebuild_work_codex(db: AsyncSession, work: ImportedWork, chapters: list[ImportedChapter]) -> None:
    """Compile analysis output into four explicit, user-verifiable knowledge layers."""
    await db.execute(delete(WorkCodexEntry).where(WorkCodexEntry.imported_work_id == work.id))
    extracted = work.extracted_data or {}
    for kind, items in (
        ("character", extracted.get("characters", [])),
        ("world_rule", extracted.get("world_rules", [])),
        ("foreshadowing", extracted.get("foreshadowing", [])),
    ):
        for item in items:
            if isinstance(item, dict):
                db.add(
                    WorkCodexEntry(
                        imported_work_id=work.id,
                        layer="fact",
                        kind=kind,
                        title=str(item.get("title") or item.get("content") or kind)[:300],
                        content=item,
                        confidence=float(item.get("confidence", 0.8)),
                    )
                )
    for chapter in chapters:
        db.add(
            WorkCodexEntry(
                imported_work_id=work.id,
                layer="narrative",
                kind="chapter_summary",
                title=chapter.title or f"第{chapter.chapter_sequence}章",
                content={"sequence": chapter.chapter_sequence, "summary": chapter.summary},
                confidence=1.0 if chapter.summary else 0.5,
                source_chapter_ids=[chapter.id],
            )
        )
    if work.style_profile:
        db.add(
            WorkCodexEntry(
                imported_work_id=work.id,
                layer="style",
                kind="style_profile",
                title="全书文风指纹",
                content=work.style_profile,
                confidence=0.85,
            )
        )

    counts = [chapter.word_count for chapter in chapters]
    quote_chars = sum(ch.content.count("“") + ch.content.count('"') for ch in chapters)
    total_chars = max(1, sum(counts))
    pacing_stats = {
        "average_chapter_words": round(sum(counts) / max(1, len(counts))),
        "min_chapter_words": min(counts, default=0),
        "max_chapter_words": max(counts, default=0),
        "dialogue_marker_density": round(quote_chars / total_chars, 4),
    }
    dna = await db.scalar(select(NarrativeDna).where(NarrativeDna.imported_work_id == work.id))
    style = work.style_profile or {}
    if dna is None:
        dna = NarrativeDna(imported_work_id=work.id)
        db.add(dna)
    dna.hook_patterns = style.get("hook_mix", {}) if isinstance(style.get("hook_mix", {}), dict) else {}
    dna.pacing_stats = pacing_stats
    dna.pov_habits = str(style.get("pov_style") or "")
    dna.escalation_curve = str((work.breakpoint_analysis or {}).get("main_arc_stage") or "")
    dna.summary = "；".join(str(value) for value in style.get("signature_patterns", [])[:8])
    db.add(
        WorkCodexEntry(
            imported_work_id=work.id,
            layer="dna",
            kind="narrative_dna",
            title="叙事基因卡",
            content={
                "hook_patterns": dna.hook_patterns,
                "pacing_stats": pacing_stats,
                "pov_habits": dna.pov_habits,
                "escalation_curve": dna.escalation_curve,
                "summary": dna.summary,
            },
            confidence=0.8,
        )
    )
