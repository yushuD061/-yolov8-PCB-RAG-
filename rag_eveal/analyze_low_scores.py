"""执行第 7 步：筛选低分样本并重复裁判代表性样本。"""

from __future__ import annotations

import argparse
import ast
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ragas_smoke_test import (
    EvaluationDataset,
    FactualCorrectness,
    Faithfulness,
    LLMContextRecall,
    LangchainEmbeddingsWrapper,
    LangchainLLMWrapper,
    OpenAIEmbeddings,
    ResponseRelevancy,
    RunConfig,
    ChatOpenAI,
    env_config,
    evaluate,
    langchain_base_url,
    require_config,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
RESULTS_DIR = SCRIPT_DIR / "results"
DEFAULT_FULL_RESULT = RESULTS_DIR / "ragas_full_pcb_nasa_20260717_185147.csv"
DEFAULT_DATASET = SCRIPT_DIR / "pcb_nasa_evaluation.csv"
DEFAULT_ID_RESULT = RESULTS_DIR / "id_metrics_pcb_nasa_20260717_184133.json"
CORE_COLUMNS = ["faithfulness", "answer_relevancy", "context_recall"]
REPEAT_COLUMNS = [
    "faithfulness",
    "factual_correctness(mode=f1)",
    "context_recall",
    "answer_relevancy",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAGAS 第 7 步低分与稳定性分析")
    parser.add_argument("--full-result", type=Path, default=DEFAULT_FULL_RESULT)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--id-result", type=Path, default=DEFAULT_ID_RESULT)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--samples", type=int, default=5)
    return parser.parse_args()


def parse_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if pd.isna(value):
        return []
    parsed = ast.literal_eval(str(value))
    if not isinstance(parsed, list):
        raise ValueError(f"字段不是列表: {value}")
    return [str(item) for item in parsed]


def enrich_results(full_path: Path, dataset_path: Path) -> pd.DataFrame:
    full = pd.read_csv(full_path, encoding="utf-8-sig")
    dataset = pd.read_csv(dataset_path, dtype=str, encoding="utf-8-sig").fillna("")
    mapping = dict(zip(dataset["question_predict"], dataset["chunk_id"]))
    full.insert(0, "sample_id", full["user_input"].map(mapping))
    if full["sample_id"].isna().any():
        raise ValueError("完整结果中存在无法映射回评估数据集的问题")
    return full


def choose_representatives(dataframe: pd.DataFrame, limit: int) -> pd.DataFrame:
    candidates: list[tuple[str, pd.Series]] = []

    def add(reason: str, subset: pd.DataFrame, sort: list[str]) -> None:
        if subset.empty:
            return
        selected = subset.sort_values(sort, na_position="first").iloc[0]
        if selected["sample_id"] not in {row["sample_id"] for _, row in candidates}:
            candidates.append((reason, selected))

    judge_missing = dataframe[dataframe[REPEAT_COLUMNS].isna().any(axis=1)]
    add("judge_missing", judge_missing, ["sample_id"])
    retrieval_failure = dataframe[dataframe["id_based_context_recall"] == 0]
    add("retrieval_failure", retrieval_failure, ["context_recall", "faithfulness"])
    hit_low_context = dataframe[
        (dataframe["id_based_context_recall"] == 1)
        & (dataframe["context_recall"] <= 0.7)
    ]
    add("retrieval_hit_low_context", hit_low_context, ["context_recall", "faithfulness"])
    low_answer = dataframe[
        (dataframe["id_based_context_recall"] == 1)
        & (dataframe["answer_relevancy"] <= 0.8)
    ]
    add("low_answer_relevancy", low_answer, ["answer_relevancy", "faithfulness"])
    factual_conflict = dataframe[
        (dataframe["id_based_context_recall"] == 1)
        & (dataframe["faithfulness"] >= 0.8)
        & (dataframe["answer_relevancy"] >= 0.8)
        & (dataframe["factual_correctness(mode=f1)"] <= 0.25)
    ]
    add(
        "factual_correctness_conflict",
        factual_conflict,
        ["factual_correctness(mode=f1)", "context_recall"],
    )

    low_union = dataframe[
        (dataframe["faithfulness"] <= 0.8)
        | (dataframe["answer_relevancy"] <= 0.8)
        | (dataframe["context_recall"] <= 0.7)
        | dataframe[CORE_COLUMNS].isna().any(axis=1)
    ].sort_values(["context_recall", "faithfulness"], na_position="first")
    for _, row in low_union.iterrows():
        if len(candidates) >= limit:
            break
        if row["sample_id"] not in {item["sample_id"] for _, item in candidates}:
            candidates.append(("additional_low_score", row))

    selected = pd.DataFrame([row for _, row in candidates[:limit]]).reset_index(drop=True)
    selected.insert(1, "selection_reason", [reason for reason, _ in candidates[:limit]])
    return selected


def build_repeat_samples(selected: pd.DataFrame, repeats: int) -> tuple[list[dict], list[dict]]:
    samples: list[dict] = []
    metadata: list[dict] = []
    for _, row in selected.iterrows():
        for repeat in range(1, repeats + 1):
            samples.append(
                {
                    "user_input": str(row["user_input"]),
                    "response": str(row["response"]),
                    "retrieved_contexts": parse_list(row["retrieved_contexts"]),
                    "reference": str(row["reference"]),
                }
            )
            metadata.append(
                {
                    "sample_id": row["sample_id"],
                    "selection_reason": row["selection_reason"],
                    "repeat": repeat,
                }
            )
    return samples, metadata


def run_stability(selected: pd.DataFrame, repeats: int) -> pd.DataFrame:
    judge_config = env_config("JUDGE")
    embedding_config = env_config("EVAL_EMBEDDING")
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
    embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(
            model=embedding_config["model"],
            api_key=embedding_config["apiKey"],
            base_url=langchain_base_url(embedding_config["endpoint"]),
            max_retries=2,
            check_embedding_ctx_length=False,
        )
    )
    metrics = [
        Faithfulness(),
        FactualCorrectness(language="chinese"),
        LLMContextRecall(),
        ResponseRelevancy(llm=evaluator_llm, embeddings=embeddings, strictness=1),
    ]
    samples, metadata = build_repeat_samples(selected, repeats)
    result = evaluate(
        dataset=EvaluationDataset.from_list(samples, name="judge-stability-pcb-nasa"),
        metrics=metrics,
        llm=evaluator_llm,
        run_config=RunConfig(
            timeout=int(os.getenv("RAGAS_TIMEOUT", "120")),
            max_retries=2,
            max_workers=int(os.getenv("RAGAS_MAX_WORKERS", "2")),
            seed=42,
        ),
        experiment_name=f"judge-stability-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        raise_exceptions=False,
        show_progress=True,
    )
    details = result.to_pandas().reset_index(drop=True)
    if len(details) != len(metadata):
        raise RuntimeError("重复裁判结果行数与输入不一致")
    return pd.concat([pd.DataFrame(metadata), details], axis=1)


