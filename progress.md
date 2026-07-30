# PCB 缺陷检测系统 — 可执行计划

## 项目结构盘点进度

| 模块/任务 | 负责人 | 状态 | 完成度 | 证据/文件 | 阻塞项 | 最后更新时间 |
|---|---|---|---:|---|---|---|
| 项目目录与入口盘点 | Codex | 已完成 | 100% | `PROJECT_STRUCTURE.md`、`start.py`、`backend/main.py`、`web2/src/main.tsx` | 无 | 2026-07-13 09:15:35 +08:00 |
| 前后端与板端技术栈识别 | Codex | 已完成 | 100% | `PROJECT_STRUCTURE.md`、`pyproject.toml`、`web2/package.json`、`scripts/` | 无 | 2026-07-13 09:15:35 +08:00 |
| Python 依赖固定版本审计 | Codex | 已完成 | 100% | `PROJECT_STRUCTURE.md`、`requirements.txt`、`uv.lock` | 第三方依赖未锁定，需后续重新生成锁文件 | 2026-07-13 09:15:35 +08:00 |
| 架构、数据流、部署与风险说明 | Codex | 已完成 | 100% | `PROJECT_STRUCTURE.md` | 生产入口与数据目录仍待项目方确认 | 2026-07-13 09:15:35 +08:00 |
| PostgreSQL Docker 打包 | Codex | 已完成 | 100% | `docker-compose.postgres.yml`、`.env.postgres.example`、`POSTGRES_DOCKER.md` | 启动前需由用户设置数据库密码；需本机 Docker 验证 | 2026-07-13 09:15:35 +08:00 |
| 文档模型与解析器迁移 | Codex | 已完成 | 100% | `backend/agent/document/`、`backend/routes/rag.py` | 文档版本模型尚未接入持久化版本表 | 2026-07-13 +08:00 |
| RAG 文档入库时间时区修复 | Codex | 已完成 | 100% | `backend/agent/rag/rag_engine.py`、`web2/src/components/RagTab.tsx` | 无 | 2026-07-13 +08:00 |
| RAG 文档跨存储删除一致性 | Codex | 已完成 | 100% | `backend/agent/platform/postgres.py`、`backend/agent/rag/rag_engine.py`、`backend/routes/rag.py`、`web2/src/components/RagTab.tsx` | 需重启后端后用真实 PostgreSQL 复核 | 2026-07-13 +08:00 |
| RAG 检测历史与良品率分析 | Codex | 已完成 | 100% | `backend/store/inspection_store.py`、`backend/routes/detect.py`、`backend/routes/rag.py`、`web2/src/components/ImageRecTab.tsx`、`web2/src/App.tsx` | 实时板端良品需设备提供完整过板/批次边界信号 | 2026-07-13 +08:00 |
| 检测历史日历与批次筛选 | Codex | 已完成 | 100% | `backend/store/inspection_store.py`、`web2/src/components/HistoryTab.tsx`、`web2/src/components/ImageRecTab.tsx` | 旧记录没有批次号，统一显示为历史记录 | 2026-07-13 +08:00 |
| 系统配置检测存储落地 | Codex | 已完成 | 100% | `backend/routes/detect.py`、`backend/store/inspection_store.py`、`backend/store/alarm_store.py`、`web2/src/App.tsx`、`web2/src/components/ConfigTab.tsx` | 无 | 2026-07-13 +08:00 |
| 历史与 RAG 独立滚动及会话历史 | Codex | 已完成 | 100% | `web2/src/App.tsx`、`web2/src/components/HistoryTab.tsx`、`web2/src/components/RagTab.tsx` | RAG 会话保存在当前浏览器 localStorage | 2026-07-13 +08:00 |
| RAG 对话删除 | Codex | 已完成 | 100% | `web2/src/components/RagTab.tsx` | 删除仅作用于当前浏览器本地会话 | 2026-07-13 +08:00 |
| RAG 三栏布局与文档折叠 | Codex | 已完成 | 100% | `web2/src/components/RagTab.tsx` | 小屏幕按左、中、右顺序纵向排列 | 2026-07-13 +08:00 |
| RAG 左右停靠栏 | Codex | 已完成 | 100% | `web2/src/components/RagTab.tsx` | 当前按桌面工作区布局优化 | 2026-07-13 +08:00 |
| RAG 独立对话栏与右收文档面板 | Codex | 已完成 | 100% | `web2/src/components/RagTab.tsx` | 文档上传和列表分别维护展开状态 | 2026-07-13 +08:00 |
| RAG 统一文档管理模块 | Codex | 已完成 | 100% | `web2/src/components/RagTab.tsx` | 上传、配置和文档列表统一滚动与收起 | 2026-07-13 +08:00 |
| RAG 对话单条与批量删除 | Codex | 已完成 | 100% | `web2/src/components/RagTab.tsx` | 删除操作在生成回答期间禁用 | 2026-07-13 +08:00 |
| 检测历史缺陷编号说明 | Codex | 已完成 | 100% | `web2/src/components/HistoryTab.tsx`、`web2/src/components/ImageRecTab.tsx`、`web2/src/App.tsx` | 实时检测目标 ID 可能是跟踪编号 | 2026-07-13 +08:00 |
| 缺陷类别编号调整为 1–6 | Codex | 已完成 | 100% | `web2/src/components/HistoryTab.tsx`、`web2/src/App.tsx` | 模型内部仍使用 0–5 | 2026-07-13 +08:00 |
| 缺陷类别编号回退到 0–5 | Codex | 已完成 | 100% | `web2/src/components/HistoryTab.tsx`、`web2/src/App.tsx` | 已反向迁移上一版 1–6 浏览器记录 | 2026-07-13 +08:00 |
| 历史目标编号按缺陷类别纠正 | Codex | 已完成 | 100% | `web2/src/components/HistoryTab.tsx`、`web2/src/types.ts`、`web2/src/App.tsx` | 实时检测仍保留板端跟踪 ID | 2026-07-13 +08:00 |
| LangSmith 依赖安装与文档 | Codex | 已完成 | 100% | `requirements.txt`、`pyproject.toml`、`LANGSMITH.md`、`PROJECT_STRUCTURE.md` | SDK 已安装，业务 tracing 尚未接入 | 2026-07-13 +08:00 |

