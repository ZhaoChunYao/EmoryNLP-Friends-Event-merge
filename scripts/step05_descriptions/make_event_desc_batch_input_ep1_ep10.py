#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate Batch INPUT JSONL only (NO submission) for event description step.

Inputs:
- Scene source DOCX per episode:
    resolved_episode_/friends_s01_eXX.docx
  We extract scenes by splitting on "Scene:" and taking blocks that start with "s".
  Each scene block begins with e.g. "s01_e01_c01" which we use as scene_id.

- Attachment JSON per scene:
    merge/result_id/episode_{N}/s01_e{XX}_c{YY}.json
  (episode_{N} corresponds to episode number XX, i.e. episode_1 -> e01)

Traversal:
- Iterate episode_1 ... episode_10 under merge/result_id/
- For each episode, iterate all *.json files matching s01_e??_c??.json
- For each JSON, find the corresponding scene text from the episode DOCX by scene_id.

Output:
- event_desc_batch_input_s01_ep1_ep10.jsonl (in current working directory)

Notes:
- Uses Responses API request format (url=/v1/responses) suitable for Batch API.
- Structured output schema is lab-compatible:
    top-level object; events is array; events.items is object (NOT array).
- Prompt is kept EXACTLY as provided; only {scene} and {attachment} are substituted.
"""

import json
import re
from pathlib import Path
from docx import Document  # requires python-docx installed


# -----------------------
# Config
# -----------------------
SEASON = "s01"
EP_START = 11
EP_END = 24

DOCX_DIR = Path("resolved_episode_")
MERGE_ROOT = Path("merge") / "result_id"

OUTPUT_JSONL = Path(f"event_desc_batch_input_{SEASON}_ep{EP_START}_ep{EP_END}.jsonl")

MODEL = "gpt-5"


# -----------------------
# Strict schema (lab-compatible)
# -----------------------
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["events"],
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["event_id", "description"],
                "properties": {
                    "event_id": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        }
    },
}


# -----------------------
# Prompt (MUST NOT CHANGE)
# -----------------------
PROMPT = """
First read the full scene:

{scene}

Then, for each event_id, figure out an event description of the follow form using the information in the scene:

1. For each event id, use its utterance id to find the corresponding utterance
2. In the utterance, find the speaker
3. narrate the event from the speaker's view:
the event can only be one of the following 3 cases
(1) The speaker is talking about a past event about themselves or other people. 
(2) The speaker is talking about future plan about themselves or other people. 
(3) The speaker is talking about a current action about themselves or other people. 

Your description should be: who says who is doing/has done/is planning to do what. The "who" part has already been resolved with the speaker name at the beginning of each utterance, and the standard character names written in the brackets, so just use the standard character names instead of pronouns. 

You may resolve ambiguities in the event description using the context of the scene.

Resolve pronouns and demonstratives (e.g., he, she, they, it, this, that)
to the specific characters, objects, events, or facts they refer to in the scene.

In particular, resolve non-person pronouns such as "it", "this", or "that"
when they refer to previously mentioned events, situations, or facts.

Replace vague pronouns with their explicit referents whenever possible.

Each event description must be self-contained. Do not assume that other event descriptions provide context. Resolve pronouns and omitted information so that the event description can be understood independently.

Attached File:
{attachment}
""".strip("\n")


# -----------------------
# Helpers
# -----------------------
SCENE_ID_RE = re.compile(r"^(s\d{2}_e\d{2}_c\d{2,})\b", re.IGNORECASE)
ATTACHMENT_RE = re.compile(r"^(s\d{2}_e\d{2}_c\d{2,})\.json$", re.IGNORECASE)


def read_scenes_map_from_docx(docx_path: Path) -> dict:
    """
    Returns dict: {scene_id: full_scene_text_block}
    scene_id like "s01_e01_c01"
    """
    doc = Document(str(docx_path))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    scenes_map = {}
    for block in text.split("Scene:"):
        block = block.strip()
        if not block:
            continue
        if not block.startswith("s"):
            continue
        first_line = block.splitlines()[0].strip()
        m = SCENE_ID_RE.match(first_line)
        if not m:
            continue
        scene_id = m.group(1).lower()
        scenes_map[scene_id] = block
    return scenes_map


def build_prompt(scene_text: str, attachment_text: str) -> str:
    # Do NOT paraphrase; only substitute placeholders
    return PROMPT.format(scene=scene_text, attachment=attachment_text)


def main():
    # Guards against the schema pitfalls you hit before
    assert SCHEMA.get("type") == "object"
    assert SCHEMA["properties"]["events"]["items"].get("type") == "object"

    total_reqs = 0

    with OUTPUT_JSONL.open("w", encoding="utf-8") as out:
        for ep in range(EP_START, EP_END + 1):
            episode_folder = MERGE_ROOT / f"episode_{ep}"
            if not episode_folder.exists():
                raise FileNotFoundError(f"Missing episode folder: {episode_folder}")

            docx_path = DOCX_DIR / f"friends_{SEASON}_e{ep:02d}.docx"
            if not docx_path.exists():
                raise FileNotFoundError(f"Missing DOCX: {docx_path}")

            scenes_map = read_scenes_map_from_docx(docx_path)
            if not scenes_map:
                raise ValueError(f"No scenes parsed from DOCX: {docx_path}")

            attachments = []
            for p in episode_folder.iterdir():
                if not p.is_file():
                    continue
                m = ATTACHMENT_RE.match(p.name)
                if not m:
                    continue
                scene_id = m.group(1).lower()
                attachments.append((scene_id, p))

            attachments.sort(key=lambda x: x[0])
            if not attachments:
                raise FileNotFoundError(f"No attachment json files found in: {episode_folder}")

            for scene_id, attach_path in attachments:
                if scene_id not in scenes_map:
                    raise KeyError(
                        f"Scene id {scene_id} not found in DOCX scenes map for episode {ep}. "
                        f"DOCX={docx_path} attachment={attach_path}"
                    )

                scene_text = scenes_map[scene_id]
                attachment_text = attach_path.read_text(encoding="utf-8")

                prompt = build_prompt(scene_text, attachment_text)

                req = {
                    "custom_id": f"episode_{ep}__{scene_id}",
                    "method": "POST",
                    "url": "/v1/responses",
                    "body": {
                        "model": MODEL,
                        "input": prompt,
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": "event_descriptions",
                                "strict": True,
                                "schema": SCHEMA,
                            }
                        },
                    },
                }

                out.write(json.dumps(req, ensure_ascii=False) + "\n")
                total_reqs += 1

            print(f"✅ episode_{ep}: {len(attachments)} scenes")

    print(f"\n✅ Wrote {total_reqs} requests -> {OUTPUT_JSONL}")


if __name__ == "__main__":
    main()
