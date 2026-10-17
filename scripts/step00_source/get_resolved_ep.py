#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from docx import Document


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_root(data: Any) -> List[Dict[str, Any]]:
    """
    Top level could be list or dict; normalize to list[season_obj]
    (Same behavior as get_ep.py)
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "season_id" in data and "episodes" in data:
            return [data]
        if "seasons" in data and isinstance(data["seasons"], list):
            return data["seasons"]
    raise ValueError("Unrecognized JSON structure at root.")


def parse_episode_range(spec: str) -> List[int]:
    """
    Supports "3-10" or "3,4,6,10"
    (Same behavior as get_ep.py)
    """
    spec = spec.strip()
    if "-" in spec:
        a, b = spec.split("-", 1)
        a, b = int(a), int(b)
        if a > b:
            a, b = b, a
        return list(range(a, b + 1))
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    return [int(p) for p in parts]


def speaker_string(speakers: Any) -> str:
    """
    speakers: list[str] or []
    empty/missing => "Unknown Speaker"
    non-empty => ", ".join(...)
    (Same behavior as get_ep.py)
    """
    if not speakers:
        return "Unknown Speaker"
    if isinstance(speakers, list):
        return ", ".join(str(s) for s in speakers)
    return str(speakers)


def find_season(seasons: List[Dict[str, Any]], season_id: str) -> Dict[str, Any]:
    for s in seasons:
        if isinstance(s, dict) and s.get("season_id") == season_id:
            return s
    raise ValueError(f"Season not found: {season_id}")


def episodes_by_id(season_obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    eps = season_obj.get("episodes", [])
    if not isinstance(eps, list):
        raise ValueError("season.episodes is not a list")
    out: Dict[str, Dict[str, Any]] = {}
    for ep in eps:
        if isinstance(ep, dict) and ep.get("episode_id"):
            out[ep["episode_id"]] = ep
    return out


# -----------------------------
# NEW: entity-aware transcript resolver
# -----------------------------

_NO_SPACE_BEFORE = {
    ".", ",", "!", "?", ";", ":", ")", "]", "}", "%", "…",
    "?!", "!!",
}
_NO_SPACE_AFTER = {"(", "[", "{", '"', "“", "‘"}
_ATTACH_TO_PREV = {
    "'s", "’s", "n't", "’t", "'re", "’re", "'m", "’m", "'ll", "’ll", "'d", "’d", "'ve", "’ve"
}


def detokenize(tokens: List[str]) -> str:
    """
    Heuristic detokenizer that works reasonably with the provided Friends tokenization.
    Goal: produce human-like text, not necessarily byte-identical to original transcript.
    """
    out: List[str] = []
    for tok in tokens:
        if not out:
            out.append(tok)
            continue

        prev = out[-1]

        # Attach contractions/possessives to previous token
        if tok in _ATTACH_TO_PREV:
            out[-1] = prev + tok
            continue

        # Ellipsis sometimes appears as "..." token
        if tok == "..." or tok == "…":
            out[-1] = prev + tok
            continue

        # No space before punctuation
        if tok in _NO_SPACE_BEFORE:
            out[-1] = prev + tok
            continue

        # If previous is an opening bracket/quote, no leading space
        if prev in _NO_SPACE_AFTER:
            out[-1] = prev + tok
            continue

        # Default: add space
        out.append(" " + tok)

    return "".join(out)


def normalize_token_sentences(tokens_field: Any) -> List[List[str]]:
    """
    tokens can be:
      - list[list[str]] (common)
      - list[str] (rare)
      - [] / None
    Normalize to list[list[str]]
    """
    if tokens_field is None:
        return []
    if not isinstance(tokens_field, list):
        return []
    if len(tokens_field) == 0:
        return []
    if all(isinstance(x, str) for x in tokens_field):
        return [tokens_field]  # single sentence
    # assume list of lists
    return [x for x in tokens_field if isinstance(x, list)]


def normalize_entities_sentences(ents_field: Any, n_sent: int) -> List[List[List[Any]]]:
    """
    character_entities typically aligns with tokens as list[list[span]].
    Return list per sentence, padded/truncated to n_sent.
    """
    if not isinstance(ents_field, list):
        return [[] for _ in range(n_sent)]

    ents: List[List[List[Any]]] = []
    for item in ents_field:
        if isinstance(item, list):
            ents.append(item)
        else:
            ents.append([])

    if len(ents) < n_sent:
        ents.extend([[] for _ in range(n_sent - len(ents))])
    if len(ents) > n_sent:
        ents = ents[:n_sent]
    return ents


def span_replacement_text(span: List[Any]) -> Optional[str]:
    """
    span format: [start, end, "Name"] or [start, end, "Name1", "Name2", ...]
    If multiple names, join with ' and '.
    """
    if not isinstance(span, list) or len(span) < 3:
        return None
    names = [str(x) for x in span[2:] if x is not None]
    if not names:
        return None

    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for n in names:
        if n not in seen:
            uniq.append(n)
            seen.add(n)

    if len(uniq) == 1:
        return uniq[0]
    return " and ".join(uniq)

'''
def resolve_tokens_with_entities(tokens: List[str], spans: List[List[Any]]) -> List[str]:
    """
    Replace token spans [start,end) with canonical entity name token(s).
    We insert the replacement as a SINGLE token (may contain spaces);
    detokenize() will handle it as one chunk.
    Assumes spans are within-bounds and mostly non-overlapping.
    """
    # Build mapping from start -> (end, repl)
    start_map: Dict[int, Tuple[int, str]] = {}
    for sp in spans:
        if not isinstance(sp, list) or len(sp) < 3:
            continue
        try:
            start = int(sp[0])
            end = int(sp[1])
        except Exception:
            continue
        if start < 0 or end <= start:
            continue
        repl = span_replacement_text(sp)
        if repl is None:
            continue
        # If conflict, keep the longer span (simple tie-break)
        if start in start_map:
            prev_end, _ = start_map[start]
            if end > prev_end:
                start_map[start] = (end, repl)
        else:
            start_map[start] = (end, repl)

    resolved: List[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        if i in start_map:
            end, repl = start_map[i]
            end = min(end, n)
            resolved.append(repl)
            i = end
            continue
        resolved.append(tokens[i])
        i += 1
    return resolved
'''

'''
def resolve_tokens_with_entities(tokens: List[str], spans: List[List[Any]]) -> List[str]:
    """
    Instead of replacing token span, annotate the first token:

    He -> He (Paul the Wine Guy)
    """

    start_map = {}

    for sp in spans:
        if len(sp) < 3:
            continue

        start = int(sp[0])
        end = int(sp[1])
        names = sp[2:]

        names = list(dict.fromkeys(names))
        name_str = " and ".join(names)

        start_map[start] = (end, name_str)

    resolved = []
    i = 0
    n = len(tokens)

    while i < n:

        if i in start_map:
            end, name = start_map[i]

            token = tokens[i]

            resolved.append(f"{token} ({name})")

            # keep remaining tokens of span unchanged
            for j in range(i+1, min(end, n)):
                resolved.append(tokens[j])

            i = end
            continue

        resolved.append(tokens[i])
        i += 1

    return resolved
'''

def resolve_tokens_with_entities(tokens: List[str], spans: List[List[Any]]) -> List[str]:
    """
    Replace token spans [start, end) with canonical entity name token(s).
    The replacement is inserted as a single token string, which may contain spaces.
    detokenize() will keep it as one chunk.

    Example:
      ["He", "'s"] + span [0,1,"Paul the Wine Guy"]
      -> ["Paul the Wine Guy", "'s"]
      -> "Paul the Wine Guy's"
    """
    start_map: Dict[int, Tuple[int, str]] = {}

    for sp in spans:
        if not isinstance(sp, list) or len(sp) < 3:
            continue

        try:
            start = int(sp[0])
            end = int(sp[1])
        except Exception:
            continue

        if start < 0 or end <= start:
            continue

        repl = span_replacement_text(sp)
        if repl is None:
            continue

        # same start: keep longer span
        if start in start_map:
            prev_end, _ = start_map[start]
            if end > prev_end:
                start_map[start] = (end, repl)
        else:
            start_map[start] = (end, repl)

    resolved: List[str] = []
    i = 0
    n = len(tokens)

    while i < n:
        if i in start_map:
            end, repl = start_map[i]
            end = min(end, n)
            resolved.append(repl)
            i = end
            continue

        resolved.append(tokens[i])
        i += 1

    return resolved


def resolve_transcript(utt: Dict[str, Any]) -> str:
    """
    If tokens + character_entities exist, rebuild a resolved transcript from them.
    Otherwise, fall back to original transcript (exactly like get_ep.py uses).
    """
    transcript = utt.get("transcript", "")
    if transcript is None:
        transcript = ""

    token_sents = normalize_token_sentences(utt.get("tokens"))
    if not token_sents:
        return transcript

    ent_sents = normalize_entities_sentences(utt.get("character_entities"), len(token_sents))

    resolved_sent_texts: List[str] = []
    for toks, spans in zip(token_sents, ent_sents):
        if not toks:
            continue
        if not isinstance(spans, list):
            spans = []
        new_toks = resolve_tokens_with_entities([str(t) for t in toks], spans)
        resolved_sent_texts.append(detokenize(new_toks))

    # Join sentence chunks with a single space (common in original transcripts)
    resolved = " ".join(t for t in resolved_sent_texts if t is not None)

    # If something went wrong and we produced empty while original had content, fall back
    if resolved.strip() == "" and transcript.strip() != "":
        return transcript

    return resolved


def write_episode_docx(ep: Dict[str, Any], out_path: Path) -> None:
    """
    Same output structure as get_ep.py:
      Episode header line
      Scene header line(s)
      Then each utterance line: "[utt_id] Speaker: transcript"
    Only change: transcript is entity-resolved.
    """
    episode_id = ep.get("episode_id")
    if not episode_id:
        raise ValueError("Episode missing episode_id")

    doc = Document()

    # Episode header（no blank lines）
    doc.add_paragraph(f"Episode: {episode_id}")

    scenes = ep.get("scenes", [])
    if not isinstance(scenes, list):
        raise ValueError(f"{episode_id}.scenes is not a list")

    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        scene_id = sc.get("scene_id")
        if not scene_id:
            raise ValueError(f"{episode_id} has a scene missing scene_id")

        # Scene header（no blank lines）
        doc.add_paragraph(f"Scene: {scene_id}")

        utterances = sc.get("utterances", [])
        if not isinstance(utterances, list):
            raise ValueError(f"{scene_id}.utterances is not a list")

        for utt in utterances:
            if not isinstance(utt, dict):
                continue

            utt_id = utt.get("utterance_id")
            if not utt_id:
                raise ValueError(f"{scene_id} has utterance missing utterance_id")

            spk = speaker_string(utt.get("speakers", []))

            # NEW: resolved transcript (but keep the "None -> ''" rule)
            resolved = resolve_transcript(utt)
            if resolved is None:
                resolved = ""

            # Same rule: even if transcript is empty, still output ": "
            line = f"[{utt_id}] {spk}: {resolved}"
            doc.add_paragraph(line)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))


def main():
    p = argparse.ArgumentParser(
        description="Extract Friends JSON into per-episode docx, same format as get_ep.py, but resolves character entities."
    )
    p.add_argument("--input", default="friends_season_01.json", help="Input JSON path (default: ./friends_season_01.json)")
    p.add_argument("--outdir", default="replaced_episode", help="Output directory (default: ./episode)")
    p.add_argument("--season", default="s01", help="Season id (default: s01)")
    p.add_argument("--episodes", default="1-24", help='Episode range (default: "3-10")')
    args = p.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.outdir)
    season_id = args.season
    ep_nums = parse_episode_range(args.episodes)

    data = load_json(in_path)
    seasons = normalize_root(data)
    season_obj = find_season(seasons, season_id)
    ep_map = episodes_by_id(season_obj)

    for n in ep_nums:
        eid = f"{season_id}_e{n:02d}"
        ep = ep_map.get(eid)
        if ep is None:
            raise ValueError(f"Episode not found in JSON: {eid}")

        out_path = out_dir / f"friends_{eid}.docx"
        write_episode_docx(ep, out_path)


if __name__ == "__main__":
    main()