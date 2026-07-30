# RAGAS 评估进度与后续执行说明

> 项目：PCB 缺陷检测系统 RAG 评估  
> 评估框架：RAGAS（用户口述中的 “RAGA” 按 RAGAS 理解）  
> 当前阶段：第 7 步已完成，下一步执行第 8 步  
> 最后更新：2026-07-18 11:17:38 +08:00  
> 维护者：Codex

## 1. 评估目标

对项目真实 `RagEngine` 的检索与回答质量进行可复现评估，分开衡量：

1. 检索是否召回标注的正确文档。
2. 检索结果中噪声文档的比例。
3. 回答是否忠实于检索上下文。
4. 回答是否直接回应用户问题。
5. 检索上下文是否覆盖参考答案所需事实。
6. RAG、Prompt、模型或知识库变化后是否发生质量回退。

评估索引必须与业务知识库隔离；测试问题不得写入检索语料；所有实验必须记录数据集版本、模型、`top_k`、检索/改写/精排配置和结果文件。

## 2. 十步计划当前状态

| # | 任务 | 状态 | 完成度 | 当前结果/证据 | 下一动作或阻塞项 |
|---:|---|---|---:|---|---|
| 1 | 安装并锁定 RAGAS 评估依赖 | 已完成 | 100% | `pyproject.toml`、`uv.lock`；RAGAS 与相关依赖已安装 | `pyproject.toml` 仍使用最低版本约束，实际精确版本以 `uv.lock` 为准 |
| 2 | 复用当前 CSV 数据做 Smoke Test | 已完成 | 100% | `rag_evaluation.csv` 与 `pcb_nasa_evaluation.csv` 均完成 3 条 Smoke Test | 无 |
| 3 | 编写 RagEngine -> RAGAS 适配器 | 已完成 | 100% | `adapters/project_rag.py`、2 个 `unittest` 全部通过 | 无；后续评估统一通过适配器 |
| 4 | 先跑无 LLM 的 ID 检索指标 | 已完成 | 100% | `id_metrics_pcb_nasa_20260717_184133.json`；43 条全量，5 条 Top-3 未命中，所有门槛通过 | 无；保留 5 条未命中作为第 7 步分析输入 |
| 5 | 用 3-5 条样例验证裁判模型和 Embedding 配置 | 已完成 | 100% | 3 条新数据集 Smoke Test；裁判和 4096 维 Embedding 链路正常 | 正式全量前保留一次配置自检即可 |
| 6 | 跑完整 RAGAS 实验 | 已完成 | 100% | `ragas_full_pcb_nasa_20260717_185147.csv` 及摘要 JSON；43 条全量，耗时 3025.92 秒 | 三个质量门槛均未通过；转入第 7 步定位低分与裁判稳定性 |
| 7 | 检查低分样例和裁判稳定性 | 已完成 | 100% | `ragas_low_scores_20260718_111236.md`、`judge_stability_20260718_111236.csv`；5 条代表样本各重复 3 次 | 32 条低分/缺失样本待后续修复；5 条代表样本中 4 条裁判不稳定 |
| 8 | 将评估集扩充到至少 100 条 | 进行中 | 43% | 新 NASA 数据集 43 条，旧数据集 32 条；两者来源不同，暂不直接合并 | **下一步**：增加至少 57 条同口径、高质量、人工可审计样本 |
| 9 | 固定首次完整结果作为基线 | 未开始 | 0% | 尚无 43 条完整 RAGAS 结果 | 第 6、7 步完成后冻结 baseline 结果和配置快照 |
| 10 | 后续变更运行回归对比 | 未开始 | 0% | 尚未建立 baseline/current 对比脚本 | 第 9 步后实现回归报告和门禁阈值 |

总体进度约为 **74%**。第 1、2、3、4、5、6、7 步已完成；第 8 步已有部分成果；第 8 步是当前唯一应执行的下一步骤。

## 3. 已完成的重要结果

### 3.1 依赖和运行环境

当前虚拟环境精确版本如下，均已出现在 `uv.lock` 的解析结果中：

