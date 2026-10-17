#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from docx import Document
import json
from pathlib import Path

# === Structured Output Schema (STRICT) ===
# Output is a JSON object with exactly one key "tuples".
# "tuples" is an array of 4-item arrays: [verb, subject, object|null, uid]
TUPLE_SCHEMA = {
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
                    "uid": {"type": "string"},
                },
            },
        }
    },
}

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

def main():
    # 你的 episode docx 目录
    episode_dir = Path("episode")
    # 输出 jsonl（你要先检查这个文件）
    out_jsonl = Path("batch_input_s10_e01_e18.jsonl")

    # 收集 e01-e10（文件名按你目前生成方式：episode/friends_s01_e03.docx 这种）
    docx_paths = []
    for ep in range(1, 19):
        docx_paths.append(episode_dir / f"friends_s10_e{ep:02d}.docx")

    # 校验文件存在
    missing = [str(p) for p in docx_paths if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing episode docx files:\n" + "\n".join(missing))

    requests = []
    for docx_path in docx_paths:
        episode_id = docx_path.stem.replace("friends_", "")  # friends_s01_e03 -> s01_e03
        dialogues = read_scenes_from_docx(docx_path)

        for i, dialogue in enumerate(dialogues, start=1):
            user_prompt = f"""
    Life event extraction:

    Each verb is a candidate for life event.

    For each verb, make a candidate tuple (verb, subject, object), where object may be null.

    If you see prepositional phrase in a sentence more than once, then make a separate candidate for each prepositional phrase.
    Example:
    “I’m planning to sing a song in front of everybody.” ->
        (I, ’m planning to, sing a song in front of everybody)
        (I, sing, song)
        (I, sing in front of, everybody)

    === Scene ===

    {dialogue}

    return (verb, subject, object, uid) tuples (For example, if a candidate is extracted from "[s01_e01_c01_u001] Monica Geller: There's nothing to tell! He's just some guy I work with!", then the uid is s01_e01_c01_u001)
    """

            req = {
                # ✅ 关键：custom_id 编码 episode + scene序号，方便你对账/分组/排查
                "custom_id": f"{episode_id}__scene_{i:03d}",
                "method": "POST",
                "url": "/v1/responses",
                "body": {
                    "model": "gpt-5",
                    "input": user_prompt,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "utt_event_tuples",
                            "strict": True,
                            "schema": TUPLE_SCHEMA,
                        }
                    },
                },
            }
            requests.append(req)

    # 写 jsonl
    with out_jsonl.open("w", encoding="utf-8") as f:
        for req in requests:
            f.write(json.dumps(req, ensure_ascii=False) + "\n")

    print(f"✅ Wrote {len(requests)} requests to: {out_jsonl}")

if __name__ == "__main__":
    main()