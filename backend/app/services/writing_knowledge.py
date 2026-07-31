"""Import and compile the personal writing library into source-grounded RAG records."""

from __future__ import annotations

import asyncio
import hashlib
import re
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.engine.retrieval import embed_texts, embedding_configured
from app.models import WritingKnowledgeChunk, WritingKnowledgeDocument, WritingMethodCard

SUPPORTED_TEXT = {".txt", ".md", ".text", ".rtf"}
OFFICE_EXTENSIONS = {".doc", ".wps", ".xlsx"}

CURATED_METHODS = [
    {
        "slug": "reader-promise-ledger",
        "title": "用读者期待管理长篇承诺",
        "principle": "长篇吸引力来自期待的开启、推进与兑现；悬念、关系、成长和身份承诺必须分层维护。",
        "when_to_use": "定卷纲、章纲和检查长线是否失速时",
        "procedure": ["写明本章开启或推进的期待", "安排可见进展与新的代价", "在承诺窗口内兑现或有理由改期"],
        "checks": ["本章是否改变至少一条读者正在等待的线", "新钩子是否具体而非空泛"],
        "anti_patterns": ["只加谜团不回收", "用突发事件冒充推进"],
        "tags": ["期待", "悬念", "伏笔", "长篇"],
        "source_terms": ["期待感", "期待"],
    },
    {
        "slug": "causal-scene-contract",
        "title": "以选择和后果组织场景",
        "principle": "可执行场景由欲望、阻力、行动和局部后果构成；重大代价只留给真正的高潮节点。",
        "when_to_use": "把章纲变成正文场景时",
        "procedure": ["给人物一个当下能行动的目标", "让他行动并得到回应", "把眼前后果交给下一场"],
        "checks": ["删掉该场是否会破坏因果链", "人物或读者理解是否至少有一项变化"],
        "anti_patterns": ["事件清单式扩写", "人物只被情节拖着走"],
        "tags": ["情节", "人物", "冲突", "场景"],
        "source_terms": ["情节", "冲突"],
    },
    {
        "slug": "pressure-reveals-character",
        "title": "让压力下的选择刻画人物",
        "principle": "人物不是标签集合；其核心欲望、防御和底线要在两难选择及代价中被读者看见。",
        "when_to_use": "设计主角、配角转变和关系冲突时",
        "procedure": ["明确人物想要和害怕失去什么", "制造两种都要付价的选择", "让后果持续影响关系和行动"],
        "checks": ["选择是否只有这个人物会这样做", "变化是否有压力和铺垫"],
        "anti_patterns": ["用形容词宣布性格", "为反转让人物突然降智"],
        "tags": ["人物", "主动行为", "代价"],
        "source_terms": ["人物刻画", "人物"],
    },
    {
        "slug": "subtext-dialogue",
        "title": "用目的和隐瞒写对话",
        "principle": "有效对话不是轮流递送信息，而是双方带着目的试探、回避和交换筹码。",
        "when_to_use": "关系推进、谈判、冲突和信息释放时",
        "procedure": ["给双方不同的表面目的和真实目的", "让回答改变对方策略", "用动作与停顿承担未说出口的部分"],
        "checks": ["遮住姓名后声音是否仍可区分", "台词是否改变局势或关系"],
        "anti_patterns": ["自问自答交代设定", "每句都精准服务说明"],
        "tags": ["对话", "对白", "人物"],
        "source_terms": ["潜台词", "对话"],
    },
    {
        "slug": "consciousness-continuity",
        "title": "用人物意识接力消除情节拼装感",
        "principle": (
            "真人叙事的连续性来自余波改变注意、注意触发私人联想、联想造成解释或误读、"
            "解释促成动作、动作再留下余波；细节必须经过具体人物的欲望和关系史筛选。"
        ),
        "when_to_use": "正文像事件清单、场景切换后人物情绪清零、细节丰富却没有代入感时",
        "procedure": [
            "找出上一瞬间尚未消散的身体感受、意图、误解或未说出口的话",
            "让余波决定人物此刻先注意什么并唤起只属于他的联想",
            "让人物的解释、自我辩护或误读自然促成下一步动作",
            "在场景末留下会影响下一场注意或措辞的具体残留",
        ],
        "checks": [
            "相邻段落之间能否说清注意为何转移",
            "换成同题材任意主角后关键观察与反应是否仍成立",
            "对话潜台词是否来自双方关系史和当前隐瞒",
        ],
        "anti_patterns": ["用他想或他意识到反复解释心理", "场景切换后用摘要清空人物状态", "罗列与判断无关的感官细节"],
        "tags": ["人物", "代入感", "心理", "对白", "连续性", "真人感"],
        "source_terms": ["代入感", "心理描写", "人物刻画", "对话描写"],
    },
    {
        "slug": "pressure-density-pacing",
        "title": "用压力密度而非字数控制节奏",
        "principle": "节奏是压力、信息与后果密度的变化；快慢都要服务读者注意力，而不是按固定字数制造高潮。",
        "when_to_use": "审查章节松散、赶场或长期同速时",
        "procedure": ["标记每场新增压力、信息和后果", "在关键选择前留出反应空间", "压缩不改变判断的重复过程"],
        "checks": ["连续场景的压力是否有变化", "慢场是否仍在积累意义"],
        "anti_patterns": ["固定间隔强行高潮", "靠短句切段伪造紧张"],
        "tags": ["节奏", "情节"],
        "source_terms": ["节奏", "张弛"],
    },
    {
        "slug": "foreshadow-payoff-chain",
        "title": "把伏笔维护成可推进的因果线",
        "principle": "伏笔要经历埋设、强化、误读和回收，并在回收时改变人物选择或读者理解。",
        "when_to_use": "悬念、秘密和长线反转设计时",
        "procedure": ["记录首次可见证据", "在遗忘前用新含义推进", "以行动后果完成回收"],
        "checks": ["回收是否能指回早期证据", "伏笔是否只是作者知道"],
        "anti_patterns": ["结尾凭空加黑影", "揭晓后不改变任何事"],
        "tags": ["伏笔", "悬念", "情节"],
        "source_terms": ["伏笔", "铺垫"],
    },
    {
        "slug": "rolling-long-outline",
        "title": "滚动规划百万字长篇",
        "principle": "稳定全书核心承诺，细化当前卷与近期章节，远期只保留方向和约束，随已发生后果滚动更新。",
        "when_to_use": "规划长篇、换卷和发现大纲僵化时",
        "procedure": ["锁定全书不可变承诺", "细化当前卷的局势变化", "只为近期章节写可执行场景", "每章后根据后果更新"],
        "checks": ["当前卷是否兑现全书承诺的一部分", "远期规划是否给人物选择留空间"],
        "anti_patterns": ["开书前写死数百章", "遇到问题就换地图或杀角色"],
        "tags": ["大纲", "长篇", "卷纲", "章纲"],
        "source_terms": ["大纲和细纲", "大纲"],
    },
    {
        "slug": "reader-orientation-budget",
        "title": "控制开篇的读者认知负担",
        "principle": "前三万字先让读者认住主角、地点和眼前目标；设定、人物与悬念必须按理解顺序逐步进入。",
        "when_to_use": "规划开篇十章、首章和检查读者看不懂时",
        "procedure": ["每章写明读者已知的锚点", "每章只加入一个主要新信息", "前三章持续聚焦主角", "用行动展示必要规则"],
        "checks": ["读者是否知道跟着谁、在哪里、眼前要什么", "前五章是否出现超过两个地点或过多人物", "是否把卷末答案提前写进开篇"],
        "anti_patterns": ["开篇罗列世界百科", "多人多线同时启动", "十章完成一卷甚至全书问题", "每章都强行重大反转"],
        "tags": ["开篇", "代入感", "读者", "节奏", "长篇"],
        "source_terms": ["开头三万字", "代入感", "小剧情"],
    },
    {
        "slug": "genre-growth-contract",
        "title": "按题材兑现成长与关系体验",
        "principle": (
            "男频成长要写规则、资源、限制和代价；女频成长要同时维护能力、身份、关系与情感选择，"
            "不能只换地图或播报等级。"
        ),
        "when_to_use": "设计升级、金手指、感情线和卷转换时",
        "procedure": ["定义成长改变了什么行动可能", "同步增加限制与新责任", "让关系和身份回应能力变化"],
        "checks": ["升级是否解决旧问题并制造新问题", "感情推进是否来自双方选择"],
        "anti_patterns": ["无代价金手指", "把误会拖延当感情线", "换地图清空旧因果"],
        "tags": ["男频", "女频", "升级", "金手指", "言情", "玄幻"],
        "source_terms": ["金手指", "升级", "女频"],
    },
]


