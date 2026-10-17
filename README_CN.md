# EmoryNLP Season 1 pipeline

源目录：`C:\Users\ZhaoC\Desktop\EmoryNLP`。本文件夹供查看和核对，未压缩；顶层只有 `scripts/`、`data/` 和本 README。数据范围是 Season 1 第 1–24 集主流程及其两种 MSF 输入路线。

## 从头到尾的路线

| 步骤 | 脚本顺序 | 输入 → 输出 |
|---|---|---|
| 00 原始 episode | `get_ep.py`；另有 `get_resolved_ep.py` | `friends_season_01.json` → 原始 episode DOCX；解析版脚本从同一 JSON 生成实体解析 DOCX。 |
| 01 候选提取 | `scene_step1_input.py` → `batch.py` → `get_batch_result.py` → `debug.py` | episode DOCX → 候选请求 JSONL → Batch 响应 JSONL → 每集/场景候选 JSON。 |
| 02 tuple 规范化 | `scene_step3_direct_ep01_ep10.py`（1–10 集）或 `scene_step3_direct.py`（11–24 集）→ 共用 Batch 脚本 → `get_batch_result.py` → `get_candidate.py` | episode DOCX + 候选 TXT → 规范化请求/响应 JSONL → 每场景 JSON + 可读 tuple TXT。 |
| 03 融合输入 | `get_augmented.py` | 原始 episode DOCX + 规范化 tuple TXT → 每集/场景的融合输入 TXT。 |
| 04 事件融合 | `merge_new_batch.py` → 共用 Batch 脚本 → `get_batch_result.py` → 共用 `debug.py` → `correct_eid.py` | 融合输入 TXT → 融合请求/响应 JSONL → 原始场景 JSON → 规范化 event ID 的 JSON。 |
| 05 描述生成 | `make_event_desc_batch_input_ep1_ep10.py` → 共用 Batch 脚本 → `get_batch_result.py` → `split.py` | 实体解析 episode DOCX + 规范化事件 JSON → 描述请求/响应 JSONL → 每场景描述 JSON。 |
| 06a MSF 事件输入 | `batch_msf.py` → `MSF.py` → `get_batch_input.py` → `get_anonymized.py` → `big5_batch.py` → 共用 Batch 脚本 → `get_output.py` → 分析脚本 | episode DOCX + 第 05 步描述 → MSF 场景数据 → 事件输入/匿名输入 → Big Five 请求/响应 → 评分 JSON 和分析结果。 |
| 06b MSF 原始文本输入 | `GET_BATCH_INPUT_utterance.py` → `replace.py` → `get_anonymized_utterance.py` → `big5_batch_utterance.py` → 共用 Batch 脚本 → 共用 `get_output.py` | MSF 场景数据 + 原始 episode DOCX → utterance 输入 → 替换后文本 → 匿名文本 → 请求/响应 → 评分 JSON。比较脚本为 `anlysis_utterance_vs_event.py`。 |

`debug.py` 只放一份：它在候选响应和融合响应阶段重复使用。`get_output.py` 也只放一份；源文件当前配置为文本分支，处理事件分支时需把输入 JSONL 和输出目录改为事件分支对应路径。

## 每个脚本的输入和输出

