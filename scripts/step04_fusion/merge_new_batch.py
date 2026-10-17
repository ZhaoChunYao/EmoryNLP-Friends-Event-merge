#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate batch INPUT JSONL only (no submission).

Input folders:
  merge/episode_1 ... merge/episode_10
Each folder contains scene files like:
  s01_e01_cxx.txt   (also supports s01_e##_c###.txt)

Output:
  merge/batch_input_utterance_merge_ep1_ep10.jsonl

Notes:
- Prompt & schema kept identical to merge_new_batch.py (no paraphrase / no logic change).
- Uses Responses API request format (url=/v1/responses) suitable for Batch API.
"""

import json
import re
from pathlib import Path

# -------- Config --------
MODEL = "gpt-5"

MERGE_ROOT = Path("merge")  # <- 你的 merge 根目录
EP_START = 11
EP_END = 24
OUT_JSONL = MERGE_ROOT / "batch_input_utterance_merge_ep11_ep24.jsonl"

# -------- Prompt (COPY EXACTLY from your merge_new_batch.py) --------
PROMPT = """You are performing Utterance-Level Event Consolidation.

The input may contain multiple utterances. You must process each utterance independently.

For each utterance, the input contains:

A set of tuples extracted from the SAME utterance

The original utterance text

Your task:

Partition the tuples into one or more utterance-level events.
Each event must correspond to a SINGLE real-world occurrence.

You must NOT summarize, delete, reinterpret, or use knowledge outside the utterance.

Core Principle

Two tuples belong to the SAME utterance-level event
if and only if they describe the SAME real-world occurrence.

To determine this, apply the following THREE-DIMENSION TEST.

THREE-DIMENSION TEST

For each pair of tuples, check:

1️⃣ Temporal Unity

They must refer to:

The same time point, OR

A continuous, inseparable time span within the utterance

If there is explicit temporal separation (e.g., then, later, before, after, yesterday, in high school, etc.),
→ Temporal Unity fails.

If Temporal Unity fails → they belong to DIFFERENT events.

2️⃣ Participant Configuration Unity

They must share:

The same core participants (subject + primary object), OR

One tuple elaborates the same participants without replacing them.

If core participants are replaced with different entities (not refinement but substitution),
→ Participant Unity fails.

If Participant Unity fails → DIFFERENT events.

3️⃣ Action Identity Unity

They must describe:

The same action/state, OR

A semantic decomposition of the same action, OR

A cognitive/state expansion of the same occurrence
(e.g., realize X + be X)

If the predicates represent two independently occurring actions that could stand alone,
→ Action Unity fails.

If Action Unity fails → DIFFERENT events.

Decision Rule (Partition Rule)

For tuples A and B:

If ALL THREE unities hold → SAME event
If ANY unity fails → DIFFERENT event

There is NO default merging rule.
Each decision must pass all three tests.
Do NOT default to splitting. Only create a new event when at least one of the three unities clearly fails.

Procedure

Start with the first tuple → create Event 1

For each next tuple:

Compare with existing event(s)

If it satisfies all three unities with an event → assign to that event

Otherwise → create a new event

All tuples must be assigned to exactly one event.

Output Format (Strict JSON)
{
  "utterances": [
    {
      "utterance_id": "...",
      "events": [
        {
          "event_id": "...",
          "tuples": [ ... ]
        }
      ]
    }
  ]
}

Input:
{Attached File}
"""

# -------- Structured Output Schema (STRICT; top-level MUST be object) --------
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["utterances"],
    "properties": {
        "utterances": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["utterance_id", "events"],
                "properties": {
                    "utterance_id": {"type": "string"},
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["event_id", "tuples"],
                            "properties": {
                                "event_id": {"type": "string"},
                                "tuples": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
            },
        }
    },
}

def build_input(file_text: str) -> str:
    return PROMPT.replace("{Attached File}", file_text)

# matches: s01_e01_c01.txt / s01_e10_c123.txt etc
SCENE_FILE_RE = re.compile(r"^(s\d{2}_e\d{2}_c\d+)\.txt$", re.IGNORECASE)

def iter_scene_files(ep_dir: Path):
    """
    Returns list of (scene_key, path) sorted by numeric c-index when possible.
    scene_key: e.g., s01_e03_c07
    """
    items = []
    for p in ep_dir.iterdir():
        if not p.is_file():
            continue
        m = SCENE_FILE_RE.match(p.name)
        if not m:
            continue
        scene_key = m.group(1)
        # sort key: (episode, c_index)
        c_match = re.search(r"_c(\d+)$", scene_key, re.IGNORECASE)
        c_idx = int(c_match.group(1)) if c_match else 10**9
        items.append((c_idx, scene_key, p))

    items.sort(key=lambda x: x[0])
    return [(scene_key, p) for _, scene_key, p in items]

def main():
    MERGE_ROOT.mkdir(parents=True, exist_ok=True)

    total = 0
    with OUT_JSONL.open("w", encoding="utf-8") as out:
        for ep in range(EP_START, EP_END + 1):
            ep_dir = MERGE_ROOT / f"episode_{ep}"
            if not ep_dir.exists():
                raise FileNotFoundError(f"Missing folder: {ep_dir}")

            scene_files = iter_scene_files(ep_dir)
            if not scene_files:
                raise FileNotFoundError(f"No s??_e??_c*.txt found in: {ep_dir}")

            for scene_key, path in scene_files:
                file_text = path.read_text(encoding="utf-8")
                full_input = build_input(file_text)

                req = {
                    # custom_id 直接用 scene_key + episode folder，方便回溯
                    "custom_id": f"episode_{ep}__{scene_key}",
                    "method": "POST",
                    "url": "/v1/responses",
                    "body": {
                        "model": MODEL,
                        "input": full_input,
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": "utterance_event_consolidation",
                                "strict": True,
                                "schema": SCHEMA,
                            }
                        },
                    },
                }

                out.write(json.dumps(req, ensure_ascii=False) + "\n")
                total += 1

            print(f"✅ episode_{ep}: {len(scene_files)} files")

    print(f"\n✅ Wrote {total} requests -> {OUT_JSONL}")

if __name__ == "__main__":
    main()