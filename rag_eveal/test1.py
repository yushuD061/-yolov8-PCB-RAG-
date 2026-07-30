"""用 LangSmith 评估项目 RAG 的检索与回答质量。

默认执行完整评估；使用 ``--local-retrieval-only`` 可在不访问 LangSmith、
不调用 LLM 的情况下检查 CSV、索引以及 TF-IDF 检索基线。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from langsmith import Client, evaluate
from langsmith.schemas import Example, Run


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
CSV_PATH = SCRIPT_DIR / "rag_evaluation.csv"
RESULTS_DIR = SCRIPT_DIR / "results"
REQUIRED_COLUMNS = {
    "chunk_id", "hierarchy", "title", "content", "keywords", "question_predict",
    "relevant_doc_ids", "reference_answer",
}
sys.path.insert(0, str(BACKEND_DIR))

# 评估库必须隔离于业务库。默认使用可复现的本地混合稀疏检索；显式配置后可叠加向量检索。
load_dotenv(SCRIPT_DIR / ".env.langsmith")
os.environ["RAG_VECTOR_ENABLED"] = os.getenv("RAG_EVAL_VECTOR_ENABLED", "true")
if os.environ["RAG_VECTOR_ENABLED"].strip().lower() in ("1", "true", "yes"):
    os.environ.setdefault("CHROMA_ENABLED", "true")
    os.environ.setdefault("CHROMA_PATH", str(SCRIPT_DIR / "data" / "chroma_evaluation"))
    os.environ.setdefault("CHROMA_COLLECTION", "rag_evaluation_chunks")

from agent.rag.rag_engine import RagEngine  # noqa: E402
from services.llm_service import call_llm_api  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LangSmith RAG evaluation")
    parser.add_argument("--dataset-name", default="rag_evaluation")
    parser.add_argument("--experiment-prefix", default="rag_evaluation experiment")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-concurrency", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0, help="只评估前 N 条；0 表示全部")
    parser.add_argument("--no-llm-judge", action="store_true", help="仅计算检索指标")
    parser.add_argument(
        "--local-retrieval-only",
        action="store_true",
        help="只运行本地 TF-IDF 检索基线，不访问 LangSmith/LLM",
    )
    return parser.parse_args()


def load_evaluation_rows(limit: int = 0) -> pd.DataFrame:
    dataframe = pd.read_csv(CSV_PATH, dtype=str).fillna("")
    missing = REQUIRED_COLUMNS.difference(dataframe.columns)
    if missing:
        raise ValueError(f"评估 CSV 缺少字段: {', '.join(sorted(missing))}")
    if dataframe.empty:
        raise ValueError("评估 CSV 为空")
    if dataframe["chunk_id"].duplicated().any():
        raise ValueError("评估 CSV 的 chunk_id 必须唯一")
    if dataframe["question_predict"].duplicated().any():
        raise ValueError("评估 CSV 的 question_predict 必须唯一")
    known_ids = set(dataframe["chunk_id"])
    for row in dataframe.itertuples(index=False):
        relevant_ids = parse_relevant_doc_ids(row.relevant_doc_ids)
        unknown = set(relevant_ids).difference(known_ids)
        if unknown:
            raise ValueError(f"{row.chunk_id} 的 relevant_doc_ids 包含未知 ID: {sorted(unknown)}")
        if not row.reference_answer.strip():
            raise ValueError(f"{row.chunk_id} 的 reference_answer 为空")
    return dataframe.head(limit).copy() if limit > 0 else dataframe


def csv_version() -> str:
    return hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()[:12]


def dataframe_version(dataframe: pd.DataFrame) -> str:
    payload = dataframe[list(sorted(REQUIRED_COLUMNS))].to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def llm_config(prefix: str = "OPENAI") -> dict[str, str]:
    return {
        "endpoint": os.getenv(f"{prefix}_BASE_URL", os.getenv("OPENAI_BASE_URL", "")),
        "apiKey": os.getenv(f"{prefix}_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        "model": os.getenv(f"{prefix}_MODEL", os.getenv("OPENAI_MODEL", "")),
        "inputCostPerMillion": os.getenv(
            f"{prefix}_INPUT_COST_PER_MILLION",
            os.getenv(
                "OPENAI_INPUT_COST_PER_MILLION",
                os.getenv("LLM_INPUT_COST_PER_MILLION", ""),
            ),
        ),
        "cachedInputCostPerMillion": os.getenv(
            f"{prefix}_CACHED_INPUT_COST_PER_MILLION",
            os.getenv(
                "OPENAI_CACHED_INPUT_COST_PER_MILLION",
                os.getenv("LLM_CACHED_INPUT_COST_PER_MILLION", ""),
            ),
        ),
        "outputCostPerMillion": os.getenv(
            f"{prefix}_OUTPUT_COST_PER_MILLION",
            os.getenv(
                "OPENAI_OUTPUT_COST_PER_MILLION",
                os.getenv("LLM_OUTPUT_COST_PER_MILLION", ""),
            ),
        ),
    }


def require_llm_config(config: dict[str, str]) -> None:
    missing = [key for key in ("endpoint", "apiKey", "model") if not config.get(key)]
    if missing:
        raise RuntimeError(
            "请在 rag_eveal/.env.langsmith 中设置 OPENAI_BASE_URL、"
            "OPENAI_API_KEY 和 OPENAI_MODEL。"
        )


def normalize_content(value: str) -> str:
    return re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE).strip()


def parse_relevant_doc_ids(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"relevant_doc_ids 不是合法 JSON 数组: {value}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ValueError(f"relevant_doc_ids 必须是非空 JSON 数组: {value}")
    result = [str(item).strip() for item in parsed if str(item).strip()]
    if not result:
        raise ValueError(f"relevant_doc_ids 不得为空: {value}")
    return list(dict.fromkeys(result))


def build_evaluation_engine(dataframe: pd.DataFrame, top_k: int) -> RagEngine:
    """建立无问题泄漏、与 CSV 版本绑定的隔离索引。"""
    version = dataframe_version(dataframe)
    vector_enabled = os.environ["RAG_VECTOR_ENABLED"].strip().lower() in ("1", "true", "yes")
    if vector_enabled:
        os.environ["CHROMA_COLLECTION"] = f"rag_evaluation_{version}"
    mode = "vector" if vector_enabled else "sparse"
    db_path = SCRIPT_DIR / "data" / f"evaluation_rag_{version}_{mode}.db"
    engine = RagEngine(db_path=str(db_path), top_k=top_k)
    if not engine.loaded:
        for row in dataframe.itertuples(index=False):
            # question_predict 是测试输入，严禁写入被测语料，否则会虚高召回率。
            searchable_text = "\n".join(
                [
                    f"Hierarchy: {row.hierarchy}",
                    f"Title: {row.title}",
                    f"Keywords: {row.keywords}",
                    normalize_content(row.content),
                ]
            )
            engine.ingest(searchable_text, doc_name=row.chunk_id)
        print(f"已建立隔离评估索引：{len(dataframe)} 条，{db_path.name}")
    return engine


def sync_dataset(client: Client, dataframe: pd.DataFrame, dataset_name: str) -> str:
    """创建或同步固定名称的数据集，使 Experiment 始终归属同一数据集。"""
    version = dataframe_version(dataframe)
    if client.has_dataset(dataset_name=dataset_name):
        dataset = client.read_dataset(dataset_name=dataset_name)
    else:
        dataset = client.create_dataset(
            dataset_name,
            description=f"PCB RAG evaluation set; data sha256={version}",
            metadata={
                "csv_sha256": csv_version(),
                "data_sha256": version,
                "rows": len(dataframe),
            },
        )

    existing_examples = list(client.list_examples(dataset_id=dataset.id))
    by_question: dict[str, Example] = {}
    for item in existing_examples:
        question = str((item.inputs or {}).get("question", ""))
        if question in by_question:
            raise RuntimeError(f"LangSmith 数据集中存在重复问题: {question}")
        by_question[question] = item

    current_questions = set(dataframe["question_predict"])
    stale_questions = set(by_question).difference(current_questions)
    if stale_questions:
        raise RuntimeError(
            f"LangSmith 数据集 {dataset_name} 含 {len(stale_questions)} 条 CSV 中不存在的旧问题。"
            "为避免误删远端数据，请清理旧样本或通过 --dataset-name 使用新数据集。"
        )

    created = 0
    updated = 0
    for row in dataframe.itertuples(index=False):
        inputs = {"question": row.question_predict}
        outputs = {
            "answer": row.reference_answer.strip(),
            "relevant_doc_ids": parse_relevant_doc_ids(row.relevant_doc_ids),
            "title": row.title,
            "keywords": row.keywords,
        }
        metadata = {
            "hierarchy": row.hierarchy,
            "chunk_id": row.chunk_id,
            "data_sha256": version,
        }
        existing = by_question.get(row.question_predict)
        if existing is None:
            client.create_example(
                inputs=inputs,
                outputs=outputs,
                metadata=metadata,
                dataset_id=dataset.id,
            )
            created += 1
        elif (
            existing.inputs != inputs
            or existing.outputs != outputs
            or any((existing.metadata or {}).get(key) != value for key, value in metadata.items())
        ):
            client.update_example(
                existing.id,
                inputs=inputs,
                outputs=outputs,
                metadata={**(existing.metadata or {}), **metadata},
                dataset_id=dataset.id,
            )
            updated += 1

    print(
        f"LangSmith 数据集已同步：{dataset_name}，总计 {len(dataframe)} 条，"
        f"新增 {created} 条，更新 {updated} 条。"
    )
    return dataset_name


def retrieval_scores(source_ids: list[str], relevant_ids: list[str]) -> dict[str, float]:
    relevant = set(relevant_ids)
    rank = next(
        (index for index, source_id in enumerate(source_ids, start=1) if source_id in relevant),
        0,
    )
    return {
        "retrieval_hit_at_1": float(rank == 1),
        "retrieval_hit_at_3": float(0 < rank <= 3),
        "retrieval_mrr": 1.0 / rank if rank else 0.0,
        "retrieval_context_precision": (
            sum(source_id in relevant for source_id in source_ids) / len(source_ids)
            if source_ids else 0.0
        ),
    }


def make_retrieval_evaluator(top_k: int):
    def retrieval_evaluator(run: Run, example: Example | None) -> dict[str, Any]:
        metric_keys = tuple(retrieval_scores([], []))
        if run.error:
            return {
                "results": [
                    {
                        "key": key,
                        "value": "target_error",
                        "comment": str(run.error)[:500],
                    }
                    for key in metric_keys
                ]
            }
        outputs = run.outputs or {}
        reference = example.outputs if example and example.outputs else {}
        sources = outputs.get("sources", [])[:top_k]
        source_ids = [str(source.get("doc_name", "")) for source in sources]
        relevant_ids = [str(item) for item in reference.get("relevant_doc_ids", [])]
        scores = retrieval_scores(source_ids, relevant_ids)
        comment = f"relevant={relevant_ids}; retrieved={source_ids}"
        return {
            "results": [
                {"key": key, "score": score, "comment": comment}
                for key, score in scores.items()
            ]
        }

    return retrieval_evaluator


def strip_json_fence(raw: str) -> str:
    value = (raw or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value)
    value = re.sub(r"\s*```$", "", value)
    return value.strip()


def extract_json_object(raw: str) -> dict[str, Any] | None:
    """从纯 JSON、代码块或带思考说明的模型输出中提取首个 JSON 对象。"""
    value = strip_json_fence(raw)
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", value):
        try:
            parsed, _ = decoder.raw_decode(value[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def clamp_score(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def make_llm_judge_evaluator(config: dict[str, str]):
    def llm_judge(run: Run, example: Example | None) -> dict[str, Any]:
        if run.error:
            return {
                "results": [
                    {
                        "key": key,
                        "value": "target_error",
                        "comment": str(run.error)[:500],
                    }
                    for key in ("correctness", "groundedness", "answer_relevance")
                ]
            }
        outputs = run.outputs or {}
        reference = example.outputs if example and example.outputs else {}
        question = (example.inputs or {}).get("question", "") if example else ""
        sources = outputs.get("sources", [])
        context = "\n\n".join(str(item.get("content", "")) for item in sources)
        payload = {
            "question": question,
            "reference_answer": reference.get("answer", ""),
            "retrieved_context": context,
            "candidate_answer": outputs.get("answer", ""),
        }
        system_prompt = (
            "你是严格的 RAG 评估器。只根据给定 JSON 评分，禁止补充外部知识。"
            "分别给出 0 到 1 的分数：correctness 表示相对参考答案的事实正确与完整程度；"
            "groundedness 表示候选答案中的事实是否都能由检索上下文支持；"
            "answer_relevance 表示是否直接、简洁地回答问题。"
            "只输出严格 JSON："
            '{"correctness":0.0,"groundedness":0.0,"answer_relevance":0.0,'
            '"reason":"一句话理由"}'
        )
        raw = call_llm_api(
            config,
            system_prompt,
            json.dumps(payload, ensure_ascii=False),
            max_tokens=1024,
            temperature=0.0,
        )
        judged = extract_json_object(raw)
        required_keys = ("correctness", "groundedness", "answer_relevance")
        if not judged or not set(required_keys).issubset(judged):
            # 裁判格式异常不应导致整个 LangSmith 实验报错，也不应伪装成 0 分。
            preview = re.sub(r"\s+", " ", raw).strip()[:300]
            return {
                "results": [
                    {
                        "key": key,
                        "value": "judge_parse_error",
                        "comment": f"无法解析裁判 JSON: {preview}",
                    }
                    for key in required_keys
                ]
            }
        reason = str(judged.get("reason", ""))
        return {
            "results": [
                {"key": key, "score": clamp_score(judged.get(key)), "comment": reason}
                for key in ("correctness", "groundedness", "answer_relevance")
            ]
        }

    return llm_judge


def configure_engine_llm(engine: RagEngine, config: dict[str, str]) -> None:
    def generate(system_prompt: str, user_message: str) -> str:
        return call_llm_api(config, system_prompt, user_message)

    engine.set_generate_fn(generate)
    # 与真实路由一致：启用多查询改写；是否精排仍由项目配置控制。
    engine.set_rewriter(generate)
    from agent.config import get_agent_config

    if get_agent_config().rag_reranker_enabled:
        engine.set_reranker(generate)


def run_local_retrieval(dataframe: pd.DataFrame, engine: RagEngine, top_k: int) -> None:
    totals = {key: 0.0 for key in retrieval_scores([], [])}
    failures: list[str] = []
    for row in dataframe.itertuples(index=False):
        hits = engine._deduplicate_hits(engine._search(row.question_predict, top_k * 2))[:top_k]
        source_ids = [hit.chunk.doc_name for hit in hits]
        relevant_ids = parse_relevant_doc_ids(row.relevant_doc_ids)
        scores = retrieval_scores(source_ids, relevant_ids)
        for key, score in scores.items():
            totals[key] += score
        if not scores["retrieval_hit_at_3"]:
            failures.append(f"{row.chunk_id}: {source_ids}")
    print("本地 TF-IDF 检索基线（不含 LLM 查询改写）：")
    for key, total in totals.items():
        print(f"  {key}: {total / len(dataframe):.4f}")
    if failures:
        print("Top-3 未命中样例（最多 10 条）：")
        for failure in failures[:10]:
            print(f"  {failure}")


def main() -> None:
    args = parse_args()
    if args.local_retrieval_only:
        # 本地基线必须完全离线，不调用 embedding 服务或外部向量库。
        os.environ["RAG_VECTOR_ENABLED"] = "false"
    dataframe = load_evaluation_rows(args.limit)
    engine = build_evaluation_engine(dataframe, args.top_k)
    if args.local_retrieval_only:
        run_local_retrieval(dataframe, engine, args.top_k)
        return

    target_config = llm_config()
    require_llm_config(target_config)
    configure_engine_llm(engine, target_config)

    client = Client()
    dataset_name = args.dataset_name
    if args.limit > 0:
        dataset_name = f"{dataset_name}-smoke-{args.limit}"
    dataset_name = sync_dataset(client, dataframe, dataset_name)

    def rag_target(inputs: dict[str, Any]) -> dict[str, Any]:
        answer, sources = engine.query(str(inputs["question"]))
        return {"answer": answer, "sources": sources}

    evaluators = [make_retrieval_evaluator(args.top_k)]
    if not args.no_llm_judge:
        judge_config = llm_config("JUDGE")
        require_llm_config(judge_config)
        evaluators.append(make_llm_judge_evaluator(judge_config))

    results = evaluate(
        rag_target,
        data=dataset_name,
        evaluators=evaluators,
        client=client,
        experiment_prefix=args.experiment_prefix,
        description="RAG retrieval + grounded answer evaluation without question leakage",
        metadata={
            "dataset_name": dataset_name,
            "csv_sha256": csv_version(),
            "top_k": args.top_k,
            "llm_judge": not args.no_llm_judge,
        },
        max_concurrency=max(0, args.max_concurrency),
        blocking=True,
        upload_results=True,
        error_handling="log",
    )
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / f"{results.experiment_name}.csv"
    results.to_pandas().to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"LangSmith 数据集：{dataset_name}")
    print(f"LangSmith Experiment：{results.experiment_name}")
    print(f"Experiment 地址：{results.url}")
    print(f"本地结果：{output_path}")


if __name__ == "__main__":
    main()
