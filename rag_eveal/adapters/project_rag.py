"""把项目 ``RagEngine`` 的输入输出转换为 RAGAS 单轮样本。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Protocol, TypedDict

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# 评估默认使用隔离 SQLite + 稀疏检索。调用方如需评估向量链路，应在导入前显式覆盖。
os.environ.setdefault("RAG_VECTOR_ENABLED", "false")

from agent.rag.rag_engine import RagEngine  # noqa: E402


REQUIRED_COLUMNS = {
    "chunk_id",
    "hierarchy",
    "title",
    "content",
    "keywords",
    "question_predict",
    "relevant_doc_ids",
    "reference_answer",
}


class RagasSingleTurnSample(TypedDict):
    user_input: str
    response: str
    retrieved_contexts: list[str]
    reference: str
    retrieved_context_ids: list[str]
    reference_context_ids: list[str]


class RagQueryEngine(Protocol):
    def query(self, question: str) -> tuple[str, list[dict[str, Any]]]: ...


def parse_relevant_doc_ids(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"relevant_doc_ids 不是合法 JSON 数组: {value}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ValueError(f"relevant_doc_ids 必须是非空 JSON 数组: {value}")
    result = list(dict.fromkeys(str(item).strip() for item in parsed if str(item).strip()))
    if not result:
        raise ValueError(f"relevant_doc_ids 不得为空: {value}")
    return result


def normalize_content(value: str) -> str:
    return re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE).strip()


def load_evaluation_rows(csv_path: Path | str) -> pd.DataFrame:
    path = Path(csv_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"评估 CSV 不存在: {path}")
    dataframe = pd.read_csv(path, dtype=str).fillna("")
    missing = REQUIRED_COLUMNS.difference(dataframe.columns)
    if missing:
        raise ValueError(f"CSV 缺少字段: {', '.join(sorted(missing))}")
    if dataframe.empty:
        raise ValueError("评估 CSV 为空")
    if dataframe["chunk_id"].duplicated().any():
        raise ValueError("chunk_id 必须唯一")
    if dataframe["question_predict"].duplicated().any():
        raise ValueError("question_predict 必须唯一")

    known_ids = set(dataframe["chunk_id"])
    for row in dataframe.itertuples(index=False):
        unknown = set(parse_relevant_doc_ids(row.relevant_doc_ids)).difference(known_ids)
        if unknown:
            raise ValueError(f"{row.chunk_id} 引用了未知文档 ID: {sorted(unknown)}")
        if not row.question_predict.strip():
            raise ValueError(f"{row.chunk_id} 的 question_predict 为空")
        if not row.reference_answer.strip():
            raise ValueError(f"{row.chunk_id} 的 reference_answer 为空")
    return dataframe


def dataframe_version(dataframe: pd.DataFrame) -> str:
    payload = dataframe[list(sorted(REQUIRED_COLUMNS))].to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def build_isolated_engine(
    dataframe: pd.DataFrame,
    *,
    csv_path: Path | str,
    top_k: int = 3,
    data_dir: Path | str = SCRIPT_DIR / "data",
) -> RagEngine:
    """用完整 CSV 语料建立版本化隔离索引，问题列绝不参与入库。"""
    if top_k <= 0:
        raise ValueError("top_k 必须大于 0")
    path = Path(csv_path).resolve()
    dataset_name = re.sub(r"[^A-Za-z0-9_-]+", "_", path.stem)
    db_path = Path(data_dir).resolve() / (
        f"ragas_adapter_{dataset_name}_{dataframe_version(dataframe)}.db"
    )
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = RagEngine(db_path=str(db_path), top_k=top_k)
    if not engine.loaded:
        for row in dataframe.itertuples(index=False):
            searchable_text = "\n".join(
                [
                    f"Hierarchy: {row.hierarchy}",
                    f"Title: {row.title}",
                    f"Keywords: {row.keywords}",
                    normalize_content(row.content),
                ]
            )
            engine.ingest(searchable_text, doc_name=row.chunk_id)
        print(f"已建立 RAGAS 隔离索引：{len(dataframe)} 条，{db_path.name}")
    return engine


class ProjectRagAdapter:
    """执行真实项目 RAG，并产出 RAGAS ``SingleTurnSample`` 字段。"""

    def __init__(self, engine: RagQueryEngine, dataframe: pd.DataFrame):
        self.engine = engine
        self.dataframe = dataframe.reset_index(drop=True).copy()

    @classmethod
    def from_csv(
        cls,
        csv_path: Path | str,
        *,
        top_k: int = 3,
        data_dir: Path | str = SCRIPT_DIR / "data",
    ) -> "ProjectRagAdapter":
        dataframe = load_evaluation_rows(csv_path)
        engine = build_isolated_engine(
            dataframe,
            csv_path=csv_path,
            top_k=top_k,
            data_dir=data_dir,
        )
        return cls(engine, dataframe)

    @staticmethod
    def _unique_source_ids(sources: list[dict[str, Any]]) -> list[str]:
        return list(
            dict.fromkeys(
                str(source.get("doc_name", "")).strip()
                for source in sources
                if str(source.get("doc_name", "")).strip()
            )
        )

    def invoke(self, row: Any) -> RagasSingleTurnSample:
        question = str(row.question_predict)
        answer, sources = self.engine.query(question)
        return {
            "user_input": question,
            "response": str(answer),
            # 保留 RagEngine 实际交给回答链路的全部来源上下文。
            "retrieved_contexts": [str(source.get("content", "")) for source in sources],
            "reference": str(row.reference_answer),
            # ID 指标按文档判断，重复命中同一文档只计一次。
            "retrieved_context_ids": self._unique_source_ids(sources),
            "reference_context_ids": parse_relevant_doc_ids(row.relevant_doc_ids),
        }

    def collect(self, limit: int = 0) -> list[RagasSingleTurnSample]:
        if limit < 0:
            raise ValueError("limit 不得小于 0")
        selected = self.dataframe.head(limit) if limit else self.dataframe
        samples: list[RagasSingleTurnSample] = []
        for index, row in enumerate(selected.itertuples(index=False), start=1):
            print(f"[{index}/{len(selected)}] 运行项目 RAG：{row.question_predict}")
            samples.append(self.invoke(row))
        return samples

    def to_evaluation_dataset(self, limit: int = 0, *, name: str = "project-rag"):
        """延迟导入 RAGAS，使无 LLM/无 RAGAS 的单元测试仍可测试映射逻辑。"""
        from ragas import EvaluationDataset

        return EvaluationDataset.from_list(self.collect(limit), name=name)

    def close(self) -> None:
        close = getattr(self.engine, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> "ProjectRagAdapter":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
