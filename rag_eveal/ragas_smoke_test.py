"""使用当前 CSV 和项目 RagEngine 运行小规模 RAGAS Smoke Test。"""

from __future__ import annotations

import argparse
import os
import re
import sys
import types
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
DEFAULT_CSV_PATH = SCRIPT_DIR / "rag_evaluation.csv"
RESULTS_DIR = SCRIPT_DIR / "results"


def _install_ragas_compatibility_shim() -> None:
    """兼容 RAGAS 0.4.3 与新版 langchain-community 的可选 Vertex 导入。

    RAGAS 会在顶层导入已从 langchain-community 0.4 移除的 Vertex 模块，
    即使本评估仅使用 OpenAI 兼容模型。此占位类不会参与实际模型调用。
    """
    module_name = "langchain_community.chat_models.vertexai"
    try:
        __import__(module_name)
    except ModuleNotFoundError:
        module = types.ModuleType(module_name)
        module.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules[module_name] = module


_install_ragas_compatibility_shim()

from langchain_openai import ChatOpenAI, OpenAIEmbeddings  # noqa: E402
from ragas import EvaluationDataset, evaluate  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import (  # noqa: E402
    FactualCorrectness,
    Faithfulness,
    IDBasedContextPrecision,
    IDBasedContextRecall,
    LLMContextRecall,
    ResponseRelevancy,
)
from ragas.run_config import RunConfig  # noqa: E402


load_dotenv(SCRIPT_DIR / ".env.ragas")
# Smoke Test 使用完整 CSV 构建隔离的稀疏检索库，避免依赖外部向量库状态。
os.environ["RAG_VECTOR_ENABLED"] = "false"
sys.path.insert(0, str(BACKEND_DIR))

from agent.rag.rag_engine import RagEngine  # noqa: E402
from services.llm_service import call_llm_api  # noqa: E402


from adapters.project_rag import ProjectRagAdapter  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAGAS Smoke Test")
    parser.add_argument("--limit", type=int, default=3, help="评估样例数")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="评估 CSV；相对路径按当前工作目录解析",
    )
    parser.add_argument(
        "--id-only",
        action="store_true",
        help="只运行不调用裁判模型的 ID 检索指标",
    )
    return parser.parse_args()


def env_config(prefix: str) -> dict[str, str]:
    return {
        "endpoint": os.getenv(f"{prefix}_BASE_URL", ""),
        "apiKey": os.getenv(f"{prefix}_API_KEY", ""),
        "model": os.getenv(f"{prefix}_MODEL", ""),
    }


def require_config(config: dict[str, str], label: str) -> None:
    missing = [key for key, value in config.items() if not value]
    if missing:
        raise RuntimeError(f"{label} 缺少配置: {', '.join(missing)}")
    endpoint = config["endpoint"]
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"{label} endpoint 不是合法的 HTTP(S) URL: {endpoint}")


def configure_target(engine: RagEngine, config: dict[str, str]) -> None:
    def generate(system_prompt: str, user_message: str) -> str:
        return call_llm_api(config, system_prompt, user_message, temperature=0.0)

    engine.set_generate_fn(generate)
    engine.set_rewriter(generate)
    from agent.config import get_agent_config

    if get_agent_config().rag_reranker_enabled:
        engine.set_reranker(generate)


def langchain_base_url(value: str) -> str:
    return re.sub(r"/chat/completions/?$", "", value.rstrip("/"))


def main() -> None:
    args = parse_args()
    if args.limit <= 0:
        raise ValueError("--limit 必须大于 0")

    csv_path = args.csv_path.resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(f"评估 CSV 不存在: {csv_path}")
    adapter = ProjectRagAdapter.from_csv(csv_path, top_k=args.top_k)
    engine = adapter.engine
    print(f"评估数据集：{csv_path}（{len(adapter.dataframe)} 条）")
    target_config = env_config("OPENAI")
    require_config(target_config, "被测 RAG 模型")
    configure_target(engine, target_config)
    samples = adapter.collect(min(args.limit, len(adapter.dataframe)))

    metrics = [IDBasedContextPrecision(), IDBasedContextRecall()]
    evaluator_llm = None
    if not args.id_only:
        judge_config = env_config("JUDGE")
        require_config(judge_config, "RAGAS 裁判模型")
        embedding_config = env_config("EVAL_EMBEDDING")
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
            # SiliconFlow 的 Qwen Embedding 接口接收原始文本，不接收 token ID 数组。
            check_embedding_ctx_length=False,
        )
        evaluator_embeddings = LangchainEmbeddingsWrapper(embedding_model)
        metrics.extend(
            [
                Faithfulness(),
                FactualCorrectness(language="chinese"),
                LLMContextRecall(),
                ResponseRelevancy(
                    llm=evaluator_llm,
                    embeddings=evaluator_embeddings,
                    # SiliconFlow 的 OpenAI 兼容接口当前仅支持 n=1。
                    strictness=1,
                ),
            ]
        )

    dataset = EvaluationDataset.from_list(samples, name="ragas-smoke-test")
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=evaluator_llm,
        run_config=RunConfig(
            timeout=int(os.getenv("RAGAS_TIMEOUT", "120")),
            max_retries=2,
            max_workers=int(os.getenv("RAGAS_MAX_WORKERS", "2")),
            seed=42,
        ),
        experiment_name="ragas-smoke-test",
        raise_exceptions=True,
        show_progress=True,
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = RESULTS_DIR / f"ragas_smoke_{csv_path.stem}_{timestamp}.csv"
    details = result.to_pandas()
    details.to_csv(output_path, index=False, encoding="utf-8-sig")
    metric_columns: list[str] = []
    for metric in metrics:
        # 带参数的指标会输出形如 factual_correctness(mode=f1) 的列名。
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
    summary = {name: float(details[name].mean()) for name in metric_columns}
    print("\nRAGAS Smoke Test 完成：")
    for name, score in summary.items():
        print(f"  {name}: {score:.4f}")
    thresholds = {
        "faithfulness": 0.8,
        "answer_relevancy": 0.8,
        "context_recall": 0.7,
    }
    print("验收阈值（严格大于）：")
    for name, threshold in thresholds.items():
        score = summary.get(name)
        passed = score is not None and score > threshold
        rendered = f"{score:.4f}" if score is not None else "缺失"
        print(f"  {'PASS' if passed else 'FAIL'} {name}: {rendered} > {threshold:.1f}")
    print(f"明细结果：{output_path}")


if __name__ == "__main__":
    main()