def _decode_text(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or data[:400].count(b"\x00") > 20:
        for encoding in ("utf-16", "utf-16-le", "utf-16-be"):
            try:
                return data.decode(encoding).replace("\x00", "")
            except UnicodeDecodeError:
                continue
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding).replace("\x00", "")
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace").replace("\x00", "")


def _read_docx(path: Path) -> str:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.iter(ns + "p"):
        value = "".join((node.text or "") for node in paragraph.iter(ns + "t")).strip()
        if value:
            paragraphs.append(value)
    return "\n".join(paragraphs)


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def _read_xls(path: Path) -> str:
    import xlrd

    workbook = xlrd.open_workbook(path, on_demand=True)
    sections = []
    try:
        for sheet in workbook.sheets():
            rows = ["\t".join(str(value).strip() for value in sheet.row_values(index)) for index in range(sheet.nrows)]
            content = "\n".join(row for row in rows if row.strip())
            if content:
                sections.append(f"# {sheet.name}\n{content}")
    finally:
        workbook.release_resources()
    return "\n\n".join(sections)


def _read_external_office(path: Path) -> str:
    """Use platform converters when old binary formats are present on the host."""
    with tempfile.TemporaryDirectory(prefix="fushengliunian-guide-") as temp_dir:
        converted = Path(temp_dir) / f"{path.stem}.txt"
        commands = [
            (("antiword", str(path)), True),
            (
                (
                    "textutil",
                    "-convert",
                    "txt",
                    "-encoding",
                    "UTF-8",
                    "-output",
                    str(converted),
                    str(path),
                ),
                False,
            ),
            (
                ("soffice", "--headless", "--convert-to", "txt:Text", "--outdir", temp_dir, str(path)),
                False,
            ),
        ]
        for command, reads_stdout in commands:
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            if reads_stdout and completed.returncode == 0 and completed.stdout.strip():
                return completed.stdout
            if completed.returncode == 0 and converted.exists():
                return converted.read_text(encoding="utf-8", errors="ignore")
    raise RuntimeError(f"无法解析 {path.suffix}，请在部署机安装 antiword 或 LibreOffice 后重试")


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_TEXT:
        return _decode_text(path.read_bytes())
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".xls":
        return _read_xls(path)
    if suffix in OFFICE_EXTENSIONS:
        return _read_external_office(path)
    raise RuntimeError(f"暂不支持 {suffix or '无扩展名'}")