> 原交通检测系统改为 PCB 缺陷检测，模型：6 类（missing_hole, mouse_bite, open_circuit, short, spur, spurious_copper）

## ✅ 已完成

### 阶段一：模型适配（已完成）

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 1 | 更新配置模型名 | `backend/data/config.json` | ✅ `selectedModel` 设为 `yolo26n`，对应 `model/yolo26n.pt` |

### 阶段二：后端适配（8 步，全部完成）

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 2 | 更新类别映射 | `backend/core/pipeline.py` | ✅ |
| 3 | 移除 estimator 模块 | `backend/core/estimator.py` | ✅ 已删除 |
| 4 | 简化管线 | `backend/core/pipeline.py` | ✅ |
| 5 | 简化硬件遥测 | `backend/core/hardware.py` | ✅ |
| 6 | 更新数据模型 | `backend/models.py` | ✅ |
| 7 | 更新配置 | `backend/data/config.json` | ✅ |
| 8 | 适配 WS 消息 | `backend/main.py` | ✅ |

### 阶段三：前端适配（已全部完成 + 扩展）

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 7 | 更新类型定义 | `web2/src/types.ts` | ✅ |
| 8 | 精简 Tab 结构 | `web2/src/App.tsx` | ✅ |
| 9 | 适配图片检测 | `web2/src/components/ImageRecTab.tsx` | ✅ |
| 10 | 适配视频检测 | `web2/src/components/VideoRecTab.tsx` | ✅ |
| 11 | 更新 Sidebar | `web2/src/components/Sidebar.tsx` | ✅ |

### 阶段四：清理与验证（已全部完成）

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 12 | 删除交通相关组件 | 删除 `CameraTab.tsx` | ✅ |
| 13 | 更新文档 | `前端结构梳理.md` `后端结构梳理.md` `start.md` | ✅ |
| 14 | 清理修改记录 | `修改记录.md` | ✅ |
| 15 | 编译验证 | `npx tsc --noEmit` 通过 | ✅ |

