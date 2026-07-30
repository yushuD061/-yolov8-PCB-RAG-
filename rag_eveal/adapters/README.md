# RagEngine -> RAGAS 适配器

`ProjectRagAdapter` 是项目 RAG 与评估框架之间的唯一映射入口。

## 输入 CSV

必须包含：

```text
chunk_id,hierarchy,title,content,keywords,question_predict,relevant_doc_ids,reference_answer
```

适配器会检查空数据、重复 Chunk ID、重复问题、空问题/答案、无效 JSON 引用和未知文档 ID。

## 输出字段

每条样本固定输出：

```text
user_input
response
retrieved_contexts
reference
retrieved_context_ids
reference_context_ids
```

- `response` 和 `retrieved_contexts` 来自真实 `RagEngine.query()`。
- `retrieved_contexts` 保留实际检索到的全部上下文。
- `retrieved_context_ids` 按文档 ID 去重，避免一个文档的多个子块重复影响 ID 指标。
- `reference` 和 `reference_context_ids` 来自黄金 CSV。

## 使用

```python
from adapters.project_rag import ProjectRagAdapter

with ProjectRagAdapter.from_csv(
    "rag_eveal/pcb_nasa_evaluation.csv",
    top_k=3,
) as adapter:
    # 调用方应先按项目真实配置给 adapter.engine 注入生成、改写和精排函数。
    evaluation_dataset = adapter.to_evaluation_dataset(limit=3)
```

当前 `ragas_smoke_test.py` 已使用该适配器，不再单独维护字段映射代码。

## 隔离和可复现性

- 索引文件名包含 CSV 名称和规范字段内容的 SHA-256 短版本号。
- 索引使用完整 CSV 语料建立，即使只评估前 N 条也不会缩小检索语料。
- `question_predict` 不参与入库，避免问题泄漏。
- `close()` 和上下文管理器会显式释放 SQLite 连接。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover `
  -s .\rag_eveal\tests `
  -p "test_*.py" -v
```