def _tags(path: Path, heading_path: list[str], content: str) -> list[str]:
    raw = " ".join([str(part) for part in path.parts[-3:]] + heading_path + [content[:500]])
    candidates = (
        "大纲",
        "人物",
        "情节",
        "对白",
        "对话",
        "节奏",
        "伏笔",
        "悬念",
        "开篇",
        "文笔",
        "世界观",
        "世界规则",
        "升级",
        "金手指",
        "主动行为",
        "代价",
        "网文",
        "男频",
        "女频",
        "言情",
        "玄幻",
        "仙侠",
        "武侠",
        "都市",
        "科幻",
        "悬疑",
    )
    return [tag for tag in candidates if tag in raw]


def split_guide(text: str, source: Path, *, max_chars: int = 1800, overlap: int = 180) -> list[dict]:
    heading_path: list[str] = []
    chunks: list[dict] = []
    buffer: list[str] = []
    start = 0
    cursor = 0

    def flush(end: int) -> None:
        nonlocal buffer, start
        content = "\n".join(buffer).strip()
        if content:
            chunks.append(
                {
                    "heading_path": list(heading_path),
                    "content": content,
                    "start_char": start,
                    "end_char": end,
                    "tags": _tags(source, heading_path, content),
                }
            )
        tail = content[-overlap:] if overlap else ""
        buffer = [tail] if tail else []
        start = max(end - len(tail), 0)

    for line in text.splitlines():
        stripped = re.sub(r"^\s+", "", line).strip()
        if not stripped:
            cursor += len(line) + 1
            continue
        if re.match(r"^(#{1,6}\s+|[一二三四五六七八九十]+[、.．]|\d+[、.．])", stripped):
            if buffer:
                flush(cursor)
            heading = re.sub(r"^#+\s*", "", stripped)
            heading_path = [*heading_path[-2:], heading]
        buffer.append(stripped)
        cursor += len(line) + 1
        if sum(len(item) + 1 for item in buffer) >= max_chars:
            flush(cursor)
    if buffer:
        flush(len(text))
    return chunks


