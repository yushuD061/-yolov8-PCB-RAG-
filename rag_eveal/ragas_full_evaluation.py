"""运行第 6 步：43 条完整项目链路 RAGAS 评估。"""

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
from urllib.parse import urlparse

import pandas as pd

from ragas_smoke_test import (
    ChatOpenAI,
    EvaluationDataset,
    FactualCorrectness,
    Faithfulness,
    IDBasedContextPrecision,
    IDBasedContextRecall,
    LLMContextRecall,
    LangchainEmbeddingsWrapper,
    LangchainLLMWrapper,
    OpenAIEmbeddings,
    ProjectRagAdapter,
    ResponseRelevancy,
    RunConfig,
    configure_target,
    env_config,
    evaluate,
    langchain_base_url,
    require_config,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_CSV_PATH = SCRIPT_DIR / "pcb_nasa_evaluation.csv"
RESULTS_DIR = SCRIPT_DIR / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="43 条完整 RAGAS 实验")
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--top-k", type=int, default=3)
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


def endpoint_host(config: dict[str, str]) -> str:
    parsed = urlparse(config["endpoint"])
    return parsed.hostname or ""


def summarize_column(series: pd.Series) -> dict[str, float | int | None]:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return {
            "mean": None,
            "median": None,
            "p25": None,
            "p75": None,
            "min": None,
            "max": None,
            "valid_count": 0,
            "failure_count": int(len(numeric)),
        }
    return {
        "mean": float(valid.mean()),
        "median": float(valid.median()),
        "p25": float(valid.quantile(0.25)),
        "p75": float(valid.quantile(0.75)),
        "min": float(valid.min()),
        "max": float(valid.max()),
        "valid_count": int(valid.count()),
        "failure_count": int(numeric.isna().sum()),
    }