| 依赖 | 精确版本 | 用途 |
|---|---:|---|
| `ragas` | `0.4.3` | RAGAS 评估框架 |
| `langchain-community` | `0.4.2` | RAGAS 0.4.3 兼容依赖 |
| `langchain-core` | `1.4.9` | LangChain 基础接口 |
| `langchain-openai` | `1.3.5` | OpenAI 兼容裁判和 Embedding 适配 |
| `openai` | `2.45.0` | OpenAI 兼容客户端 |
| `datasets` | `5.0.0` | 数据集结构支持 |
| `pyarrow` | `25.0.0` | 表格数据后端 |
| `pandas` | `3.0.3` | CSV 和结果处理 |
| `numpy` | `2.4.6` | 指标和向量计算 |
| `tiktoken` | `0.13.0` | 上下文 token 上限审计 |
| `langsmith` | `0.10.2` | 可选实验追踪与既有评估链路 |

注意：`pyproject.toml` 中评估依赖当前写为 `>=`，不能单独作为“精确锁定”证据；可复现安装必须同时保留并使用 `uv.lock`。

### 3.2 评估数据集

| 数据集 | 行数 | 用途 | 状态 |
|---|---:|---|---|
| `rag_eveal/rag_evaluation.csv` | 32 | 早期 IPC/PCBA 评估集 | 已完成多轮 Smoke Test；来源身份与新 NASA 数据集不同 |
| `rag_eveal/pcb_nasa_evaluation.csv` | 43 | 当前主评估集；来自 4 份用户确认的 NASA PCB 文档 | 当前推荐用于第 4-9 步 |

两个 CSV 均使用以下固定列：

```text
chunk_id,hierarchy,title,content,keywords,question_predict,relevant_doc_ids,reference_answer
```

新 NASA 数据集审计结果：

- 43 条，重复 Chunk ID 0，重复问题 0，空字段 0，无效引用 0。
- 来源分布：PCB01=13、PCB02=13、PCB03=9、PCB04=8。
- 最大上下文 1,780 字符、384 `cl100k_base` tokens。
- 问题不写入 `content`，避免检索泄漏。
- 本地混合 TF-IDF 初始基线：Hit@1=0.8140、Hit@3=0.8837。

### 3.3 最近一次 Smoke Test

结果文件：`rag_eveal/results/ragas_smoke_pcb_nasa_evaluation_20260716_110540.csv`

| 指标 | 3 条平均分 | 阈值 | 结果 |
|---|---:|---:|---|
| ID Context Precision | 0.4444 | 暂未设门禁 | 记录 |
| ID Context Recall | 1.0000 | 暂未设门禁 | 通过 |
| Faithfulness | 0.8889 | > 0.8 | 通过 |
| Answer Relevancy | 0.9594 | > 0.8 | 通过 |
| Context Recall | 1.0000 | > 0.7 | 通过 |
| Factual Correctness F1 | 0.1667 | 暂不作为门禁 | 需检查中文裁判稳定性 |

Factual Correctness 与其他指标及实际回答的语义一致程度明显冲突，暂时只能作为诊断指标，不能在未完成稳定性分析前用于发布门禁。

### 3.4 适配器

`rag_eveal/adapters/project_rag.py` 已成为项目 RAG 到 RAGAS 的统一入口，负责：

- CSV 结构、唯一性、引用和空值校验。
- 用完整 CSV 语料创建版本化隔离 SQLite 索引。
- 保证 `question_predict` 不参与入库。
- 调用真实 `RagEngine.query()`。
- 输出 `user_input`、`response`、`retrieved_contexts`、`reference`、`retrieved_context_ids`、`reference_context_ids`。
- 保留实际上下文，并按文档 ID 去重检索 ID。
- 显式关闭 SQLite 资源。

### 3.5 第 4 步全量无 LLM ID 检索结果

正式脚本：`rag_eveal/id_retrieval_metrics.py`  
不可变结果：`rag_eveal/results/id_metrics_pcb_nasa_20260717_184133.json`

| 指标 | 43 条宏平均 | 建议阈值 | 结果 |
|---|---:|---:|---|
| ID Context Precision@3 | 0.2946 | 暂未设门禁 | 记录 |
| ID Context Recall@3 | 0.8837 | >= 0.85 | 通过 |
| Hit@1 | 0.8837 | >= 0.75 | 通过 |
| Hit@3 | 0.8837 | >= 0.85 | 通过 |
| MRR | 0.8837 | >= 0.80 | 通过 |