async def ingest_path(db: AsyncSession, root: str | Path, *, embed: bool = True) -> dict:
    root_path = Path(root).expanduser().resolve()
    files = [path for path in root_path.rglob("*") if path.is_file() and not path.name.startswith(".")]
    imported = retried = skipped = embedded = 0
    errors: list[dict] = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        existing = await db.scalar(
            select(WritingKnowledgeDocument).where(
                WritingKnowledgeDocument.source_path == str(path),
                WritingKnowledgeDocument.source_sha256 == digest,
            )
        )
        if existing and existing.status != "error":
            skipped += 1
            continue
        try:
            text = extract_text(path).replace("\x00", "")
            pieces = split_guide(text, path)
            if not pieces:
                raise RuntimeError("文件没有可导入的文本内容")
            values = {
                "source_path": str(path),
                "source_sha256": digest,
                "title": path.stem,
                "category": next((part for part in path.parts if "写作" in part or "网文" in part), "未分类"),
                "source_format": path.suffix.lower().lstrip("."),
                "status": "ready",
                "error_message": None,
                "outline": [{"heading_path": item["heading_path"], "chunk_index": i} for i, item in enumerate(pieces)],
            }
            if existing:
                await db.execute(delete(WritingKnowledgeChunk).where(WritingKnowledgeChunk.document_id == existing.id))
                for key, value in values.items():
                    setattr(existing, key, value)
                document = existing
                retried += 1
            else:
                document = WritingKnowledgeDocument(**values)
                db.add(document)
            await db.flush()
            chunks = []
            for index, piece in enumerate(pieces):
                chunk = WritingKnowledgeChunk(document_id=document.id, chunk_index=index, **piece)
                chunks.append(chunk)
                db.add(chunk)
            if embed:
                embedding_settings = get_settings()
                batch_size = max(embedding_settings.embedding_batch_size, 1)
                embedding_model = getattr(embedding_settings, "embedding_model", "unknown")
                for offset in range(0, len(chunks), batch_size):
                    batch = chunks[offset : offset + batch_size]
                    try:
                        vectors = await embed_texts([chunk.content for chunk in batch])
                        for chunk, vector in zip(batch, vectors, strict=True):
                            chunk.embedding = vector
                            chunk.embedding_model = embedding_model if vector is not None else None
                            chunk.embedding_dimensions = len(vector) if vector is not None else None
                            embedded += int(vector is not None)
                    except Exception as exc:  # indexing can be retried without losing source text
                        errors.append({"path": str(path), "stage": "embedding", "error": str(exc)[:300]})
            imported += 1
        except Exception as exc:
            errors.append({"path": str(path), "stage": "extract", "error": str(exc)[:500]})
            if existing:
                existing.status = "error"
                existing.error_message = str(exc)[:4000]
            else:
                db.add(
                    WritingKnowledgeDocument(
                        source_path=str(path),
                        source_sha256=digest,
                        title=path.stem,
                        category="未分类",
                        source_format=path.suffix.lower().lstrip("."),
                        status="error",
                        error_message=str(exc)[:4000],
                        outline=[],
                        metadata_json={},
                    )
                )
    await db.commit()
    failed = len({item["path"] for item in errors if item["stage"] == "extract"})
    return {
        "files": len(files),
        "imported": imported,
        "retried": retried,
        "skipped": skipped,
        "failed": failed,
        "embedded": embedded,
        "errors": errors,
    }


async def embed_missing_chunks(db: AsyncSession, *, limit: int | None = None) -> dict:
    settings = get_settings()
    vector_enabled = embedding_configured(settings)
    if not vector_enabled:
        return {"missing_seen": 0, "embedded": 0, "vector_enabled": False, "errors": []}
    lock_id = 7_241_024
    if not await db.scalar(select(func.pg_try_advisory_lock(lock_id))):
        return {
            "missing_seen": 0,
            "embedded": 0,
            "vector_enabled": True,
            "already_running": True,
            "errors": [],
        }
    batch_size = max(settings.embedding_batch_size, 1)
    embedded = missing_seen = 0
    errors: list[dict] = []
    failed_ids: set = set()
    concurrency = max(int(getattr(settings, "embedding_concurrency", 4)), 1)
    page_size = max(batch_size * concurrency * 4, batch_size)
    try:
        while limit is None or missing_seen < limit:
            current_limit = min(page_size, limit - missing_seen) if limit is not None else page_size
            filters = [WritingKnowledgeChunk.embedding.is_(None)]
            if failed_ids:
                filters.append(WritingKnowledgeChunk.id.not_in(failed_ids))
            chunks = list(
                (
                    await db.scalars(
                        select(WritingKnowledgeChunk)
                        .where(*filters)
                        .order_by(WritingKnowledgeChunk.created_at.asc())
                        .limit(current_limit)
                    )
                ).all()
            )
            if not chunks:
                break
            missing_seen += len(chunks)
            batches = [chunks[offset : offset + batch_size] for offset in range(0, len(chunks), batch_size)]
            for offset in range(0, len(batches), concurrency):
                wave = batches[offset : offset + concurrency]
                results = await asyncio.gather(
                    *(embed_texts([chunk.content for chunk in batch]) for batch in wave),
                    return_exceptions=True,
                )
                for batch, result in zip(wave, results, strict=True):
                    if isinstance(result, Exception):
                        failed_ids.update(chunk.id for chunk in batch)
                        errors.append(
                            {
                                "chunk_ids": [str(chunk.id) for chunk in batch],
                                "error": str(result)[:500],
                            }
                        )
                        continue
                    for chunk, vector in zip(batch, result, strict=True):
                        chunk.embedding = vector
                        chunk.embedding_model = (
                            getattr(settings, "embedding_model", "unknown") if vector is not None else None
                        )
                        chunk.embedding_dimensions = len(vector) if vector is not None else None
                        embedded += int(vector is not None)
                await db.commit()
            db.expunge_all()
    finally:
        await db.scalar(select(func.pg_advisory_unlock(lock_id)))
    return {"missing_seen": missing_seen, "embedded": embedded, "vector_enabled": True, "errors": errors}


