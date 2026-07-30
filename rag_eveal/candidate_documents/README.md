# PCB RAG 候选文档清单

> 收集日期：2026-07-15  
> 范围假设：用户所说的 “PCD” 按当前项目上下文理解为 “PCB/PCBA”。  
> 状态：仅作为候选资料，尚未写入知识库或生成评估数据集。

## 建议优先审阅

| 编号 | 本地文件 | 页数 | 主题 | 来源与使用状态 | 建议 |
|---|---|---:|---|---|---|
| PCB-01 | `NASA_GSFC-STD-8001_Printed_Circuit_Board_QA.pdf` | 33 | 印制电路板质量保证要求、供应商与制造控制、检验和验收 | NASA GSFC 技术标准；封面标明批准公开发布、无限制分发 | 强烈推荐。正式标准结构清晰，适合生成事实型问答和质量保证类测试集 |
| PCB-02 | `NASA_PCB_Inspection_and_Quality_Control.pdf` | 84 | PCB 失效原因、物理失效、材料、湿气、测试与检验、失效分析 | NASA NTRS 20180005658；Public；美国政府作品，允许公众使用 | 强烈推荐。与当前缺陷检测、检验和可靠性场景最贴近 |
| PCB-03 | `NASA_PCB_Quality_Metrics_that_Drive_Reliability.pdf` | 60 | PWB 结构完整性、供应商质量偏差、不符合项、根因和缓解措施 | NASA NTRS 20200000752；Public；美国政府作品，允许公众使用 | 强烈推荐。适合质量指标、根因和供应商风险类问题 |
| PCB-04 | `NASA_Value_of_Workmanship_Standards.pdf` | 30 | 工艺标准价值、设计/材料/过程/过程控制/筛选如何预防缺陷 | NASA NTRS 20130013420；Public；美国政府作品，允许公众使用 | 推荐。适合工艺标准、质量体系和缺陷预防类问题 |

## 扩展候选

| 编号 | 本地文件 | 页数 | 主题 | 来源与使用状态 | 建议 |
|---|---|---:|---|---|---|
| PCB-05 | `NASA_Building_Reliable_Circuit_Board_Assemblies.pdf` | 411 | 可靠电路板组件、制造和装联经验、失效与可靠性 | NASA NTRS 20220012625；Public，但记录注明部分内容可能受版权保护 | 内容丰富但体量大。建议确认后只抽取明确可用章节，并保留页码和来源标记 |
| PCB-06 | `NASA_High-Speed_PCB_Design_Guide.pdf` | 115 | 高速 PCB 叠层、阻抗、材料、布线、信号完整性和制造设计 | NASA S3VI 资源库托管；文档实际品牌为 Sierra Circuits，并非 NASA 标准 | 可作为设计知识扩展，但与当前装联缺陷评估主题较远，且需单独确认第三方使用条款 |

## 原始来源

- PCB-01: <https://s3vi.ndc.nasa.gov/ssri-kb/static/resources/gsfc-std-8001.pdf>
- PCB-02: <https://ntrs.nasa.gov/citations/20180005658>
- PCB-03: <https://ntrs.nasa.gov/citations/20200000752>
- PCB-04: <https://ntrs.nasa.gov/citations/20130013420>
- PCB-05: <https://ntrs.nasa.gov/citations/20220012625>
- PCB-06: <https://s3vi.ndc.nasa.gov/ssri-kb/static/resources/High-Speed%20PCB%20Design%20Guide.pdf>

## 未下载但建议用户自备授权副本

下列 IPC 标准与当前主题高度相关，但通常不是可自由下载的公开全文。本次没有从第三方镜像收集：

- IPC-A-610：电子组件可接受性
- J-STD-001：焊接电气和电子组件要求
- IPC-6012：刚性印制板鉴定与性能规范
- IPC-2221：印制板通用设计标准
- IPC-7711/7721：电子组件返工、修改和维修

如果用户拥有合法副本，可以与上述 NASA 公开材料组合成更完整的数据集，但应在数据集中记录来源、版本和许可范围。

## 校验结果

- 六个文件均可被 PDF 解析器打开。
- 页数分别为 33、84、60、30、411、115 页。
- 六个文件均能抽取文本，不是纯扫描图片。
- 六个文件首页已渲染为 `_preview/` 下的 PNG 进行视觉抽检。
- `validation.json` 保存了文件大小、页数、PDF 元数据和前三页文本摘要。
- `NASA_Building_Reliable_Circuit_Board_Assemblies.pdf` 存在部分交叉引用对象警告，但可打开、可提取文本、可渲染；正式处理时应按页验证。

## 建议的首批组合

建议先选择 PCB-01、PCB-02、PCB-03、PCB-04。它们覆盖质量保证、缺陷/失效、检验、可靠性指标和工艺控制，主题互补，版权状态也最清晰。确认后再进行去重、按章节切块、问题生成和人工抽检。