本次严格使用本地词级+字符级 TF-IDF，字符权重为 `0.35`，并禁用生成、查询改写、LLM reranker 和外部 Embedding。数据集 SHA-256 为 `e4f24dccec7048b42b4ef711d73b0fa73a2d61600fa17bd68c16c787d83f6d0b`。ID Precision 按 RAGAS 0.4.3 的集合口径计算；当前样本通常只有 1 个相关文档而固定返回 3 个文档，所以命中样本通常为 `1/3`。

5 条 Top-3 未命中样本已完整保存在结果 JSON 中：`PCB01-P021-C032`、`PCB01-P023-C035`、`PCB01-P025-C039`、`PCB03-P022-C037`、`PCB03-P034-C054`。运行时 Git commit 为 `035e9f94ac9cc3169960c5595f11a270dd72f8a9`，工作树非干净状态，结果同时保存了评估脚本、适配器和检索引擎的 SHA-256。

### 3.6 第 6 步 43 条完整 RAGAS 结果

正式脚本：`rag_eveal/ragas_full_evaluation.py`  
逐条结果：`rag_eveal/results/ragas_full_pcb_nasa_20260717_185147.csv`  
摘要结果：`rag_eveal/results/ragas_full_pcb_nasa_20260717_185147_summary.json`

运行时间为 2026-07-17 18:51:47 至 19:42:13，共 `3025.92` 秒。配置为 DeepSeek 被测模型与裁判、SiliconFlow Embedding、`top_k=3`、候选池 24、查询改写数 3、字符权重 0.35、LLM reranker 开启、RAGAS 并发数 2。

| 指标 | 均值 | 有效样本 | 门槛 | 结果 |
|---|---:|---:|---:|---|
| IDBasedContextPrecision | 0.4302 | 43/43 | 暂未设门禁 | 记录 |
| IDBasedContextRecall | 0.9535 | 43/43 | 暂未设门禁 | 记录 |
| Faithfulness | 0.7416 | 41/43 | > 0.8 | 未通过 |
| Answer Relevancy | 0.7299 | 42/43 | > 0.8 | 未通过 |
| LLM Context Recall | 0.5506 | 42/43 | > 0.7 | 未通过 |
| Factual Correctness F1 | 0.2624 | 41/43 | 诊断用途 | 不作门禁 |

缺失裁判结果没有按 0 分计入均值。第 6 步只证明完整实验已执行，不代表质量验收通过；低分、缺失结果和 Factual Correctness 异常进入第 7 步分析。

### 3.7 第 7 步低分与裁判稳定性结果

执行脚本：`rag_eveal/analyze_low_scores.py`  
低分报告：`rag_eveal/results/ragas_low_scores_20260718_111236.md`  
重复裁判明细：`rag_eveal/results/judge_stability_20260718_111236.csv`

全量 43 条结果的筛选统计：

| 条件 | 低分数 | 缺失数 |
|---|---:|---:|
| Faithfulness <= 0.8 | 24 | 2 |
| Answer Relevancy <= 0.8 | 12 | 1 |
| Context Recall <= 0.7 | 22 | 1 |
| 任一条件命中或核心指标缺失（去重） | 32 | - |

抽取 5 类代表样本，每条重复评判 3 次，共 15 组样本、60 个指标任务，四项指标均为 15/15 有效。以任一指标极差 >= 0.3 或标准差 >= 0.15 作为不稳定信号，5 条中有 4 条不稳定：

| Sample ID | 代表类型 | 主要稳定性结论 |
|---|---|---|
| `PCB01-P004-C003` | Answer Relevancy 低 | Answer Relevancy 极差 0.9758、标准差 0.4600，明显不稳定 |
| `PCB01-P012-C015` | ID 命中但 Context Recall 低 | Context Recall 极差 1.0000；Factual Correctness 极差 0.4000 |
| `PCB03-P022-C037` | 检索失败 | Factual Correctness 极差 0.4000；Context Recall 与 Answer Relevancy 稳定为 0 |
| `PCB04-P009-C003` | Factual Correctness 冲突 | Faithfulness 稳定为 1.0、Answer Relevancy 均值 0.9211，但 Factual Correctness 稳定为 0 |
| `PCB04-P020-C012` | 第 6 步裁判缺失 | 重跑全部有效；Faithfulness 极差 0.6667、标准差 0.3143 |