def compile_method_card(chunk: WritingKnowledgeChunk) -> WritingMethodCard:
    lines = [line.strip(" -\t") for line in chunk.content.splitlines() if line.strip()]
    principle = lines[0][:1000] if lines else "从来源片段提炼写作方法"
    procedure = [line for line in lines if re.match(r"^(\d+[、.)]|[一二三四五六七八九十]+[、.])", line)][:8]
    checks = [line for line in lines if any(word in line for word in ("检查", "避免", "必须", "不要", "注意"))][:8]
    slug = f"guide-{str(chunk.id).replace('-', '')}"
    title = chunk.heading_path[-1] if chunk.heading_path else principle[:80]
    return WritingMethodCard(
        slug=slug,
        title=title[:500],
        principle=principle,
        when_to_use="写章纲、建筑场景或审稿时按标签选择",
        procedure=procedure or ["先明确人物目标、阻力和选择，再决定具体表达"],
        checks=checks or ["方法必须能在正文中观察到结果"],
        anti_patterns=["只复制抽象结论，不检查人物和场景因果"],
        tags=chunk.tags,
        wikilinks=[],
        source_chunk_ids=[chunk.id],
        status="draft",
    )


async def compile_method_cards(db: AsyncSession, *, limit: int | None = None) -> int:
    query = select(WritingKnowledgeChunk).order_by(WritingKnowledgeChunk.created_at.asc())
    if limit:
        query = query.limit(limit)
    chunks = list((await db.scalars(query)).all())
    cited_chunk_ids = {
        chunk_id
        for source_ids in (await db.scalars(select(WritingMethodCard.source_chunk_ids))).all()
        for chunk_id in (source_ids or [])
    }
    created = 0
    for chunk in chunks:
        if chunk.id in cited_chunk_ids:
            continue
        db.add(compile_method_card(chunk))
        cited_chunk_ids.add(chunk.id)
        created += 1
    await db.commit()
    return created


async def curate_method_cards(db: AsyncSession) -> dict[str, int]:
    """Publish a small reviewed method layer while preserving source-chunk traceability."""
    created = updated = skipped = 0
    for definition in CURATED_METHODS:
        source_ids: list = []
        for term in definition["source_terms"]:
            chunks = list(
                (
                    await db.scalars(
                        select(WritingKnowledgeChunk)
                        .where(WritingKnowledgeChunk.content.ilike(f"%{term}%"))
                        .order_by(WritingKnowledgeChunk.created_at.asc())
                        .limit(2)
                    )
                ).all()
            )
            source_ids.extend(chunk.id for chunk in chunks if chunk.id not in source_ids)
        if not source_ids:
            skipped += 1
            continue
        card = await db.scalar(select(WritingMethodCard).where(WritingMethodCard.slug == definition["slug"]))
        values = {key: value for key, value in definition.items() if key != "source_terms"}
        values.update({"source_chunk_ids": source_ids[:4], "wikilinks": [], "status": "published"})
        if card is None:
            db.add(WritingMethodCard(**values))
            created += 1
        else:
            for key, value in values.items():
                setattr(card, key, value)
            card.revision += 1
            updated += 1
    await db.commit()
    return {"created": created, "updated": updated, "skipped_without_sources": skipped}