| 脚本 | 输入 | 输出 |
|---|---|---|
| `step00_source/get_ep.py` | season JSON | 每集原始 DOCX |
| `step00_source/get_resolved_ep.py` | season JSON | 每集实体解析 DOCX |
| `step01_candidates/scene_step1_input.py` | episode DOCX | 候选提取请求 JSONL |
| `step01_candidates/debug.py` | Batch 响应 JSONL | 按 custom ID 拆分的场景 JSON；可配置输入和输出目录，融合响应阶段复用 |
| `common/batch.py` | 请求 JSONL | 上传请求文件并创建 Batch，打印 Batch ID |
| `common/get_batch_result.py` | Batch ID、目标文件名 | 下载 Batch 响应 JSONL |
| `step02_tuple_normalization/scene_step3_direct_ep01_ep10.py` | 第 1–10 集 episode DOCX、候选 TXT | tuple 规范化请求 JSONL |
| `step02_tuple_normalization/scene_step3_direct.py` | 第 11–24 集 episode DOCX、候选 TXT | tuple 规范化请求 JSONL |
| `step02_tuple_normalization/get_candidate.py` | tuple 规范化响应 JSON | 可读 tuple TXT |
| `step03_fusion_input/get_augmented.py` | episode DOCX、tuple TXT | 按 utterance 组织的融合输入 TXT |
| `step04_fusion/merge_new_batch.py` | 融合输入 TXT | 融合请求 JSONL |
| `step04_fusion/correct_eid.py` | 原始融合 JSON | 事件 ID 规范化 JSON |
| `step05_descriptions/make_event_desc_batch_input_ep1_ep10.py` | 实体解析 episode DOCX、规范化事件 JSON | 描述请求 JSONL |
| `step05_descriptions/split.py` | 描述响应 JSONL | 按 episode/scene 拆分的描述 JSON |
| `step06_msf_event/batch_msf.py` | episode DOCX | 调用 `MSF.py` 并汇总到 MSF 场景数据目录 |
| `step06_msf_event/MSF.py` | 单集 DOCX | 该集的 MSF 场景 JSON/CSV |
| `step06_msf_event/get_batch_input.py` | MSF 场景 JSON、第五步描述 JSON | 事件式 Big Five 输入 TXT |
| `step06_msf_event/get_anonymized.py` | 事件式输入 TXT、season JSON | 匿名事件输入 TXT |
| `step06_msf_event/big5_batch.py` | 匿名事件输入 TXT | 事件式 Big Five 请求 JSONL |
| `step06_msf_text/GET_BATCH_INPUT_utterance.py` | MSF 场景 JSON | 原始 utterance 输入 TXT |
| `step06_msf_text/replace.py` | utterance 输入 TXT、episode DOCX | 替换后的 utterance TXT |
| `step06_msf_text/get_anonymized_utterance.py` | 替换后的 TXT、season JSON | 匿名 utterance TXT |
| `step06_msf_text/big5_batch_utterance.py` | 匿名 utterance TXT | 原始文本式 Big Five 请求 JSONL；脚本当前只选第 1–2 集 |
| `step06_msf_text/get_output.py` | Batch 响应 JSONL | 每个 episode/character/subscene 的评分 JSON |
| `step06_msf_analysis/run_bigfive_analysis.py` | 事件评分 JSON | 角色、episode 汇总表及图表 |
| `step06_msf_analysis/run_bigfive_analysis_scene.py` | 事件评分 JSON、对应输入 TXT | scene 级汇总及图表 |
| `step06_msf_analysis/anlysis_utterance_vs_event.py` | 事件评分 JSON、原始文本评分 JSON | 两种输入路线的比较结果 |

两个共用 Batch 脚本是本查看目录中整理的通用版本，不含密钥：`batch.py <input.jsonl>`；`get_batch_result.py <batch_id> <output.jsonl>`。运行前由环境变量 `OPENAI_API_KEY` 提供密钥。

## 数据位置

| 数据目录 | 内容 |
|---|---|
| `data/step00_raw_episode/` | Season 1 原始 JSON、原始 episode DOCX、实体解析 DOCX、替换 DOCX |
| `data/step01_candidate_extraction/` | 请求 JSONL、响应 JSONL、可读候选 TXT |
| `data/step02_tuple_normalization/` | 请求/响应 JSONL、场景 JSON、可读 tuple TXT |
| `data/step03_fusion_input/` | 融合输入 TXT、请求/响应 JSONL |
| `data/step04_fusion/` | 原始融合 JSON、规范化事件 JSON、可读事件 TXT |
| `data/step05_descriptions/` | 描述请求/响应 JSONL、场景 JSON、可读描述 TXT |
| `data/step06_msf/event_based/` | 事件路线输入、匿名输入、请求/响应、评分 JSON、分析输出 |
| `data/step06_msf/original_text_based/` | 原始 utterance、替换文本、匿名文本、请求/响应、评分 JSON |
| `data/step06_msf/shared_source/` | 两条 MSF 路线共用的场景级 MSF 输出 |
| `data/step06_msf/comparison_analysis/` | 事件路线与原始文本路线的比较结果 |

`readable_event_txt/` 和 `readable_description_txt/` 是根据同目录场景 JSON 导出的逐场景可读版本，保留 JSON 中的记录，便于人工查看与对应。

## 使用范围

此目录聚焦 Season 1 主流程。原始代码中的默认集数和路径有后续运行设置：例如 `scene_step1_input.py` 当前默认指向 S10，`make_event_desc_batch_input_ep1_ep10.py` 当前常量指向第 11–24 集。数据目录保留的是 S1 实际请求、响应和阶段结果；脚本运行时需按上述数据路径设置输入、输出及集数。
