#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate Step3 batch INPUT JSONL only (no submission), for s01 episodes e03-e07.

Assumptions (matching your existing pipeline):
- Episode DOCX files live under: episode/friends_s01_eXX.docx
- Candidate tuple files live under: candidates/candidates_epXX/parsed_scene_YY.txt
  (YY is the scene index number; supports both zero-padded and non-padded)
- One request per scene, in scene order.

Output:
- step3_batch_input_s01_e03_e07.jsonl (in current working directory)

Notes:
- Uses Responses API format (url=/v1/responses) suitable for Batch API.
- Structured output schema is lab-compatible:
    top-level object; tuples is array; tuples.items is object (NOT array).
- Prompt text is kept identical to your Step3 wording (only {dialogue} and {tuple_text} are inserted).
"""

import json
import re
from pathlib import Path

from docx import Document  # requires python-docx installed


MODEL = "gpt-5"
SEASON = "s01"
EP_START = 11
EP_END = 24

EPISODE_DIR = Path("episode")
CANDIDATES_ROOT = Path("candidates")

OUTPUT_JSONL = Path(f"step3_batch_input_{SEASON}_e{EP_START:02d}_e{EP_END:02d}.jsonl")

# -----------------------
# STRICT schema (lab-compatible)
# -----------------------
TUPLE_SCHEMA_STEP3 = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tuples"],
    "properties": {
        "tuples": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["verb", "subject", "object", "uid"],
                "properties": {
                    "verb": {"type": "string"},
                    "subject": {"type": "string"},
                    "object": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "uid": {"type": "string"}
                },
            },
        }
    },
}

# -----------------------
# Prompt template (kept as-is)
# -----------------------
PROMPT_TEMPLATE = """For the verb of the candidate tuples, strip any auxiliaries come before the verb, move the preposition to the object.  

After this, you should see multiple tuples with the same verb:
If you found these multiple tuples are also identical/too similar in object, then keep the one with the longest object and eliminate the duplicates. 

However, if you found that the multiple tuples have substantiate different information in their object, you must keep them all

(Currently your tuples should be (verb, subject, object, uid), but if you find the tuples are not in this ordered, please adjust it to the correct order before you proceed.)
return (verb, subject, object, uid) tuples

Dialogue:
{dialogue}

Life Event Candiates:
{tuple_text}

After this, do 2 additional steps:

1. 
Resolve subject pronoun (1. if the subject is a pronoun, look at the dialogue to decide the person/entity the pronoun is pointing to, then augment the subject with a slash, i.e., I->I/(name) you->you/(name) , etc, 2. if subject is already a name, then do nothing),
2. 
lemmatize the verb
"""

def read_scenes_from_docx(path: Path):
    """Extract each scene (starting with 'Scene:') as a separate text block."""
    doc = Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    scenes = []
    for block in text.split("Scene:"):
        block = block.strip()
        if not block:
            continue
        if not block.startswith("s"):
            continue
        scenes.append(block)
    return scenes

_scene_re = re.compile(r"parsed_scene_(\d+)\.txt$", re.IGNORECASE)

def find_tuple_files(base_dir: Path):
    """Find parsed_scene_*.txt and sort by numeric scene index."""
    files = []
    if not base_dir.exists():
        return files
    for f in base_dir.iterdir():
        if not f.is_file():
            continue
        m = _scene_re.search(f.name)
        if m:
            files.append((int(m.group(1)), f))
    files.sort(key=lambda x: x[0])
    return [p for _, p in files]

def build_prompt(dialogue: str, tuple_text: str) -> str:
    return PROMPT_TEMPLATE.format(dialogue=dialogue, tuple_text=tuple_text).strip("\n")

def main():
    # guards against the exact schema mistakes you hit earlier
    assert TUPLE_SCHEMA_STEP3.get("type") == "object"
    assert TUPLE_SCHEMA_STEP3["properties"]["tuples"]["items"].get("type") == "object"

    requests = []
    total_scenes = 0

    for ep in range(EP_START, EP_END + 1):
        episode_id = f"{SEASON}_e{ep:02d}"

        docx_path = EPISODE_DIR / f"friends_{episode_id}.docx"
        if not docx_path.exists():
            raise FileNotFoundError(f"Missing episode docx: {docx_path}")

        candidates_dir = CANDIDATES_ROOT / f"candidates_ep{ep:02d}"
        tuple_files = find_tuple_files(candidates_dir)
        if not tuple_files:
            raise FileNotFoundError(f"No tuple files found in: {candidates_dir} (expected parsed_scene_*.txt)")

        dialogues = read_scenes_from_docx(docx_path)

        if len(dialogues) != len(tuple_files):
            raise ValueError(
                f"Scene count mismatch for {episode_id}: dialogues={len(dialogues)} vs tuple_files={len(tuple_files)}\n"
                f"docx={docx_path}\n"
                f"candidates_dir={candidates_dir}"
            )

        for i, (dialogue, tuple_file) in enumerate(zip(dialogues, tuple_files), start=1):
            total_scenes += 1
            with open(tuple_file, "r", encoding="utf-8") as tf:
                tuple_text = tf.read().strip()

            user_prompt = build_prompt(dialogue, tuple_text)

            req = {
                "custom_id": f"{episode_id}__scene_{i:03d}",
                "method": "POST",
                "url": "/v1/responses",
                "body": {
                    "model": MODEL,
                    "input": user_prompt,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "step3_tuples",
                            "strict": True,
                            "schema": TUPLE_SCHEMA_STEP3,
                        }
                    },
                },
            }
            requests.append(req)

        print(f"✅ Prepared {episode_id}: {len(dialogues)} scenes")

    with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
        for r in requests:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n✅ Wrote {len(requests)} requests (total scenes={total_scenes}) -> {OUTPUT_JSONL}")

if __name__ == "__main__":
    main()