def attach_statistics(details: pd.DataFrame) -> pd.DataFrame:
    output = details.copy()
    for column in REPEAT_COLUMNS:
        grouped = details.groupby("sample_id")[column]
        output[f"{column}_mean"] = output["sample_id"].map(grouped.mean())
        output[f"{column}_min"] = output["sample_id"].map(grouped.min())
        output[f"{column}_max"] = output["sample_id"].map(grouped.max())
        output[f"{column}_range"] = output[f"{column}_max"] - output[f"{column}_min"]
        output[f"{column}_std"] = output["sample_id"].map(lambda value: grouped.get_group(value).std(ddof=0))
        output[f"{column}_valid_count"] = output["sample_id"].map(grouped.count())
    return output


def stability_lookup(details: pd.DataFrame) -> dict[str, dict[str, dict[str, float]]]:
    lookup: dict[str, dict[str, dict[str, float]]] = {}
    for sample_id, group in details.groupby("sample_id"):
        lookup[sample_id] = {}
        for column in REPEAT_COLUMNS:
            valid = pd.to_numeric(group[column], errors="coerce").dropna()
            lookup[sample_id][column] = {
                "mean": float(valid.mean()) if not valid.empty else float("nan"),
                "range": float(valid.max() - valid.min()) if not valid.empty else float("nan"),
                "std": float(valid.std(ddof=0)) if not valid.empty else float("nan"),
                "valid": int(valid.count()),
            }
    return lookup


