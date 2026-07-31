import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.engine.retrieval import _infer_writing_tags
from app.models import WritingKnowledgeChunk, WritingKnowledgeDocument
from app.services import writing_knowledge
from app.services.writing_knowledge import _decode_text, compile_method_card, ingest_path, split_guide


class FakeSession:
    def __init__(self, existing: WritingKnowledgeDocument | None = None) -> None:
        self.existing = existing
        self.added: list[object] = []
        self.executed: list[object] = []

    async def scalar(self, _query):
        return self.existing

    async def execute(self, query):
        self.executed.append(query)

    def add(self, value: object) -> None:
        if isinstance(value, WritingKnowledgeDocument) and value.id is None:
            value.id = uuid.uuid4()
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


def test_decode_text_handles_utf16_without_postgres_null_bytes() -> None:
    decoded = _decode_text("人物要有渴望".encode("utf-16"))

    assert decoded == "人物要有渴望"
    assert "\x00" not in decoded


def test_writing_query_routes_domain_synonyms_to_tags() -> None:
    assert {"人物", "节奏", "大纲"}.issubset(_infer_writing_tags("配角在长篇章纲里如何通过放慢场景表现动机"))


def test_split_guide_preserves_heading_path_source_offsets_and_tags() -> None:
    text = "一、人物冲突\n人物必须有具体渴望。\n1. 阻力\n不要为了反转让人物突然降智。\n"

    chunks = split_guide(text, Path("写作指导库/人物教程.txt"), max_chars=40, overlap=0)

    assert chunks
    assert chunks[0]["heading_path"] == ["一、人物冲突"]
    assert chunks[0]["start_char"] == 0
    assert chunks[-1]["end_char"] == len(text)
    assert "人物" in {tag for chunk in chunks for tag in chunk["tags"]}


def test_compiled_method_card_keeps_source_chunk_citation() -> None:
    chunk = WritingKnowledgeChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=0,
        heading_path=["对话"],
        content="对话要有潜台词。\n1. 先确认双方目的。\n不要轮流递送背景信息。",
        start_char=0,
        end_char=32,
        tags=["对话"],
    )

    card = compile_method_card(chunk)

    assert card.status == "draft"
    assert card.source_chunk_ids == [chunk.id]
    assert "对话" in card.tags


def test_compiled_method_card_limits_imported_heading_to_database_width() -> None:
    chunk = WritingKnowledgeChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=0,
        heading_path=["长" * 800],
        content="具体方法。",
        start_char=0,
        end_char=5,
        tags=[],
    )

    card = compile_method_card(chunk)

    assert len(card.title) == 500


@pytest.mark.asyncio
async def test_ingest_retries_an_unchanged_error_document(tmp_path: Path) -> None:
    source = tmp_path / "人物.txt"
    source.write_text("人物必须有具体渴望。", encoding="utf-8")
    existing = WritingKnowledgeDocument(
        id=uuid.uuid4(),
        source_path=str(source),
        source_sha256="old",
        title="人物",
        category="未分类",
        source_format="txt",
        status="error",
        error_message="旧转换器不可用",
        outline=[],
        metadata_json={},
    )
    # Match the digest because unchanged failed sources are the retry case.
    existing.source_sha256 = writing_knowledge.hashlib.sha256(source.read_bytes()).hexdigest()
    db = FakeSession(existing)

    report = await ingest_path(db, tmp_path, embed=False)

    assert report["imported"] == 1
    assert report["retried"] == 1
    assert report["failed"] == 0
    assert existing.status == "ready"
    assert existing.error_message is None
    assert db.executed
    assert any(isinstance(item, WritingKnowledgeChunk) for item in db.added)


@pytest.mark.asyncio
async def test_ingest_batches_embeddings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "节奏.txt"
    source.write_text("占位文本", encoding="utf-8")
    pieces = [
        {
            "heading_path": ["节奏"],
            "content": f"片段 {index}",
            "start_char": index,
            "end_char": index + 1,
            "tags": ["节奏"],
        }
        for index in range(5)
    ]
    batch_lengths: list[int] = []

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        batch_lengths.append(len(texts))
        return [[0.0] * 1024 for _ in texts]

    monkeypatch.setattr(writing_knowledge, "split_guide", lambda *_args, **_kwargs: pieces)
    monkeypatch.setattr(writing_knowledge, "embed_texts", fake_embed)
    monkeypatch.setattr(writing_knowledge, "get_settings", lambda: SimpleNamespace(embedding_batch_size=2))

    report = await ingest_path(FakeSession(), tmp_path, embed=True)

    assert batch_lengths == [2, 2, 1]
    assert report["embedded"] == 5
