# PCB NASA 评估数据集说明

## 输出

- 数据集：`pcb_nasa_evaluation.csv`
- 审计：`pcb_nasa_evaluation_audit.json`
- 生成脚本：`generate_pcb_dataset.py`
- 切块预览：`pcb_nasa_chunks_preview.json`

原有 `rag_evaluation.csv` 未被覆盖。

## 来源

数据集仅使用用户确认的四份候选文档：

1. `NASA_GSFC-STD-8001_Printed_Circuit_Board_QA.pdf`
2. `NASA_PCB_Inspection_and_Quality_Control.pdf`
3. `NASA_PCB_Quality_Metrics_that_Drive_Reliability.pdf`
4. `NASA_Value_of_Workmanship_Standards.pdf`

每条 `hierarchy` 均保存文档标题和 PDF 页码。每条 `relevant_doc_ids` 只指向生成该问题的源 Chunk。

## CSV 字段

```text
chunk_id,hierarchy,title,content,keywords,question_predict,relevant_doc_ids,reference_answer
```

该结构与现有 LangSmith/RAGAS 评估脚本使用的字段约定兼容。

## 上下文窗口控制

- 每个 Chunk 只来自单个 PDF 页面，不跨文档合并。
- 页眉、页脚、会议日期、邮箱等重复噪声在切块前清理。
- 按句子/项目符号边界切分；缺少标点的超长表格文本按词边界切分。
- 生成阶段硬上限：1,800 字符、480 `cl100k_base` tokens。
- 最终数据集实际最大值：1,780 字符、384 tokens。
- 每次问答生成只发送 4 个 Chunk，避免批量提示过长。
- 问题文本不会写入 `content`，避免检索泄漏。

## 质量审计

- 最终行数：43
- 来源分布：PCB01=13、PCB02=13、PCB03=9、PCB04=8
- 重复 Chunk ID：0
- 重复问题：0
- 空字段：0
- 无效引用：0
- 问题原文直接出现在上下文：0
- 本地无 LLM 混合 TF-IDF 基线：Hit@1=0.8140，Hit@3=0.8837

有 5 条样本未被本地 Top-3 基线召回，经逐条复核，其问题和参考答案仍能由标注上下文直接支持，因此作为检索难例保留。

## 已排除内容

生成后剔除了一条金额数值样本。其 PDF 文本层将完整金额错误抽取为 `$5` 并含乱码，无法作为可信黄金答案。生成脚本已加入乱码和不完整金额检测，重新生成时也会自动排除同类片段。

## 重新生成

只执行切块和窗口检查：

```powershell
.\.venv\Scripts\python.exe .\rag_eveal\generate_pcb_dataset.py --prepare-only
```

重新调用已配置裁判模型生成数据：

```powershell
.\.venv\Scripts\python.exe .\rag_eveal\generate_pcb_dataset.py --batch-size 4
```

重新生成会覆盖 `pcb_nasa_evaluation.csv`，但不会覆盖旧的 `rag_evaluation.csv`。