### 新增功能（超出原计划）

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| — | **RV1126B 实时检测** | `web2/src/components/LiveDetectTab.tsx` | 新增 Tab：RTSP 视频流连接 + 实时 6 色缺陷框叠加 + 板端状态监控（FPS/NPU/温度）+ 缺陷统计列表 + 缺陷详情画面下方 |
| — | **AI 分析全覆盖** | 已移除 | Gemini AI 曾加入 ImageRecTab/LiveDetectTab，后因需求变更移除 |
| — | **缺陷详情布局优化** | `LiveDetectTab.tsx` `ImageRecTab.tsx` | 缺陷详情从右侧面板移至画面下方，5 格卡片横排布局 |
| — | **批量图片检测** | `ImageRecTab.tsx` | 支持多图上传、批量检测、逐张进度、分类统计汇总 |
| — | **检测历史持久化** | `App.tsx` `HistoryTab.tsx` | 检测结果自动记录到 localStorage，刷新不丢失 |
| — | **侧边栏折叠** | `Sidebar.tsx` | 左侧导航栏支持折叠/展开，折叠时仅显示图标 |
| — | **图片检测框坐标修复** | `ImageRecTab.tsx` `dataAdapter.ts` `LiveDetectTab.tsx` | 坐标链路 0-100% 统一，容器精确匹配图片尺寸 |
| — | **系统配置重构** | `web2/src/components/ConfigTab.tsx` | 去掉冗余的置信度/IoU（各 Tab 独立控制），改为：模型配置 / 检测存储 / 板端参数 / 告警通知 / 系统信息 五大板块 |
| — | **SystemConfig 扩展** | `web2/src/types.ts` | 新增 `saveResults`/`retentionDays`/`jpegQuality`/`maxFps`/`npuMode`/`tempWarning`/`reviewThreshold`/`consecutiveAlerts` |
| — | **一键启动脚本** | `start.py` | 根目录运行 `python start.py` 同时启动前后端 |
| — | **模型名更新** | `ImageRecTab.tsx` `VideoRecTab.tsx` `ConfigTab.tsx` `config.json` | 默认模型名 `pcb_model` → `yolo26n` |

---

## 缺陷类型颜色映射

| 缺陷 | 颜色 | 色值 |
|------|------|------|
| missing_hole | 红 | `#ff453a` |
| mouse_bite | 橙 | `#ff9f0a` |
| open_circuit | 紫 | `#bf5af2` |
| short | 蓝 | `#0a84ff` |
| spur | 绿 | `#30d158` |
| spurious_copper | 黄 | `#ffd60a` |

## 后端 WS 消息格式（PCB 版）

```
targets_stream: [{ id, type: "defect", className, confidence, x, y, width, height }]
telemetry_metrics: { fps, npu, cpu, memUsed, memTotal, temp, latency, selectedModel }
```

## 保留功能

- ✅ 图片上传 + YOLO 检测 + 缺陷框显示 + 详情面板
- ✅ 视频上传 + 离线处理 + 进度条 + 播放
- ✅ Gemini AI 场景分析（可选）
- ✅ WebSocket 实时数据推送
- ✅ 参数调节（各 Tab 独立置信度/IOU）
- ✅ **RV1126B 板端实时检测**（新增）
- ✅ **检测结果自动保存**（新增）
- ✅ **板端硬件监控**（FPS/NPU/温度，新增）

## 2026-07-14：RAG 评估改进