def main() -> None:
    args = parse_args()
    if args.top_k != 3:
        raise ValueError("第 6 步正式口径固定为 --top-k 3")
    csv_path = args.csv_path.resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(f"评估 CSV 不存在: {csv_path}")

    target_config = env_config("OPENAI")
    judge_config = env_config("JUDGE")
    embedding_config = env_config("EVAL_EMBEDDING")
    require_config(target_config, "被测 RAG 模型")
    require_config(judge_config, "RAGAS 裁判模型")
    require_config(embedding_config, "RAGAS Embedding 模型")

    judge = ChatOpenAI(
        model=judge_config["model"],
        api_key=judge_config["apiKey"],
        base_url=langchain_base_url(judge_config["endpoint"]),
        temperature=0.0,
        max_retries=2,
    )
    evaluator_llm = LangchainLLMWrapper(judge)
    embedding_model = OpenAIEmbeddings(
        model=embedding_config["model"],
        api_key=embedding_config["apiKey"],
        base_url=langchain_base_url(embedding_config["endpoint"]),
        max_retries=2,
        check_embedding_ctx_length=False,
    )
    evaluator_embeddings = LangchainEmbeddingsWrapper(embedding_model)
    metrics = [
        IDBasedContextPrecision(),
        IDBasedContextRecall(),
        Faithfulness(),
        FactualCorrectness(language="chinese"),
        LLMContextRecall(),
        ResponseRelevancy(
            llm=evaluator_llm,
            embeddings=evaluator_embeddings,
            strictness=1,
        ),
    ]

    started_at = datetime.now().astimezone()
    with ProjectRagAdapter.from_csv(csv_path, top_k=args.top_k) as adapter:
        engine = adapter.engine
        configure_target(engine, target_config)
        rows = len(adapter.dataframe)
        print(f"第 6 步数据集：{csv_path}（{rows} 条）")
        print("正在运行真实链路：查询改写 + 混合 TF-IDF/RRF + LLM 精排 + Top-3 + 回答生成")
        samples = adapter.collect()

        dataset = EvaluationDataset.from_list(samples, name="ragas-full-pcb-nasa")
        workers = int(os.getenv("RAGAS_MAX_WORKERS", "2"))
        timeout = int(os.getenv("RAGAS_TIMEOUT", "120"))
        result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=evaluator_llm,
            run_config=RunConfig(
                timeout=timeout,
                max_retries=2,
                max_workers=workers,
                seed=42,
            ),
            experiment_name=f"ragas-full-pcb-nasa-{started_at.strftime('%Y%m%d-%H%M%S')}",
            raise_exceptions=False,
            show_progress=True,
        )
        finished_at = datetime.now().astimezone()
        details = result.to_pandas()

        metric_columns: list[str] = []
        for metric in metrics:
            matched = next(
                (
                    column
                    for column in details.columns
                    if column == metric.name or column.startswith(f"{metric.name}(")
                ),
                None,
            )
            if matched:
                metric_columns.append(matched)
        summaries = {column: summarize_column(details[column]) for column in metric_columns}

        from agent.config import get_agent_config

        project_config = get_agent_config()
        code_files = [
            Path(__file__).resolve(),
            SCRIPT_DIR / "ragas_smoke_test.py",
            SCRIPT_DIR / "adapters" / "project_rag.py",
            PROJECT_DIR / "backend" / "agent" / "rag" / "rag_engine.py",
            PROJECT_DIR / "backend" / "agent" / "rag" / "hybrid.py",
            PROJECT_DIR / "backend" / "agent" / "rag" / "rewriter.py",
            PROJECT_DIR / "backend" / "agent" / "rag" / "reranker.py",
        ]
        summary = {
            "schema_version": 1,
            "experiment": "step_6_full_ragas_pcb_nasa",
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "duration_seconds": (finished_at - started_at).total_seconds(),
            "dataset": {
                "path": str(csv_path.relative_to(PROJECT_DIR)),
                "rows": rows,
                "sha256": sha256_file(csv_path),
            },
            "configuration": {
                "top_k": args.top_k,
                "candidate_k": args.top_k * 8,
                "rewrite_queries": project_config.rag_rewrite_queries,
                "hybrid_enabled": bool(engine._hybrid_enabled),
                "char_weight": float(engine._char_weight),
                "llm_reranker_enabled": engine._reranker is not None,
                "vector_enabled": bool(engine._vector_enabled),
                "target": {
                    "host": endpoint_host(target_config),
                    "model": target_config["model"],
                },
                "judge": {
                    "host": endpoint_host(judge_config),
                    "model": judge_config["model"],
                },
                "embedding": {
                    "host": endpoint_host(embedding_config),
                    "model": embedding_config["model"],
                    "check_embedding_ctx_length": False,
                },
                "ragas_max_workers": workers,
                "ragas_timeout_seconds": timeout,
                "answer_relevancy_strictness": 1,
                "seed": 42,
            },
            "metrics": summaries,
            "thresholds": {
                "faithfulness": {"operator": ">", "value": 0.8},
                "answer_relevancy": {"operator": ">", "value": 0.8},
                "context_recall": {"operator": ">", "value": 0.7},
            },
            "threshold_results": {
                "faithfulness": bool((summaries.get("faithfulness", {}).get("mean") or 0) > 0.8),
                "answer_relevancy": bool((summaries.get("answer_relevancy", {}).get("mean") or 0) > 0.8),
                "context_recall": bool((summaries.get("context_recall", {}).get("mean") or 0) > 0.7),
            },
            "code": {
                "git_commit": git_text("rev-parse", "HEAD") or None,
                "git_worktree_dirty": bool(git_text("status", "--porcelain")),
                "files_sha256": {
                    str(path.relative_to(PROJECT_DIR)): sha256_file(path) for path in code_files
                },
                "python": sys.version.split()[0],
                "platform": platform.platform(),
            },
        }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    csv_output = RESULTS_DIR / f"ragas_full_pcb_nasa_{timestamp}.csv"
    summary_output = RESULTS_DIR / f"ragas_full_pcb_nasa_{timestamp}_summary.json"
    details.to_csv(csv_output, index=False, encoding="utf-8-sig")
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n第 6 步完整 RAGAS 实验完成：")
    for name, stats in summaries.items():
        mean = stats["mean"]
        rendered = "无有效结果" if mean is None else f"{mean:.4f}"
        print(f"  {name}: {rendered}（有效 {stats['valid_count']}/{rows}）")
    print(f"逐条结果：{csv_output}")
    print(f"摘要结果：{summary_output}")


if __name__ == "__main__":
    main()
