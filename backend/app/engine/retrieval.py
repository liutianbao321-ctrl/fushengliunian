from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    ChapterChunk,
    NovelToc,
    WritingKnowledgeChunk,
    WritingKnowledgeDocument,
    WritingMethodCard,
)


@dataclass(slots=True)
class RetrievalHit:
    chapter_sequence: int
    content: str
    score: float
    source: str


def embedding_configured(settings=None) -> bool:
    settings = settings or get_settings()
    return bool(
        settings.embedding_api_key
        and (settings.embedding_base_url or settings.embedding_provider == "aliyun_dashscope")
    )


def _infer_writing_tags(query: str) -> list[str]:
    aliases = {
        "人物": ("人物", "角色", "主角", "配角", "性格", "动机", "欲望"),
        "情节": ("情节", "冲突", "场景", "局势", "事件"),
        "对话": ("对话", "对白", "潜台词", "台词"),
        "节奏": ("节奏", "张弛", "放慢", "压缩", "详略"),
        "伏笔": ("伏笔", "暗示", "埋设", "回收"),
        "大纲": ("大纲", "章纲", "卷纲", "规划", "全书", "长篇"),
        "悬念": ("悬念", "钩子", "谜团"),
        "开篇": ("开篇", "开头", "开场"),
        "文笔": ("文笔", "句子", "描写", "修辞"),
        "世界观": ("世界观", "世界规则", "世界体系", "秩序", "势力", "地图"),
        "升级": ("升级", "成长", "境界", "进阶", "换地图"),
        "金手指": ("金手指", "系统", "特殊能力", "外挂"),
        "主动行为": ("主动行为", "主动选择", "人物欲望", "行动状态"),
        "代价": ("代价", "限制", "反噬", "牺牲"),
    }
    return [tag for tag, words in aliases.items() if any(word in query for word in words)]


async def embed_texts(texts: list[str]) -> list[list[float] | None]:
    if not texts:
        return []
    settings = get_settings()
    base_url = settings.embedding_base_url
    api_key = settings.embedding_api_key
    if not embedding_configured(settings):
        return [None] * len(texts)
    if settings.embedding_provider == "aliyun_dashscope" and not settings.embedding_base_url:
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    payload = {"model": settings.embedding_model, "input": texts}
    # DashScope's compatible endpoint accepts dimensions for the current embedding models.
    if settings.embedding_dimensions:
        payload["dimensions"] = settings.embedding_dimensions
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    response.raise_for_status()
    data = sorted(response.json()["data"], key=lambda item: item.get("index", 0))
    if len(data) != len(texts):
        raise ValueError(f"Embedding 数量错误: {len(data)} != {len(texts)}")
    vectors = [item["embedding"] for item in data]
    for vector in vectors:
        if len(vector) != settings.embedding_dimensions:
            raise ValueError(f"Embedding 维度错误: {len(vector)} != {settings.embedding_dimensions}")
    return vectors


async def embed_text(text: str) -> list[float] | None:
    return (await embed_texts([text]))[0]


def _rrf(rows: Iterable[tuple[object, float]], source: str, weight: float = 1.0) -> dict:
    result: dict = {}
    for rank, (row, _score) in enumerate(rows, start=1):
        item = result.setdefault(row.id, {"row": row, "rrf": 0.0, "sources": []})
        item["rrf"] += weight / (60 + rank)
        item["sources"].append(source)
    return result