| 任务 | 状态 | 结果 |
|---|---|---|
| 校验 32 条 CSV 评估数据 | ✅ | 字段完整，`chunk_id` 与问题均无重复 |
| 消除评估问题泄漏 | ✅ | `question_predict` 不再写入评估索引 |
| 增加 LangSmith evaluator | ✅ | 检索 4 指标 + 回答 3 指标 |
| 修复 RAG 上下文重复与 top_k 失效 | ✅ | 父块去重并严格截断 top_k |
| 加强中英跨语言查询改写 | ✅ | 中文问题至少生成一条英文技术检索式 |
| 本地检索基线 | ✅ | Hit@1=0.2500，Hit@3=0.3750，MRR=0.3021 |
| LangSmith 端到端冒烟/完整评估 | ⏸ | 等待确认允许向已配置外部端点上传评估内容 |
| LangSmith 并发评估稳定性修复 | ✅ | TF-IDF 初始化加锁，8 线程/32 次并发检索回归通过 |
| LLM 裁判输出容错 | ✅ | 支持从推理文本中提取 JSON；格式异常记录为 `judge_parse_error` 而非中断实验 |
| 评估集相关性标签升级 | ✅ | 32 条新增 `relevant_doc_ids`，支持父/子章节多正确答案 |
| 评估集参考答案升级 | ✅ | 32 条新增面向问题的简洁中文 `reference_answer` |
| 本地混合稀疏检索 | ✅ | 词级 TF-IDF + 字符 n-gram；新基线 Hit@1=0.2812、Hit@3=0.4375、MRR=0.3490 |
| 向量/稀疏融合接口 | ✅ | 有 embedding 后端时使用 RRF 融合 Chroma/PG 与稀疏候选 |
| LLM reranker | ✅ | 默认启用，候选精排后严格截断 top_k |
| LangSmith token/cost | ✅ | 自定义 HTTP LLM span 上传 usage；成本支持供应商返回值或每百万 token 配置 |
| 新配置端到端 LangSmith 复评 | ⏳ | 代码与离线回归完成，等待运行新 Experiment |

## 2026-07-16：RAGAS 评估计划进度

| 模块/任务 | 负责人 | 状态 | 完成度 | 证据/文件 | 阻塞项 | 最后更新时间 |
|---|---|---|---:|---|---|---|
| RAGAS 依赖安装与锁定 | Codex | 已完成 | 100% | `pyproject.toml`、`uv.lock` | 精确版本以 `uv.lock` 为准 | 2026-07-16 19:43:04 +08:00 |
| 当前 CSV Smoke Test | Codex | 已完成 | 100% | `rag_eveal/ragas_smoke_test.py`、`rag_eveal/results/` | 无 | 2026-07-16 19:43:04 +08:00 |
| RagEngine -> RAGAS 适配器 | Codex | 已完成 | 100% | `rag_eveal/adapters/project_rag.py`、`rag_eveal/tests/test_project_rag_adapter.py` | 无；2/2 unittest 通过 | 2026-07-16 19:43:04 +08:00 |
| 全量无 LLM ID 检索指标 | Codex | 已完成 | 100% | `rag_eveal/id_retrieval_metrics.py`、`rag_eveal/results/id_metrics_pcb_nasa_20260717_184133.json` | 43 条全量；5 条 Top-3 未命中；Hit@1/3、MRR、Recall@3 均通过 | 2026-07-17 18:42:55 +08:00 |
| 裁判与 Embedding 小样本验证 | Codex | 已完成 | 100% | `ragas_smoke_pcb_nasa_evaluation_20260716_110540.csv` | Factual Correctness 中文稳定性待分析 | 2026-07-16 19:43:04 +08:00 |
| 43 条完整 RAGAS 实验 | Codex | 已完成 | 100% | `rag_eveal/results/ragas_full_pcb_nasa_20260717_185147.csv`、摘要 JSON | 43 条完成；三个质量门槛均未通过 | 2026-07-18 10:54:01 +08:00 |
| 低分样例与裁判稳定性 | Codex | 已完成 | 100% | `rag_eveal/results/ragas_low_scores_20260718_111236.md`、`judge_stability_20260718_111236.csv` | 32 条低分/缺失；5 条代表样本中 4 条裁判不稳定 | 2026-07-18 11:17:38 +08:00 |
| 评估集扩充至 >=100 条 | Codex | 进行中 | 43% | `rag_eveal/pcb_nasa_evaluation.csv`（43 条） | 当前下一步；需新增至少 57 条同口径样本 | 2026-07-18 11:17:38 +08:00 |
| 固定首次完整 baseline | Codex | 未开始 | 0% | 计划目录 `rag_eveal/baselines/` | 等待完整实验和稳定性检查 | 2026-07-16 19:43:04 +08:00 |
| 后续回归对比 | Codex | 未开始 | 0% | 计划输出 `rag_eveal/results/regression_<timestamp>.md` | 依赖 baseline | 2026-07-16 19:43:04 +08:00 |

详细文件读写矩阵、指标、验收标准和后续执行方式见 `rag_eveal/RAGAS_EVALUATION_PROGRESS.md`。
