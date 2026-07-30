"""运行全量、完全离线的文档 ID 检索评估。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_CSV_PATH = SCRIPT_DIR / "pcb_nasa_evaluation.csv"
RESULTS_DIR = SCRIPT_DIR / "results"

# 第 4 步必须完全离线；在导入项目配置和适配器前锁定相关开关。
os.environ["RAG_VECTOR_ENABLED"] = "false"
os.environ["RAG_REWRITE_QUERIES"] = "0"
os.environ["RAG_RERANKER_ENABLED"] = "false"
os.environ["RAG_HYBRID_ENABLED"] = "true"

from adapters.project_rag import ProjectRagAdapter, parse_relevant_doc_ids  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="全量无 LLM ID 检索指标")
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_text(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=PROJECT_DIR,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return completed.stdout.strip()


def unique_document_hits(engine: Any, question: str, top_k: int) -> list[Any]:
    """保留每个文档的最高排名命中，直到获得 Top-K 文档。"""
    raw_hits = engine._search(question, max(top_k * 4, 10))
    hits: list[Any] = []
    seen: set[str] = set()
    for hit in raw_hits:
        document_id = str(hit.chunk.doc_name).strip()
        if not document_id or document_id in seen:
            continue
        seen.add(document_id)
        hits.append(hit)
        if len(hits) == top_k:
            break
    return hits


def score_retrieval(retrieved: list[str], relevant: list[str]) -> dict[str, float]:
    relevant_set = set(relevant)
    matched = relevant_set.intersection(retrieved)
    first_rank = next(
        (rank for rank, document_id in enumerate(retrieved, start=1) if document_id in relevant_set),
        0,
    )
    return {
        "id_context_precision_at_3": len(matched) / len(retrieved) if retrieved else 0.0,
        "id_context_recall_at_3": len(matched) / len(relevant_set) if relevant_set else 0.0,
        "hit_at_1": float(first_rank == 1),
        "hit_at_3": float(0 < first_rank <= 3),
        "mrr": 1.0 / first_rank if first_rank else 0.0,
    }


def main() -> None:
    args = parse_args()
    if args.top_k != 3:
        raise ValueError("第 4 步的正式口径固定为 --top-k 3")

    csv_path = args.csv_path.resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(f"评估 CSV 不存在: {csv_path}")

    details: list[dict[str, Any]] = []
    with ProjectRagAdapter.from_csv(csv_path, top_k=args.top_k) as adapter:
        engine = adapter.engine
        print(f"数据集：{csv_path}（{len(adapter.dataframe)} 条）")
        print("模式：本地词级 + 字符级 TF-IDF；生成/改写/reranker/Embedding 均禁用")
        for index, row in enumerate(adapter.dataframe.itertuples(index=False), start=1):
            hits = unique_document_hits(engine, str(row.question_predict), args.top_k)
            retrieved_ids = [str(hit.chunk.doc_name) for hit in hits]
            relevant_ids = parse_relevant_doc_ids(str(row.relevant_doc_ids))
            scores = score_retrieval(retrieved_ids, relevant_ids)
            details.append(
                {
                    "sample_id": str(row.chunk_id),
                    "question": str(row.question_predict),
                    "reference_context_ids": relevant_ids,
                    "retrieved_context_ids": retrieved_ids,
                    "retrieved_scores": [round(float(hit.score), 8) for hit in hits],
                    "metrics": scores,
                }
            )
            print(
                f"[{index:02d}/{len(adapter.dataframe)}] "
                f"{'HIT ' if scores['hit_at_3'] else 'MISS'} {row.chunk_id} -> {retrieved_ids}"
            )

        metric_names = tuple(details[0]["metrics"])
        summary = {
            name: sum(item["metrics"][name] for item in details) / len(details)
            for name in metric_names
        }
        misses = [item for item in details if not item["metrics"]["hit_at_3"]]
        generated_at = datetime.now().astimezone()
        code_files = [
            Path(__file__).resolve(),
            SCRIPT_DIR / "adapters" / "project_rag.py",
            PROJECT_DIR / "backend" / "agent" / "rag" / "rag_engine.py",
        ]
        git_commit = git_text("rev-parse", "HEAD")
        payload = {
            "schema_version": 1,
            "experiment": "step_4_offline_id_retrieval",
            "generated_at": generated_at.isoformat(timespec="seconds"),
            "dataset": {
                "path": str(csv_path.relative_to(PROJECT_DIR)),
                "rows": len(adapter.dataframe),
                "sha256": sha256_file(csv_path),
            },
            "configuration": {
                "top_k": args.top_k,
                "retrieval": "word_char_tfidf",
                "hybrid_enabled": bool(engine._hybrid_enabled),
                "char_weight": float(engine._char_weight),
                "generation_enabled": False,
                "query_rewrite_enabled": False,
                "llm_reranker_enabled": False,
                "external_embedding_enabled": False,
            },
            "code": {
                "git_commit": git_commit or None,
                "git_worktree_dirty": bool(git_text("status", "--porcelain")),
                "files_sha256": {
                    str(path.relative_to(PROJECT_DIR)): sha256_file(path) for path in code_files
                },
                "python": sys.version.split()[0],
                "platform": platform.platform(),
            },
            "metrics": summary,
            "thresholds": {
                "hit_at_1": 0.75,
                "hit_at_3": 0.85,
                "mrr": 0.80,
                "id_context_recall_at_3": 0.85,
            },
            "threshold_results": {
                name: summary[name] >= threshold
                for name, threshold in {
                    "hit_at_1": 0.75,
                    "hit_at_3": 0.85,
                    "mrr": 0.80,
                    "id_context_recall_at_3": 0.85,
                }.items()
            },
            "top_3_miss_count": len(misses),
            "top_3_misses": misses,
            "samples": details,
        }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = args.output.resolve() if args.output else RESULTS_DIR / (
        f"id_metrics_pcb_nasa_{generated_at.strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n第 4 步 ID 检索指标：")
    for name, value in summary.items():
        print(f"  {name}: {value:.4f}")
    print(f"  Top-3 未命中: {len(misses)}/{len(details)}")
    print(f"结果文件：{output_path}")


if __name__ == "__main__":
    main()
