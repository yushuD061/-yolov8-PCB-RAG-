from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


RAG_EVAL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAG_EVAL_DIR))

from adapters.project_rag import (  # noqa: E402
    ProjectRagAdapter,
    build_isolated_engine,
    load_evaluation_rows,
)


class FakeEngine:
    def query(self, question: str):
        return "答案", [
            {"doc_name": "doc-1", "content": "上下文 A"},
            {"doc_name": "doc-1", "content": "上下文 B"},
            {"doc_name": "doc-2", "content": "上下文 C"},
        ]


def sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "chunk_id": "doc-1",
                "hierarchy": "Source > Page 1",
                "title": "Title 1",
                "content": "Alpha source content.",
                "keywords": "alpha",
                "question_predict": "Alpha 是什么？",
                "relevant_doc_ids": json.dumps(["doc-1"]),
                "reference_answer": "Alpha 的参考答案。",
            },
            {
                "chunk_id": "doc-2",
                "hierarchy": "Source > Page 2",
                "title": "Title 2",
                "content": "Beta source content.",
                "keywords": "beta",
                "question_predict": "Beta 是什么？",
                "relevant_doc_ids": json.dumps(["doc-2"]),
                "reference_answer": "Beta 的参考答案。",
            },
        ]
    )


class ProjectRagAdapterTests(unittest.TestCase):
    def test_maps_engine_output_to_ragas_fields_and_deduplicates_ids(self):
        adapter = ProjectRagAdapter(FakeEngine(), sample_dataframe())
        sample = adapter.collect(limit=1)[0]
        self.assertEqual(
            set(sample),
            {
                "user_input",
                "response",
                "retrieved_contexts",
                "reference",
                "retrieved_context_ids",
                "reference_context_ids",
            },
        )
        self.assertEqual(sample["retrieved_context_ids"], ["doc-1", "doc-2"])
        self.assertEqual(len(sample["retrieved_contexts"]), 3)
        self.assertEqual(sample["reference_context_ids"], ["doc-1"])

    def test_load_and_isolated_index_never_ingest_question_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path = root / "evaluation.csv"
            sample_dataframe().to_csv(csv_path, index=False, encoding="utf-8")
            dataframe = load_evaluation_rows(csv_path)
            engine = build_isolated_engine(
                dataframe,
                csv_path=csv_path,
                top_k=2,
                data_dir=root / "data",
            )
            stored = "\n".join(chunk.content for chunk in engine.store.get_all_chunks())
            self.assertIn("Alpha source content", stored)
            self.assertNotIn("Alpha 是什么", stored)
            ProjectRagAdapter(engine, dataframe).close()


if __name__ == "__main__":
    unittest.main()
