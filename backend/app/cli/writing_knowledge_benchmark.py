from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.database import SessionLocal
from app.engine.retrieval import writing_guide_search


async def run(dataset_path: Path, *, limit: int) -> None:
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    results = []
    async with SessionLocal() as db:
        for case in cases:
            hits = await writing_guide_search(db, case["query"], limit=limit)
            expected_tags = set(case.get("expected_tags", []))
            expected_terms = case.get("expected_terms", [])
            relevant = any(
                expected_tags.intersection(hit["tags"]) or any(term in hit["content"] for term in expected_terms)
                for hit in hits
            )
            cited = bool(hits) and all(
                hit.get("chunk_id") and hit.get("source_path") and hit.get("source_title") for hit in hits
            )
            results.append(
                {
                    "category": case["category"],
                    "query": case["query"],
                    "relevant_at_k": relevant,
                    "citations_complete": cited,
                    "hit_count": len(hits),
                }
            )
    total = len(results)
    report = {
        "dataset": str(dataset_path),
        "cases": total,
        "limit": limit,
        "heuristic_recall_at_k": round(sum(item["relevant_at_k"] for item in results) / total, 4),
        "citation_completeness": round(sum(item["citations_complete"] for item in results) / total, 4),
        "failures": [item for item in results if not item["relevant_at_k"] or not item["citations_complete"]],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="运行写作知识库检索健康检查")
    parser.add_argument(
        "dataset",
        nargs="?",
        type=Path,
        default=Path(__file__).parents[2] / "benchmarks" / "writing_knowledge_queries.json",
    )
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run(args.dataset, limit=args.limit))


if __name__ == "__main__":
    main()