结论：低分同时来自基础检索失败、查询改写/精排挤出正确文档、ID 命中但事实窗口覆盖不足、回答扩写或遗漏，以及裁判异常。Factual Correctness 与其他指标既存在波动，也存在稳定的系统性冲突，继续只作诊断指标，不得设为硬门禁。完整的逐样本问题、召回 ID、离线对照、回答、参考答案、初步归因和修复顺序均保存在低分报告中。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover `
  -s .\rag_eveal\tests `
  -p "test_*.py" -v
```

当前结果：2/2 通过，不访问外部模型。

## 4. 当前需要读取的文件

### 4.1 每次评估都必须读取

| 文件 | 读取目的 | 是否包含敏感信息 | 注意事项 |
|---|---|---|---|
| `rag_eveal/pcb_nasa_evaluation.csv` | 当前黄金问题、上下文、正确文档 ID 和参考答案 | 否，来源为公开文档 | 第 4-9 步的主数据集；不要将问题写回索引语料 |
| `rag_eveal/adapters/project_rag.py` | CSV 校验、隔离索引、字段映射 | 否 | 后续脚本应复用，不再复制映射代码 |
| `backend/agent/rag/rag_engine.py` | 真实检索、回答生成、候选池和 Top-K 行为 | 否 | 修改会改变基线，必须记录 Git diff/版本 |
| `backend/agent/rag/hybrid.py` | 多查询和 RRF 融合 | 否 | 第 4 步 ID 指标必须反映当前实现 |
| `backend/agent/rag/reranker.py` | LLM listwise 精排 | 否 | 第 4 步无 LLM 时必须禁用；第 6 步启用 |
| `backend/agent/rag/rewriter.py` | 多查询改写 | 否 | 第 4 步无 LLM 时必须禁用；第 6 步按真实配置启用 |
| `backend/agent/config.py` | `top_k`、混合检索、精排、向量配置解释 | 否 | 每次实验保存有效配置 |
| `backend/agent/.env` | 业务 RAG 的运行配置 | **是** | 只读取键和值供本地运行；严禁提交或写入报告 |
| `rag_eveal/.env.ragas` | 目标模型、裁判和 Embedding 配置 | **是** | 严禁输出 API Key、提交 Git 或复制到结果 CSV |
| `pyproject.toml`、`uv.lock` | 依赖声明和精确解析版本 | 否 | 结果元数据应记录 lock 状态或依赖版本 |

### 4.2 数据集生成和溯源时读取

| 文件/目录 | 读取目的 | 注意事项 |
|---|---|---|
| `rag_eveal/candidate_documents/` | 4 份选定 NASA PDF 和候选来源清单 | 仅第 8 步扩充数据集时需要 |
| `rag_eveal/candidate_documents/validation.json` | PDF 页数、元数据和文本可读性 | 不代替人工事实审阅 |
| `rag_eveal/generate_pcb_dataset.py` | 受控切块和问答生成流程 | 重新运行会覆盖新 CSV，运行前应备份或使用新输出名 |
| `rag_eveal/pcb_nasa_chunks_preview.json` | 切块 token、页码和预览审计 | 适合检查窗口和异常片段 |
| `rag_eveal/pcb_nasa_evaluation_audit.json` | 数据集统计与完整性检查 | 数据集变化后必须同步刷新 |

### 4.3 历史对照时读取

| 文件/目录 | 用途 |
|---|---|
| `rag_eveal/rag_evaluation.csv` | 旧 32 条数据集对照，不应未经来源核验直接并入 NASA 数据集 |
| `rag_eveal/test1.py` | 既有 LangSmith 完整评估入口和指标实现参考 |
| `rag_eveal/results/` | Smoke Test、LangSmith 和后续全量结果历史 |
| `rag_eveal/PCB_NASA_DATASET.md` | 新数据集的生成、窗口和审计说明 |
| `rag_eveal/adapters/README.md` | 适配器字段契约和使用方法 |

## 5. 当前和后续需要写入的文件

### 5.1 已存在且允许更新

| 文件/目录 | 写入内容 | 写入时机 | 禁止事项 |
|---|---|---|---|
| `rag_eveal/results/` | 每次实验的逐条 CSV、摘要 JSON 和失败样例报告 | 第 4、5、6、7、9、10 步 | 不写 API Key；文件名必须含数据集和时间/实验 ID |
| `rag_eveal/data/` | 由 CSV 版本生成的隔离 SQLite/向量索引 | 第 4、6 步 | 不与 `backend/data/rag.db` 混用 |
| `rag_eveal/RAGAS_EVALUATION_PROGRESS.md` | 当前状态、结果、下一步和风险 | 每完成一个步骤后 | 不记录密钥 |
| `progress.md` | 根项目级 RAGAS 任务状态 | 每完成一个步骤后 | 状态和完成度必须与本文件一致 |
| `修改记录.md` | 时间、文件、原因和验证方式 | 每次代码/数据/文档变更后 | 不写敏感配置值 |

### 5.2 后续计划新增

以下文件尚未创建，名称是建议契约：

| 计划文件 | 产生步骤 | 内容 |
|---|---:|---|
| `rag_eveal/results/ragas_config_check_<timestamp>.json` | 5 | 裁判/Embedding 的主机、模型、向量维度和成功状态；不含密钥 |
| `rag_eveal/results/ragas_full_pcb_nasa_<timestamp>.csv` | 6 | 43 条完整逐样本 RAGAS 结果 |
| `rag_eveal/results/ragas_full_pcb_nasa_<timestamp>_summary.json` | 6 | 指标均值、中位数、分位数、失败数和运行配置 |
| `rag_eveal/pcb_nasa_evaluation_v2.csv` | 8 | 至少 100 条、同一来源与标注规范的新版本数据集 |
| `rag_eveal/baselines/pcb_nasa_baseline.json` | 9 | 首次完整基线指标、阈值、数据哈希和配置快照 |
| `rag_eveal/results/regression_<timestamp>.md` | 10 | 当前实验与 baseline 的差异和回归判定 |

## 6. 明确禁止写入或覆盖的文件

| 文件 | 原因 |
|---|---|
| `backend/data/rag.db` | 业务知识库，不能作为 CSV 评估的临时索引，也不能被评估清空/重建 |
| `backend/data/chroma/` | 业务向量数据；评估必须使用 `rag_eveal/data/` 下的隔离集合 |
| `rag_eveal/.env.ragas` 中的 API Key | 密钥只能由用户维护，不能进入日志、结果、文档或 Git |
| `backend/agent/.env` 中的 API Key/数据库密码 | 同上 |
| `rag_eveal/rag_evaluation.csv` | 旧数据集；未经明确要求不得被新 NASA 数据覆盖 |
| `rag_eveal/pcb_nasa_evaluation.csv` | 当前 43 条主数据集；第 4-7、9 步只读，第 8 步应输出新版本文件而非原地覆盖 |

## 7. 接下来需要执行的评估步骤

### 第 4 步：全量无 LLM ID 检索指标（已完成）

目的：先判断检索器本身，不让查询改写、精排、生成模型或裁判模型掩盖问题。

执行要求：

1. 读取 43 条 `pcb_nasa_evaluation.csv`。
2. 使用 `ProjectRagAdapter` 的隔离索引逻辑。
3. 禁用生成、查询改写、LLM reranker 和外部 Embedding。
4. 使用当前本地词级+字符级混合 TF-IDF。
5. 计算 ID Context Precision、ID Context Recall、Hit@1、Hit@3、MRR。
6. 输出所有 Top-3 未命中样本，而不只输出平均分。
7. 保存数据集 SHA-256、`top_k`、字符权重和代码版本信息。

建议验收阈值：

| 指标 | 建议阈值 |
|---|---:|
| Hit@1 | >= 0.75 |
| Hit@3 | >= 0.85 |
| MRR | >= 0.80 |
| ID Context Recall@3 | >= 0.85 |

正式结果为 Hit@1=0.8837、Hit@3=0.8837、MRR=0.8837、ID Context Recall@3=0.8837，所有建议门槛均已通过。与早期临时脚本的 Hit@1=0.8140 不同，本次正式脚本按适配器契约对文档 ID 去重，并保存了逐样本结果和完整复现元数据。

### 第 5 步：裁判和 Embedding 自检

当前已经完成，但全量运行前仍应执行轻量预检：

1. 裁判模型完成一次结构化输出。
2. Embedding 对一个问题返回非空定长向量；当前已验证为 4096 维。
3. 记录模型名、端点主机、维度和耗时，不记录 API Key。
4. SiliconFlow 类接口只支持 `n=1` 时，Answer Relevancy 使用 `strictness=1`。
5. Embedding 发送原始字符串，保持 `check_embedding_ctx_length=False`。

### 第 6 步：43 条完整 RAGAS 实验（已完成）

运行真实链路：原问题 + 多查询改写 + 混合检索/RRF + 24 条候选精排 + Top-3 + 回答生成。

至少计算：

- IDBasedContextPrecision
- IDBasedContextRecall
- Faithfulness
- Answer Relevancy
- LLMContextRecall
- FactualCorrectness（诊断用途，暂不做门禁）

43 条逐样本结果和摘要已保存。正式均值为 ID Precision 0.4302、ID Recall 0.9535、Faithfulness 0.7416、Answer Relevancy 0.7299、LLM Context Recall 0.5506、Factual Correctness F1 0.2624；三个质量门槛均未通过，必须完成第 7 步后再决定修复方向。

### 第 7 步：低分与裁判稳定性（已完成）

已筛出 32 条低分或核心指标缺失样本，并完成 5 条代表样本各 3 次重复评判。详细均值、极差、标准差和有效次数见稳定性 CSV；逐样本归因和修复建议见低分报告。Factual Correctness 继续只作诊断指标，不作为硬门禁。

### 第 8 步：扩充到至少 100 条

需要至少新增 57 条同口径样本。优先覆盖：

- 多文档问题。
- 相似章节辨析。
- 数值/阈值问题。
- 无答案问题。
- 同义改写与中英文混合查询。
- 制造、检验、可靠性、失效分析和工艺控制的均衡分布。

每条必须保留文档、页码、Chunk ID、参考答案和人工审核状态；有 OCR 数值缺失或乱码的片段直接排除。

### 第 9 步：固定首次完整基线

基线至少记录：

- 数据集 SHA-256 和行数。
- Git commit/工作树状态。
- Python 和关键依赖版本。
- 目标模型、裁判模型、Embedding 模型。
- `top_k`、候选池、改写数、混合权重和精排开关。
- 各指标及门禁阈值。
- 完整结果文件路径。

### 第 10 步：回归对比

RAG 代码、Prompt、模型、Embedding、Chunk 策略、知识库或数据集变化时运行：

1. 同数据集、同配置重跑 current。
2. 与 baseline 按总体和逐样本比较。
3. 标记超过阈值的下降。
4. 输出新增改善、回归样本和配置差异。
5. 未通过门禁时不更新 baseline；只有确认改进后才显式晋升新基线。

## 8. 当前风险和待确认项

| 风险 | 影响 | 处理建议 |
|---|---|---|
| 3 条 Smoke Test 样本过少 | LLM 指标均值方差大 | 第 6 步跑完整 43 条，第 7 步重复裁判 |
| Factual Correctness 中文结果异常低 | 可能误判正确答案 | 暂作诊断指标；检查 prompt、语言参数和裁判重复性 |
| RAGAS 0.4.3 与新版 LangChain 存在兼容导入 | 升级可能破坏脚本 | 保留兼容垫片并在升级前跑导入/单测 |
| RAGAS/LangChain 部分 wrapper 已提示弃用 | 后续版本可能移除 | 在当前 baseline 固定后迁移到 `llm_factory`/现代 Embedding provider |
| 新数据集目前只有 43 条 | 覆盖度不足 | 第 8 步扩充到 >=100 条，并引入人工审核状态 |
| 当前工作树存在大量未提交修改 | 基线难以对应唯一代码状态 | 第 9 步必须记录 `git status` 和 commit/hash；由用户决定提交 |
| 外部模型调用会发送公开文档片段和评估问题 | 存在成本与外部传输 | 每次全量运行前确认模型、端点、样本范围和预算 |

## 9. 更新规则

每完成一个步骤，必须同步更新：

1. 本文件的十步状态表、结果、风险和最后更新时间。
2. 根目录 `progress.md` 对应任务行。
3. 根目录 `修改记录.md` 的时间、文件、原因和验证方式。
4. `rag_eveal/results/` 中的不可变结果文件。

不要用新的运行结果覆盖历史结果；使用含数据集名和时间戳的文件名。不要在未完成全量实验和稳定性检查前宣称已建立正式 baseline。
