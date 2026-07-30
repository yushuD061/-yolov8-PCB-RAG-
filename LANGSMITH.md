# LangSmith 接入说明

## 兼容版本

- 项目 Python：`3.11.9`
- 固定版本：`langsmith==0.10.2`
- 验证日期：2026-07-13
- 版本来源：使用 `uv pip install --dry-run langsmith` 从 PyPI 实时解析，并在项目 `.venv` 中完成安装和导入验证。

`requirements.txt` 与 `pyproject.toml` 均使用精确版本，避免不同机器解析到不同 LangSmith 版本。

## 安装

使用项目现有 `uv` 环境：

```powershell
$env:UV_CACHE_DIR='.uv-cache'
uv pip install --python .\.venv\Scripts\python.exe langsmith==0.10.2
```

或安装项目全部依赖：

```powershell
uv sync
```

## 配置

安装本身不会启用追踪，也不会自动上传项目数据。需要追踪时，在本地环境变量或未提交的 `backend/agent/.env` 中配置：

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=replace-with-your-langsmith-api-key
LANGSMITH_PROJECT=pcb-defect-rag
# 自托管或区域端点按实际情况设置；LangSmith 云端通常可省略。
# LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

关闭追踪：

```dotenv
LANGSMITH_TRACING=false
```

不要将真实 `LANGSMITH_API_KEY` 提交到 Git。

## RAG 评估

评估入口为 `rag_eveal/test1.py`，数据源为 `rag_eveal/rag_evaluation.csv`。脚本会：

1. 默认创建或同步固定名称 `rag_evaluation` 的 LangSmith 数据集；CSV 版本写入 metadata，旧格式样本会自动更新。
2. 使用隔离 SQLite 索引，不读取或污染业务 RAG 数据。
3. 禁止把 `question_predict` 写入被测语料，避免问题泄漏导致虚高分数。
4. 从 `relevant_doc_ids` 读取一个或多个相关父/子章节，记录检索 `Hit@1`、`Hit@3`、`MRR`、上下文精度。
5. 使用 LLM-as-judge 记录答案正确性、忠实度和回答相关性。
6. 将 LangSmith 明细同步导出到 `rag_eveal/results/`（该目录不应提交）。

完整运行明确设置 `upload_results=True`，评估结果会作为 Experiment 上传并归属 `rag_evaluation` 数据集。运行结束会输出 Experiment 名称和可直接打开的 LangSmith URL。使用 `--limit N` 时，为避免污染正式数据集，数据集名自动改为 `rag_evaluation-smoke-N`。

先运行不联网的检索基线：

```powershell
.\.venv\Scripts\python.exe rag_eveal\test1.py --local-retrieval-only
```

完整评估（会把问题、参考答案、检索上下文和模型回答发送到已配置的 LangSmith/模型 API）：

```powershell
.\.venv\Scripts\python.exe rag_eveal\test1.py --max-concurrency 2
```

低成本冒烟测试：

```powershell
.\.venv\Scripts\python.exe rag_eveal\test1.py --limit 2 --max-concurrency 1
```

只计算检索指标、不调用 LLM 裁判：

```powershell
.\.venv\Scripts\python.exe rag_eveal\test1.py --no-llm-judge
```

可选裁判模型配置为 `JUDGE_BASE_URL`、`JUDGE_API_KEY`、`JUDGE_MODEL`；未设置时复用 `OPENAI_*`。真实密钥只放在未提交的 `rag_eveal/.env.langsmith`。

### 评估 CSV 字段

- `relevant_doc_ids`：非空 JSON 数组，例如 `["6-01","6.1-01","6.2-01"]`；任一章节被召回即视为命中。
- `reference_answer`：针对 `question_predict` 的简洁中文标准答案。回答正确性不再使用完整英文 chunk 作为参考。

### 混合检索与精排

- 本地默认融合 jieba 词级 TF-IDF 与字符 2~5 gram TF-IDF，字符通道权重由 `RAG_CHAR_WEIGHT` 控制，默认 `0.35`。
- 中文查询改写会至少生成一条英文技术检索式，再对多查询结果做 RRF。
- 完整评估默认复用项目已配置的多语言 embedding；Chroma/PG 向量召回会与本地稀疏召回再次做 RRF。评估脚本按 CSV 哈希使用独立 Chroma collection，避免污染业务向量库；可用 `RAG_EVAL_VECTOR_ENABLED=false` 显式关闭。
- `--local-retrieval-only` 始终强制关闭 embedding 和外部向量库，确保基线不联网。
- `RAG_RERANKER_ENABLED=true` 时，最终候选由 LLM listwise reranker 精排后再截断到 `top_k`。

embedding 配置示例见 `rag_eveal/.env.langsmith.example`。建议使用支持中文与英文的模型，并为评估配置独立的 Chroma 路径和 collection。

### Token 与成本

`call_llm_api` 已作为 LangSmith `llm` 子 span 追踪，并从 OpenAI 兼容响应的 `usage` 字段上传：

- `input_tokens`
- `output_tokens`
- `total_tokens`
- 缓存命中 token（供应商返回时）
- `input_cost` / `output_cost` / `total_cost`

如果模型服务不直接返回 cost，需要在 `.env.langsmith` 按供应商当前价格配置：

```dotenv
OPENAI_INPUT_COST_PER_MILLION=
OPENAI_CACHED_INPUT_COST_PER_MILLION=
OPENAI_OUTPUT_COST_PER_MILLION=
```

价格刻意不在仓库中硬编码，避免供应商调价后继续产生错误成本。未配置价格时 token 仍会上传，但 LangSmith 无法识别模型价格时 `total_cost` 可能为空。

## 数据边界

完整评估会产生外部数据传输。执行前应确认 CSV 内容、问题、参考答案、检索上下文和模型回答允许发送到所配置的 LangSmith 与模型服务端点。密钥不会作为评估样本上传。

## 当前接入范围

SDK、依赖声明、离线/在线 RAG 评估链路和自定义 HTTP LLM span 已经接入。后续可继续细分：

1. `backend/routes/rag.py` 的单次 RAG 请求。
2. query rewriting、向量/TF-IDF 检索和 reranker 阶段。
3. `backend/services/llm_service.py` 的 embedding 请求。
4. 最终答案、耗时、召回来源和错误；API key 已从 trace 输入中移除。

## 验证

```powershell
.\.venv\Scripts\python.exe -c "import langsmith; print(langsmith.__version__)"
```

预期输出：

```text
0.10.2
```