async def writing_guide_search(
    db: AsyncSession,
    query: str,
    *,
    tags: list[str] | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Search the source-grounded writing library without mixing it into story Canon."""
    effective_tags = tags or _infer_writing_tags(query)
    filters = []
    if effective_tags:
        filters.append(WritingKnowledgeChunk.tags.overlap(effective_tags))
    fts_rank = func.ts_rank_cd(
        func.to_tsvector("simple", WritingKnowledgeChunk.content),
        func.plainto_tsquery("simple", query),
    )
    fts_rows = list(
        (
            await db.execute(
                select(WritingKnowledgeChunk, fts_rank.label("score"))
                .where(*filters, fts_rank > 0)
                .order_by(fts_rank.desc())
                .limit(limit * 4)
            )
        ).all()
    )
    lexical_source = "guide_fts"
    if not fts_rows and effective_tags:
        fts_rows = list(
            (
                await db.execute(
                    select(WritingKnowledgeChunk, literal(0.0).label("score"))
                    .where(*filters)
                    .order_by(WritingKnowledgeChunk.created_at.asc())
                    .limit(limit * 4)
                )
            ).all()
        )
        lexical_source = "guide_tag"
    vector_rows: list[Any] = []
    try:
        embedding = await embed_text(query)
    except (httpx.HTTPError, ValueError, KeyError):
        embedding = None
    if embedding is not None:
        distance = WritingKnowledgeChunk.embedding.cosine_distance(embedding)
        settings = get_settings()
        vector_rows = list(
            (
                await db.execute(
                    select(WritingKnowledgeChunk, distance.label("distance"))
                    .where(
                        *filters,
                        WritingKnowledgeChunk.embedding.is_not(None),
                        WritingKnowledgeChunk.embedding_model == settings.embedding_model,
                        WritingKnowledgeChunk.embedding_dimensions == settings.embedding_dimensions,
                    )
                    .order_by(distance.asc())
                    .limit(limit * 4)
                )
            ).all()
        )
    lexical_weight = 0.15 if lexical_source == "guide_tag" else 1.0
    ranks = _rrf(fts_rows, lexical_source, lexical_weight)
    for key, item in _rrf(vector_rows, "guide_vector", 1.2).items():
        existing = ranks.setdefault(key, item)
        if existing is not item:
            existing["rrf"] += item["rrf"]
            existing["sources"].extend(item["sources"])
    ranked = sorted(ranks.values(), key=lambda item: item["rrf"], reverse=True)
    ordered: list[dict[str, Any]] = []
    seen_documents: set[Any] = set()
    for item in ranked:
        document_id = item["row"].document_id
        if document_id in seen_documents:
            continue
        ordered.append(item)
        seen_documents.add(document_id)
        if len(ordered) >= limit:
            break
    if len(ordered) < limit:
        ordered_ids = {item["row"].id for item in ordered}
        ordered.extend(item for item in ranked if item["row"].id not in ordered_ids)
        ordered = ordered[:limit]
    document_ids = list({item["row"].document_id for item in ordered})
    documents = {
        row.id: row
        for row in (
            await db.scalars(select(WritingKnowledgeDocument).where(WritingKnowledgeDocument.id.in_(document_ids)))
        ).all()
    }
    return [
        {
            "chunk_id": str(item["row"].id),
            "content": item["row"].content,
            "heading_path": item["row"].heading_path,
            "tags": item["row"].tags,
            "score": round(item["rrf"], 6),
            "source": "+".join(item["sources"]),
            "document_id": str(item["row"].document_id),
            "source_title": documents[item["row"].document_id].title,
            "source_path": documents[item["row"].document_id].source_path,
        }
        for item in ordered
    ]


async def writing_method_card_search(
    db: AsyncSession,
    query: str,
    *,
    tags: list[str] | None = None,
    limit: int = 4,
    status: str = "published",
) -> list[dict[str, Any]]:
    """Search the compiled LLM-Wiki-style method layer before raw excerpts."""
    tag_aliases = {"对白": "对话", "悬疑": "悬念", "章纲": "大纲", "卷纲": "大纲"}
    effective_tags = list(dict.fromkeys([*(tags or []), *_infer_writing_tags(query)]))
    effective_tags = list(dict.fromkeys([*effective_tags, *(tag_aliases.get(tag, tag) for tag in effective_tags)]))
    filters = [WritingMethodCard.status == status]
    rank = func.ts_rank_cd(
        func.to_tsvector("simple", WritingMethodCard.principle + " " + WritingMethodCard.when_to_use),
        func.plainto_tsquery("simple", query),
    )
    rows = list(
        (
            await db.execute(
                select(WritingMethodCard, rank.label("score"))
                .where(*filters, rank > 0)
                .order_by(rank.desc())
                .limit(limit)
            )
        ).all()
    )
    if not rows:
        cards = list((await db.scalars(select(WritingMethodCard).where(*filters))).all())

        def lexical_card_score(card: WritingMethodCard) -> float:
            searchable = " ".join([card.title, card.principle, card.when_to_use, *card.tags])
            tag_score = len(set(effective_tags).intersection(card.tags)) * 3
            direct_score = sum(2 for tag in effective_tags if tag in searchable)
            phrase_score = sum(1 for token in query.replace("，", " ").split() if token in searchable)
            return float(tag_score + direct_score + phrase_score)

        ranked_cards = sorted(cards, key=lambda card: (lexical_card_score(card), card.updated_at), reverse=True)
        rows = [(card, lexical_card_score(card)) for card in ranked_cards[:limit]]
    return [
        {
            "card_id": str(card.id),
            "title": card.title,
            "principle": card.principle,
            "when_to_use": card.when_to_use,
            "procedure": card.procedure,
            "checks": card.checks,
            "anti_patterns": card.anti_patterns,
            "tags": card.tags,
            "sources": [str(value) for value in (card.source_chunk_ids or [])],
            "score": round(float(score), 6),
        }
        for card, score in rows
    ]


async def hybrid_search(
    db: AsyncSession,
    project_id,
    query: str,
    *,
    entities: list[str] | None = None,
    chapter_before: int | None = None,
    limit: int = 12,
) -> list[RetrievalHit]:
    filters = [ChapterChunk.project_id == project_id]
    if chapter_before is not None:
        filters.append(ChapterChunk.chapter_sequence < chapter_before)

    fts_rank = func.ts_rank_cd(
        func.to_tsvector("simple", ChapterChunk.content),
        func.plainto_tsquery("simple", query),
    )
    fts_rows = (
        await db.execute(
            select(ChapterChunk, fts_rank.label("score"))
            .where(*filters, fts_rank > 0)
            .order_by(fts_rank.desc())
            .limit(limit * 3)
        )
    ).all()

    vector_rows: list[Any] = []
    try:
        embedding = await embed_text(query)
    except (httpx.HTTPError, ValueError, KeyError):
        embedding = None
    if embedding is not None:
        distance = ChapterChunk.embedding.cosine_distance(embedding)
        settings = get_settings()
        vector_rows = (
            await db.execute(
                select(ChapterChunk, distance.label("distance"))
                .where(
                    *filters,
                    ChapterChunk.embedding.is_not(None),
                    ChapterChunk.embedding_model == settings.embedding_model,
                    ChapterChunk.embedding_dimensions == settings.embedding_dimensions,
                )
                .order_by(distance.asc())
                .limit(limit * 3)
            )
        ).all()

    entity_rows: list[ChapterChunk] = []
    if entities:
        entity_filters = [
            ChapterChunk.project_id == project_id,
            ChapterChunk.entities.overlap(entities),
        ]
        if chapter_before is not None:
            entity_filters.append(ChapterChunk.chapter_sequence < chapter_before)
        entity_rows = list(
            (
                await db.scalars(
                    select(ChapterChunk)
                    .where(*entity_filters)
                    .order_by(ChapterChunk.chapter_sequence.desc(), ChapterChunk.chunk_index.asc())
                    .limit(limit * 3)
                )
            ).all()
        )

    ranks: dict[Any, dict[str, Any]] = {}
    for rank, (chunk, _score) in enumerate(fts_rows, start=1):
        item = ranks.setdefault(chunk.id, {"chunk": chunk, "rrf": 0.0, "sources": []})
        item["rrf"] += 1.0 / (60 + rank)
        item["sources"].append("fts")
        if entities and set(entities).intersection(chunk.entities):
            item["rrf"] += 1.2 / 60
            item["sources"].append("entity")
    for rank, (chunk, _distance) in enumerate(vector_rows, start=1):
        item = ranks.setdefault(chunk.id, {"chunk": chunk, "rrf": 0.0, "sources": []})
        item["rrf"] += 0.8 / (60 + rank)
        item["sources"].append("vector")
    for rank, chunk in enumerate(entity_rows, start=1):
        item = ranks.setdefault(chunk.id, {"chunk": chunk, "rrf": 0.0, "sources": []})
        if "entity" not in item["sources"]:
            item["rrf"] += 1.2 / (60 + rank)
            item["sources"].append("entity")

    ordered = sorted(ranks.values(), key=lambda item: item["rrf"], reverse=True)[:limit]
    return [
        RetrievalHit(
            chapter_sequence=item["chunk"].chapter_sequence,
            content=item["chunk"].content,
            score=round(item["rrf"], 6),
            source="+".join(item["sources"]),
        )
        for item in ordered
    ]


async def build_toc_view(db: AsyncSession, project_id, parent_id=None) -> list[dict[str, Any]]:
    if isinstance(parent_id, str):
        parent_id = uuid.UUID(parent_id)
    rows = list(
        (
            await db.scalars(
                select(NovelToc)
                .where(NovelToc.project_id == project_id, NovelToc.parent_id == parent_id)
                .order_by(NovelToc.sequence.asc())
            )
        ).all()
    )
    return [
        {
            "node_id": str(row.id),
            "level": row.level,
            "title": row.title,
            "summary": row.summary or "",
            "chapter_range": [row.chapter_range_start, row.chapter_range_end],
            "characters": row.characters,
            "key_events": row.key_events,
        }
        for row in rows
    ]


async def pageindex_navigate(
    db: AsyncSession,
    project_id,
    query: str,
    *,
    thread_id: str,
    max_depth: int = 4,
    max_nodes: int = 12,
) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.scalars(
                select(NovelToc)
                .where(NovelToc.project_id == project_id)
                .order_by(NovelToc.level.asc(), NovelToc.sequence.asc())
            )
        ).all()
    )
    nodes = [
        {
            "node_id": str(row.id),
            "parent_id": str(row.parent_id) if row.parent_id else None,
            "level": row.level,
            "title": row.title,
            "summary": row.summary or "",
            "chapter_range": [row.chapter_range_start, row.chapter_range_end],
            "characters": row.characters,
            "key_events": row.key_events,
        }
        for row in rows
    ]
    if not nodes:
        return []
    terms = {token for token in query.replace("，", " ").replace("。", " ").split() if token}
    ranked_ids: list[str] = []
    if get_settings().llm_backend != "mock":
        from app.services.llm_client import llm_client as _llm
        from app.services.skill_loader import load_skill_prompt
        from app.utils.canonical import parse_json_object

        try:
            raw = await _llm.complete(
                load_skill_prompt("novel-pageindex") or "你是小说分层索引导航器，只输出 JSON。",
                json.dumps({"query": query, "nodes": nodes, "max_nodes": max_nodes}, ensure_ascii=False),
                response_format="json",
            )
            ranked_ids = [str(value) for value in parse_json_object(raw).get("ranked_node_ids", [])]
        except (ValueError, httpx.HTTPError):
            ranked_ids = []
    if not ranked_ids:
        ranked = sorted(
            nodes,
            key=lambda node: sum(term in json.dumps(node, ensure_ascii=False) for term in terms),
            reverse=True,
        )
        ranked_ids = [node["node_id"] for node in ranked[:max_nodes]]
    by_id = {node["node_id"]: node for node in nodes}
    return [by_id[node_id] for node_id in ranked_ids if node_id in by_id][:max_nodes]
