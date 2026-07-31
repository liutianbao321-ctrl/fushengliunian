from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal
from app.services.writing_knowledge import compile_method_cards, curate_method_cards, embed_missing_chunks, ingest_path


async def run(
    root: str | None,
    *,
    embed: bool,
    compile_cards: bool,
    card_limit: int | None,
    curate_cards: bool,
    embed_limit: int | None,
    verbose_errors: bool,
) -> None:
    settings = get_settings()
    resolved_root = root or settings.writing_knowledge_root
    if not resolved_root:
        raise SystemExit("请传入知识库目录，或配置 WRITING_KNOWLEDGE_ROOT")
    async with SessionLocal() as db:
        report = await ingest_path(db, resolved_root, embed=embed)
        if embed:
            backfill = await embed_missing_chunks(db, limit=embed_limit)
            report["embedding_backfill"] = {
                "missing_seen": backfill["missing_seen"],
                "embedded": backfill["embedded"],
                "vector_enabled": backfill["vector_enabled"],
                "already_running": backfill.get("already_running", False),
                "error_count": len(backfill["errors"]),
            }
            if verbose_errors:
                report["embedding_backfill"]["errors"] = backfill["errors"]
        if compile_cards:
            report["method_cards_created"] = await compile_method_cards(db, limit=card_limit)
        if curate_cards:
            report["curated_method_cards"] = await curate_method_cards(db)
    errors = report.pop("errors")
    report["error_count"] = len(errors)
    report["error_summary"] = dict(
        sorted(
            Counter(
                f"{item['stage']}:{Path(item['path']).suffix.lower() or '[no extension]'}" for item in errors
            ).items()
        )
    )
    if verbose_errors:
        report["errors"] = errors
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="导入写作指导库并构建可追溯 RAG")
    parser.add_argument("root", nargs="?", help="写作指导库根目录")
    parser.add_argument("--no-embed", action="store_true", help="只导入文本，稍后再生成向量")
    parser.add_argument("--compile-cards", action="store_true", help="生成带来源的方法卡")
    parser.add_argument("--card-limit", type=int, default=None, help="本次最多编译的方法卡数")
    parser.add_argument("--curate-cards", action="store_true", help="发布经审查且可追溯来源的核心方法卡")
    parser.add_argument("--embed-limit", type=int, default=None, help="本轮最多回填多少个缺失向量")
    parser.add_argument("--verbose-errors", action="store_true", help="输出每个失败文件的详细信息")
    args = parser.parse_args()
    asyncio.run(
        run(
            args.root,
            embed=not args.no_embed,
            compile_cards=args.compile_cards,
            card_limit=args.card_limit,
            curate_cards=args.curate_cards,
            embed_limit=args.embed_limit,
            verbose_errors=args.verbose_errors,
        )
    )


if __name__ == "__main__":
    main()
