#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Iterable

from docx import Document


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_root(data: Any) -> List[Dict[str, Any]]:
    """
    顶层可能是 list 或 dict；统一成 list[season_obj]
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
    支持 "3-10" 或 "3,4,6,10"
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
    speakers: list[str] 或 []
    空/缺失 => "Unknown Speaker"
    非空 => ", ".join(...)
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
    out = {}
    for ep in eps:
        if isinstance(ep, dict) and ep.get("episode_id"):
            out[ep["episode_id"]] = ep
    return out


def write_episode_docx(ep: Dict[str, Any], out_path: Path) -> None:
    episode_id = ep.get("episode_id")
    if not episode_id:
        raise ValueError("Episode missing episode_id")

    doc = Document()

    # Episode header（无空行）
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

        # Scene header（无空行）
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

            # 关键：只用 transcript；不 strip、不 replace；None -> ""
            transcript = utt.get("transcript", "")
            if transcript is None:
                transcript = ""

            # 关键：即使 transcript 为空，也照样输出整行（末尾保留 ": "）
            line = f"[{utt_id}] {spk}: {transcript}"
            doc.add_paragraph(line)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))


def main():
    p = argparse.ArgumentParser(
        description="Extract Friends JSON into per-episode docx, format EXACTLY like sample."
    )
    p.add_argument("--input", default="friends_season_10.json", help="Input JSON path (default: ./friends_season_01.json)")
    p.add_argument("--outdir", default="episode", help="Output directory (default: ./episode)")
    p.add_argument("--season", default="s10", help="Season id (default: s01)")
    p.add_argument("--episodes", default="1-18", help='Episode range (default: "3-10")')
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