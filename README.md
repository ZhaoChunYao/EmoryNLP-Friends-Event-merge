# EmoryNLP Season 1 Pipeline

Source directory: `C:\Users\ZhaoC\Desktop\EmoryNLP`. This folder is for viewing and cross-checking and is uncompressed; its top level contains only `scripts/`, `data/`, and this README. The data covers the main workflow for Season 1, Episodes 1–24, and its two MSF input routes.

## End-to-End Pipeline

| Step | Script order | Input → Output |
|---|---|---|
| 00 Raw episodes | `get_ep.py`; additionally, `get_resolved_ep.py` | `friends_season_01.json` → raw episode DOCX files; the resolved-version script generates entity-resolved DOCX files from the same JSON. |
| 01 Candidate extraction | `scene_step1_input.py` → `batch.py` → `get_batch_result.py` → `debug.py` | Episode DOCX → candidate request JSONL → Batch response JSONL → candidate JSON for each episode/scene. |
| 02 Tuple normalization | `scene_step3_direct_ep01_ep10.py` (Episodes 1–10) or `scene_step3_direct.py` (Episodes 11–24) → shared Batch script → `get_batch_result.py` → `get_candidate.py` | Episode DOCX + candidate TXT → normalization request/response JSONL → per-scene JSON + readable tuple TXT. |
| 03 Fusion input | `get_augmented.py` | Raw episode DOCX + normalized tuple TXT → fusion input TXT for each episode/scene. |
| 04 Event fusion | `merge_new_batch.py` → shared Batch script → `get_batch_result.py` → shared `debug.py` → `correct_eid.py` | Fusion input TXT → fusion request/response JSONL → raw scene JSON → JSON with normalized event IDs. |
| 05 Description generation | `make_event_desc_batch_input_ep1_ep10.py` → shared Batch script → `get_batch_result.py` → `split.py` | Entity-resolved episode DOCX + normalized event JSON → description request/response JSONL → per-scene description JSON. |
| 06a MSF event input | `batch_msf.py` → `MSF.py` → `get_batch_input.py` → `get_anonymized.py` → `big5_batch.py` → shared Batch script → `get_output.py` → analysis scripts | Episode DOCX + Step 05 descriptions → MSF scene data → event input/anonymized input → Big Five request/response → scoring JSON and analysis results. |
| 06b MSF original-text input | `GET_BATCH_INPUT_utterance.py` → `replace.py` → `get_anonymized_utterance.py` → `big5_batch_utterance.py` → shared Batch script → shared `get_output.py` | MSF scene data + raw episode DOCX → utterance input → replaced text → anonymized text → request/response → scoring JSON. The comparison script is `anlysis_utterance_vs_event.py`. |

Only one copy of `debug.py` is included: it is reused at the candidate-response and fusion-response stages. Only one copy of `get_output.py` is included as well; the source file is currently configured for the text branch. To process the event branch, change the input JSONL and output directory to the corresponding event-branch paths.

## Inputs and Outputs of Each Script