def causes_for(row: pd.Series, offline_ids: list[str], stability: dict[str, Any] | None) -> list[str]:
    causes: list[str] = []
    retrieved = set(parse_list(row["retrieved_context_ids"]))
    reference = set(parse_list(row["reference_context_ids"]))
    offline_hit = bool(reference.intersection(offline_ids))
    if row[REPEAT_COLUMNS].isna().any():
        causes.append("裁判或运行异常：至少一个 LLM 指标缺失")
    if not reference.intersection(retrieved):
        causes.append(
            "查询改写/精排失败：离线 Top-3 曾命中但完整链路将正确文档挤出"
            if offline_hit
            else "基础检索失败：离线与完整链路均未召回正确文档"
        )
    if pd.notna(row["context_recall"]) and row["context_recall"] <= 0.7 and reference.intersection(retrieved):
        causes.append("ID 已命中但事实覆盖不足，或 Context Recall 裁判与文档 ID 标注不一致")
    if pd.notna(row["faithfulness"]) and row["faithfulness"] <= 0.8:
        causes.append("回答可能包含检索上下文无法充分支持的扩写")
    if pd.notna(row["answer_relevancy"]) and row["answer_relevancy"] <= 0.8:
        causes.append("回答不够直接，或 Answer Relevancy 裁判异常")
    factual = row["factual_correctness(mode=f1)"]
    if (
        pd.notna(factual)
        and factual <= 0.25
        and pd.notna(row["faithfulness"])
        and row["faithfulness"] >= 0.8
        and pd.notna(row["answer_relevancy"])
        and row["answer_relevancy"] >= 0.8
    ):
        causes.append("Factual Correctness 与其他指标冲突：检查参考答案或中文裁判")
    if stability and any(
        stats["valid"] >= 2 and (stats["range"] >= 0.3 or stats["std"] >= 0.15)
        for stats in stability.values()
    ):
        causes.append("重复裁判方差较大：该样本的 LLM 指标不稳定")
    return causes or ["需人工复核，当前自动规则无法确定单一原因"]


