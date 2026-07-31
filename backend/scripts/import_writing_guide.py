#!/usr/bin/env python3
"""将写作指导库中的文档导入数据库，并编译方法卡。

用法:
    python scripts/import_writing_guide.py /path/to/写作指导库 [--no-embed]

示例:
    python scripts/import_writing_guide.py ~/documents/personal/写作指导库
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.services.writing_knowledge import compile_method_cards, ingest_path


async def main():
    parser = argparse.ArgumentParser(description="导入写作指导库到数据库")
    parser.add_argument("path", type=str, help="写作指导库目录路径")
    parser.add_argument("--no-embed", action="store_true", help="跳过 embedding 生成")
    parser.add_argument("--compile", action="store_true", help="导入后编译方法卡")
    args = parser.parse_args()

    guide_path = Path(args.path).expanduser().resolve()
    if not guide_path.is_dir():
        print(f"错误: 目录不存在 — {guide_path}")
        sys.exit(1)

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        print(f"正在导入: {guide_path}")
        result = await ingest_path(db, guide_path, embed=not args.no_embed)
        print(f" 文件总数:      {result['files']}")
        print(f" 本次导入:      {result['imported']}")
        print(f" 跳过(已存在):  {result['skipped']}")
        print(f" 重试(已变更):  {result['retried']}")
        print(f" 嵌入向量:      {result['embedded']}")
        if result.get("errors"):
            print(f" 错误:          {len(result['errors'])} 个")
            for err in result["errors"][:5]:
                print(f"   - {err['path']}: {err.get('error', '')}")
        if args.compile:
            print("\n正在编译方法卡...")
            compiled = await compile_method_cards(db)
            print(f" 编译方法卡:    {compiled} 张")
        print("\n导入完成。")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