| Script | Input | Output |
|---|---|---|
| `step00_source/get_ep.py` | Season JSON | Raw DOCX for each episode |
| `step00_source/get_resolved_ep.py` | Season JSON | Entity-resolved DOCX for each episode |
| `step01_candidates/scene_step1_input.py` | Episode DOCX | Candidate-extraction request JSONL |
| `step01_candidates/debug.py` | Batch response JSONL | Scene JSON split by custom ID; input and output directories can be configured, and the script is reused at the fusion-response stage |
| `common/batch.py` | Request JSONL | Uploads the request file, creates a Batch, and prints the Batch ID |
| `common/get_batch_result.py` | Batch ID, target filename | Downloads the Batch response JSONL |
| `step02_tuple_normalization/scene_step3_direct_ep01_ep10.py` | Episode DOCX for Episodes 1–10, candidate TXT | Tuple-normalization request JSONL |
| `step02_tuple_normalization/scene_step3_direct.py` | Episode DOCX for Episodes 11–24, candidate TXT | Tuple-normalization request JSONL |
| `step02_tuple_normalization/get_candidate.py` | Tuple-normalization response JSON | Readable tuple TXT |
| `step03_fusion_input/get_augmented.py` | Episode DOCX, tuple TXT | Fusion input TXT organized by utterance |
| `step04_fusion/merge_new_batch.py` | Fusion input TXT | Fusion request JSONL |
| `step04_fusion/correct_eid.py` | Raw fusion JSON | JSON with normalized event IDs |
| `step05_descriptions/make_event_desc_batch_input_ep1_ep10.py` | Entity-resolved episode DOCX, normalized event JSON | Description request JSONL |
| `step05_descriptions/split.py` | Description response JSONL | Description JSON split by episode/scene |
| `step06_msf_event/batch_msf.py` | Episode DOCX | Calls `MSF.py` and aggregates the results in the MSF scene-data directory |
| `step06_msf_event/MSF.py` | Single-episode DOCX | MSF scene JSON/CSV for that episode |
| `step06_msf_event/get_batch_input.py` | MSF scene JSON, Step 05 description JSON | Event-based Big Five input TXT |
| `step06_msf_event/get_anonymized.py` | Event-based input TXT, Season JSON | Anonymized event input TXT |
| `step06_msf_event/big5_batch.py` | Anonymized event input TXT | Event-based Big Five request JSONL |
| `step06_msf_text/GET_BATCH_INPUT_utterance.py` | MSF scene JSON | Raw utterance input TXT |
| `step06_msf_text/replace.py` | Utterance input TXT, episode DOCX | Replaced utterance TXT |
| `step06_msf_text/get_anonymized_utterance.py` | Replaced TXT, Season JSON | Anonymized utterance TXT |
| `step06_msf_text/big5_batch_utterance.py` | Anonymized utterance TXT | Original-text Big Five request JSONL; the script currently selects only Episodes 1–2 |
| `step06_msf_text/get_output.py` | Batch response JSONL | Scoring JSON for each episode/character/subscene |
| `step06_msf_analysis/run_bigfive_analysis.py` | Event scoring JSON | Character and episode summary tables and charts |
| `step06_msf_analysis/run_bigfive_analysis_scene.py` | Event scoring JSON, corresponding input TXT | Scene-level summaries and charts |
| `step06_msf_analysis/anlysis_utterance_vs_event.py` | Event scoring JSON, original-text scoring JSON | Comparison results for the two input routes |

The two shared Batch scripts in this review folder are generic versions and contain no key: `batch.py <input.jsonl>`; `get_batch_result.py <batch_id> <output.jsonl>`. Before running them, provide the key through the `OPENAI_API_KEY` environment variable.

## Data Locations

| Data directory | Contents |
|---|---|
| `data/step00_raw_episode/` | Season 1 source JSON, raw episode DOCX, entity-resolved DOCX, and replaced DOCX |
| `data/step01_candidate_extraction/` | Request JSONL, response JSONL, readable candidate TXT |
| `data/step02_tuple_normalization/` | Request/response JSONL, scene JSON, readable tuple TXT |
| `data/step03_fusion_input/` | Fusion input TXT, request/response JSONL |
| `data/step04_fusion/` | Raw fusion JSON, normalized event JSON, readable event TXT |
| `data/step05_descriptions/` | Description request/response JSONL, scene JSON, readable description TXT |
| `data/step06_msf/event_based/` | Event-route input, anonymized input, requests/responses, scoring JSON, analysis output |
| `data/step06_msf/original_text_based/` | Raw utterances, replaced text, anonymized text, requests/responses, scoring JSON |
| `data/step06_msf/shared_source/` | Scene-level MSF output shared by both routes |
| `data/step06_msf/comparison_analysis/` | Comparison results for the event route and original-text route |

`readable_event_txt/` and `readable_description_txt/` are per-scene readable versions exported from the scene JSON in the same directory. They preserve the records in the JSON and make them easier to inspect and match.

## Research Summary

The project studies long-term memory for LLMs: what events an LLM should remember and what events it should forget in conversations far beyond its context window. The foundation for all of this is defining what counts as “the same event” or “the same piece of information.” The text must first be examined for all mentions, repetitions, and additions that refer to the same event, and these must be merged as one event. This merging step is the foundation for everything that follows.

My final result was a definition that turned out to be too narrow. I had GPT process the data according to this definition and produce a set of merged events. I then found that the definition was indeed too narrow to support further cross-event merging.

- Readable merged-event data: `data/step04_fusion/readable_event_txt/`
- Definition and batch-processing script: `scripts/step04_fusion/merge_new_batch.py`