def compact(value: Any, limit: int = 1200) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def write_report(
    full: pd.DataFrame,
    stability_details: pd.DataFrame,
    id_result_path: Path,
    output_path: Path,
) -> None:
    id_payload = json.loads(id_result_path.read_text(encoding="utf-8"))
    offline = {
        item["sample_id"]: item["retrieved_context_ids"] for item in id_payload["samples"]
    }
    stability = stability_lookup(stability_details)
    low = full[
        (full["faithfulness"] <= 0.8)
        | (full["answer_relevancy"] <= 0.8)
        | (full["context_recall"] <= 0.7)
        | full[CORE_COLUMNS].isna().any(axis=1)
    ].copy()
    unstable_samples = sum(
        any(v["valid"] >= 2 and (v["range"] >= 0.3 or v["std"] >= 0.15) for v in metrics.values())
        for metrics in stability.values()
    )
    lines = [
        "# RAGAS 第 7 步低分与裁判稳定性报告",
        "",
        f"> 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
        "> 范围：43 条完整结果；代表性样本 5 条，每条重复裁判 3 次。",
        "",
        "## 1. 低分概览",
        "",
        "| 条件 | 样本数 | 缺失数 |",
        "|---|---:|---:|",
        f"| Faithfulness <= 0.8 | {int((full['faithfulness'] <= 0.8).sum())} | {int(full['faithfulness'].isna().sum())} |",
        f"| Answer Relevancy <= 0.8 | {int((full['answer_relevancy'] <= 0.8).sum())} | {int(full['answer_relevancy'].isna().sum())} |",
        f"| Context Recall <= 0.7 | {int((full['context_recall'] <= 0.7).sum())} | {int(full['context_recall'].isna().sum())} |",
        f"| 任一条件命中或核心指标缺失（去重） | {len(low)} | - |",
        "",
        "## 2. 重复裁判稳定性",
        "",
        f"代表样本中有 **{unstable_samples}** 条至少一个指标满足极差 >= 0.3 或标准差 >= 0.15，视为不稳定。",
        "",
        "| Sample ID | 选择原因 | 指标 | 均值 | 极差 | 标准差 | 有效次数 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    reasons = stability_details.drop_duplicates("sample_id").set_index("sample_id")["selection_reason"]
    for sample_id, metrics in stability.items():
        for metric, stats in metrics.items():
            lines.append(
                f"| {sample_id} | {reasons[sample_id]} | {metric} | "
                f"{stats['mean']:.4f} | {stats['range']:.4f} | {stats['std']:.4f} | {stats['valid']} |"
            )
    lines.extend(
        [
            "",
            "## 3. 全量低分样本",
            "",
            "以下归因是基于 ID 命中、离线检索对照、指标组合和重复裁判方差的初步诊断；需要在修改 RAG 或参考答案前人工复核原文。",
            "",
        ]
    )
    for _, row in low.sort_values("sample_id").iterrows():
        sample_id = row["sample_id"]
        causes = causes_for(row, offline.get(sample_id, []), stability.get(sample_id))
        lines.extend(
            [
                f"### {sample_id}",
                "",
                f"- 问题：{compact(row['user_input'])}",
                f"- 标准 ID：`{parse_list(row['reference_context_ids'])}`",
                f"- 完整链路召回 ID：`{parse_list(row['retrieved_context_ids'])}`",
                f"- 离线 Top-3 ID：`{offline.get(sample_id, [])}`",
                f"- 分数：Faithfulness={row['faithfulness']}；Answer Relevancy={row['answer_relevancy']}；Context Recall={row['context_recall']}；Factual Correctness={row['factual_correctness(mode=f1)']}",
                f"- 初步归因：{'；'.join(causes)}",
                f"- 回答：{compact(row['response'])}",
                f"- 参考答案：{compact(row['reference'])}",
                "",
            ]
        )
    lines.extend(
        [
            "## 4. 建议修复顺序",
            "",
            "1. 先修复离线与完整链路均未命中的基础检索样本。",
            "2. 对离线命中但完整链路丢失的样本检查查询改写和 LLM reranker 排序。",
            "3. 对 ID 命中但 Context Recall 低的样本核查实际返回块、参考答案事实跨度和裁判提示词。",
            "4. 收紧回答提示词，减少上下文外扩写，并要求逐项覆盖问题中的限定条件。",
            "5. 对高方差指标增加重复裁判或更换稳定裁判；Factual Correctness 在稳定前继续只作诊断，不设门禁。",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.repeats < 3:
        raise ValueError("第 7 步要求代表性样本至少重复 3 次")
    if args.samples < 3:
        raise ValueError("代表性样本数不得少于 3")
    full_path = args.full_result.resolve()
    dataset_path = args.dataset.resolve()
    id_path = args.id_result.resolve()
    for path in (full_path, dataset_path, id_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    full = enrich_results(full_path, dataset_path)
    selected = choose_representatives(full, args.samples)
    print("代表性样本：")
    for _, row in selected.iterrows():
        print(f"  {row['sample_id']}: {row['selection_reason']}")
    details = attach_statistics(run_stability(selected, args.repeats))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stability_path = RESULTS_DIR / f"judge_stability_{timestamp}.csv"
    report_path = RESULTS_DIR / f"ragas_low_scores_{timestamp}.md"
    details.to_csv(stability_path, index=False, encoding="utf-8-sig")
    write_report(full, details, id_path, report_path)
    print(f"稳定性结果：{stability_path}")
    print(f"低分报告：{report_path}")


if __name__ == "__main__":
    main()
