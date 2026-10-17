#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

from docx import Document


# --------- configurable defaults ----------
DEFAULT_RESOLVED_DIR = Path("episode")     # contains friends_s01_eXX.docx
DEFAULT_CANDIDATES_DIR = Path("final_direct/tuples")          # contains candidates_epXX/parsed_scene_*.txt
DEFAULT_OUT_DIR = Path("merge/11_24")                      # output root

DOCX_RE = re.compile(r"^friends_(s\d+_e\d+)\.docx$")  # friends_s01_e03.docx -> s01_e03
UTT_ID_RE = re.compile(r"(s\d+_e\d+_c\d+_u\d+)")
UTT_LINE_RE = re.compile(r"^\[(s\d+_e\d+_c\d+_u\d+)\]\s*(.*)$")

# scene_id from utterance_id: s01_e03_c01_u001 -> s01_e03_c01
SCENE_FROM_UTT_RE = re.compile(r"^(s\d+_e\d+_c\d+)_u\d+$")


def parse_docx_utterances(docx_path: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Read docx and build:
      utt_map: utterance_id -> full utterance line (as plain text)
      utt2scene: utterance_id -> scene_id
    """
    doc = Document(str(docx_path))

    utt_map: Dict[str, str] = {}
    utt2scene: Dict[str, str] = {}

    for p in doc.paragraphs:
        line = (p.text or "").strip()
        if not line:
            continue

        m = UTT_LINE_RE.match(line)
        if not m:
            continue

        utt_id = m.group(1)
        if utt_id in utt_map:
            # keep first, warn
            print(f"[WARN] duplicate utterance id in docx: {utt_id} ({docx_path.name})", file=sys.stderr)
            continue

        utt_map[utt_id] = line

        sm = SCENE_FROM_UTT_RE.match(utt_id)
        if sm:
            utt2scene[utt_id] = sm.group(1)
        else:
            utt2scene[utt_id] = "unknown_scene"

    if not utt_map:
        raise RuntimeError(f"No utterance lines found in {docx_path}. "
                           f"Expected lines like: [s01_e01_c01_u001] Speaker: ...")

    return utt_map, utt2scene


def find_episode_docs(resolved_dir: Path) -> List[Path]:
    docs = []
    for p in sorted(resolved_dir.glob("friends_s*_e*.docx")):
        if DOCX_RE.match(p.name):
            docs.append(p)
    if not docs:
        raise FileNotFoundError(f"No episode docx found under: {resolved_dir}")
    return docs


def candidates_folder_for_episode(candidates_root: Path, ep_id: str) -> Path:
    """
    ep_id: s01_e03 -> candidates_ep03
    """
    # take last 2 digits of episode number
    m = re.match(r"^s\d+_e(\d+)$", ep_id)
    if not m:
        raise ValueError(f"Bad episode id from filename: {ep_id}")
    ep_num = int(m.group(1))
    return candidates_root / f"candidates_ep{ep_num:02d}"


def merge_one_episode(docx_path: Path, candidates_root: Path, out_root: Path) -> None:
    m = DOCX_RE.match(docx_path.name)
    if not m:
        print(f"[SKIP] not an episode docx: {docx_path.name}", file=sys.stderr)
        return
    ep_id = m.group(1)  # s01_e03

    utt_map, utt2scene = parse_docx_utterances(docx_path)

    cand_dir = candidates_folder_for_episode(candidates_root, ep_id)
    if not cand_dir.exists():
        raise FileNotFoundError(f"Candidates folder not found: {cand_dir}")

    tuple_files = sorted(cand_dir.glob("parsed_scene_*.txt"))
    if not tuple_files:
        raise FileNotFoundError(f"No parsed_scene_*.txt under: {cand_dir}")

    # group output lines by scene_id
    scene_out: Dict[str, List[str]] = defaultdict(list)
    missing = 0

    for in_path in tuple_files:
        with in_path.open("r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue

                um = UTT_ID_RE.search(line)
                if not um:
                    raise RuntimeError(
                        f"[ERROR] Cannot find utterance id in tuple line: "
                        f"{in_path}:{lineno}\n{line}"
                    )

                utt_id = um.group(1)
                utt_line = utt_map.get(utt_id)
                if utt_line is None:
                    print(f"[ERROR] utterance missing in docx: {utt_id} (from {in_path.name}:{lineno})",
                          file=sys.stderr)
                    missing += 1
                    continue

                scene_id = utt2scene.get(utt_id, "unknown_scene")

                # write block (tuple + utterance)
                scene_out[scene_id].append(line + "\n")
                scene_out[scene_id].append(utt_line + "\n")
                scene_out[scene_id].append("\n")

    if missing > 0:
        raise RuntimeError(f"Episode {ep_id}: merge finished but {missing} tuple lines cannot find utterance in docx")

    # write to merge/episode_XX/
    ep_num = int(re.match(r"^s\d+_e(\d+)$", ep_id).group(1))
    ep_out_dir = out_root / f"episode_{ep_num}"
    ep_out_dir.mkdir(parents=True, exist_ok=True)

    for scene_id, lines in sorted(scene_out.items()):
        # e.g. merge/episode_3/s01_e03_c01.txt
        out_path = ep_out_dir / f"{scene_id}.txt"
        out_path.write_text("".join(lines), encoding="utf-8")

    print(f"OK: {ep_id} -> {ep_out_dir} ({len(scene_out)} scenes)")


def main():
    import argparse

    ap = argparse.ArgumentParser(
        description="Batch-merge tuples (candidates_epXX/parsed_scene_*.txt) with utterances from resolved_episode_/friends_s01_eXX.docx, output per-scene files."
    )
    ap.add_argument("--resolved_dir", default=str(DEFAULT_RESOLVED_DIR), help="Directory containing friends_s01_eXX.docx")
    ap.add_argument("--candidates_dir", default=str(DEFAULT_CANDIDATES_DIR), help="Root directory containing candidates_epXX/")
    ap.add_argument("--out_dir", default=str(DEFAULT_OUT_DIR), help="Output root directory (default: merge/)")
    args = ap.parse_args()

    resolved_dir = Path(args.resolved_dir)
    candidates_dir = Path(args.candidates_dir)
    out_dir = Path(args.out_dir)

    docs = find_episode_docs(resolved_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for docx in docs:
        merge_one_episode(docx, candidates_dir, out_dir)

    print("Done.")


if __name__ == "__main__":
    main()