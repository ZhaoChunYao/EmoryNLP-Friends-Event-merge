#!/usr/bin/env python3
"""Aggregate Big Five outputs from subscene level to scene level and save analysis artifacts.

Directory mapping:
    big_five_output_anon/<episode>/<character>/subscene_XXX.json
        <->
    big_five_input_anon/<episode>/<character>/subscene_XXX.txt

The input txt contains a line like:
    Scene: s01_e01_c01

This script uses that Scene field to group multiple subscenes into a single scene,
aggregates trait scores with a mean, writes scene-level JSON files under
big_five_output_anon_scene by default, and then runs the analysis/plotting on the
scene-level data.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TRAITS = ["EXT", "AGR", "CON", "NEU", "OPN"]
EPISODE_RE = re.compile(r"^s(\d+)_e(\d+)$", re.IGNORECASE)
SCENE_LINE_RE = re.compile(r"^\s*Scene\s*:\s*(s\d+_e\d+_c\d+)\s*$", re.IGNORECASE)
SCENE_ID_RE = re.compile(r"^s(\d+)_e(\d+)_c(\d+)$", re.IGNORECASE)


@dataclass
class SubsceneRecord:
    episode: str
    season_num: int
    episode_num: int
    character: str
    subscene: str
    scene: str
    scene_num: int
    scores: Dict[str, int]


@dataclass
class SceneRecord:
    episode: str
    season_num: int
    episode_num: int
    character: str
    scene: str
    scene_num: int
    subscenes: List[str]
    mean_scores: Dict[str, float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Big Five outputs from subscene level to scene level")
    parser.add_argument("--root", default="big_five_output_anon", help="Root output directory containing subscene JSON files")
    parser.add_argument("--input-root", default="big_five_input_anon", help="Root input directory containing matching subscene TXT files")
    parser.add_argument("--scene-root", default="big_five_output_anon_scene", help="Directory to write scene-level aggregated JSON files")
    parser.add_argument("--analysis-outdir", default="analysis_scene", help="Directory to write analysis artifacts")
    parser.add_argument("--season", default=None, help="Optional season prefix to restrict, e.g. s01")
    parser.add_argument("--min-series-length", type=int, default=4, help="Minimum scene count for change-point detection")
    return parser.parse_args()



def natural_episode_key(name: str) -> Tuple[int, int, str]:
    m = EPISODE_RE.match(name)
    if m:
        return (int(m.group(1)), int(m.group(2)), name)
    return (10**9, 10**9, name)



def natural_scene_key(scene_id: str) -> Tuple[int, int, int, str]:
    m = SCENE_ID_RE.match(scene_id)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), scene_id)
    return (10**9, 10**9, 10**9, scene_id)



def extract_scene_id(txt_path: Path) -> str:
    if not txt_path.exists():
        raise FileNotFoundError(f"Matching input txt file not found: {txt_path}")
    with txt_path.open("r", encoding="utf-8") as f:
        for line in f:
            m = SCENE_LINE_RE.match(line)
            if m:
                return m.group(1).lower()
    raise ValueError(f"Could not find Scene field in: {txt_path}")



def discover_records(root: Path, input_root: Path, season_prefix: Optional[str] = None) -> List[SubsceneRecord]:
    records: List[SubsceneRecord] = []
    if not root.exists():
        raise FileNotFoundError(f"Output root does not exist: {root}")
    if not input_root.exists():
        raise FileNotFoundError(f"Input root does not exist: {input_root}")

    for episode_dir in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: natural_episode_key(p.name)):
        if season_prefix and not episode_dir.name.startswith(season_prefix):
            continue
        match = EPISODE_RE.match(episode_dir.name)
        season_num, episode_num = (int(match.group(1)), int(match.group(2))) if match else (-1, -1)
        for character_dir in sorted([p for p in episode_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
            for json_path in sorted(character_dir.glob("*.json")):
                with json_path.open("r", encoding="utf-8") as f:
                    payload = json.load(f)

                scores: Dict[str, int] = {}
                for trait in TRAITS:
                    trait_obj = payload.get(trait)
                    if not isinstance(trait_obj, dict) or "score" not in trait_obj:
                        raise ValueError(f"Missing trait score for {trait} in {json_path}")
                    score = int(trait_obj["score"])
                    if score not in (-1, 0, 1):
                        raise ValueError(f"Unexpected score {score} for {trait} in {json_path}")
                    scores[trait] = score

                txt_path = input_root / episode_dir.name / character_dir.name / f"{json_path.stem}.txt"
                scene = extract_scene_id(txt_path)
                scene_match = SCENE_ID_RE.match(scene)
                if not scene_match:
                    raise ValueError(f"Unexpected scene id format {scene!r} in {txt_path}")

                records.append(
                    SubsceneRecord(
                        episode=episode_dir.name,
                        season_num=season_num,
                        episode_num=episode_num,
                        character=character_dir.name,
                        subscene=json_path.stem,
                        scene=scene,
                        scene_num=int(scene_match.group(3)),
                        scores=scores,
                    )
                )
    return records



def write_csv(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)



def aggregate_scene_records(records: Sequence[SubsceneRecord]) -> List[SceneRecord]:
    grouped: Dict[Tuple[str, str, str], List[SubsceneRecord]] = defaultdict(list)
    for rec in records:
        grouped[(rec.episode, rec.character, rec.scene)].append(rec)

    scene_records: List[SceneRecord] = []
    for (episode, character, scene), recs in sorted(
        grouped.items(), key=lambda kv: (natural_episode_key(kv[0][0]), kv[0][1], natural_scene_key(kv[0][2]))
    ):
        first = recs[0]
        mean_scores = {
            trait: sum(r.scores[trait] for r in recs) / len(recs)
            for trait in TRAITS
        }
        scene_records.append(
            SceneRecord(
                episode=episode,
                season_num=first.season_num,
                episode_num=first.episode_num,
                character=character,
                scene=scene,
                scene_num=first.scene_num,
                subscenes=sorted(r.subscene for r in recs),
                mean_scores=mean_scores,
            )
        )
    return scene_records



def write_scene_jsons(scene_records: Sequence[SceneRecord], scene_root: Path) -> None:
    for rec in scene_records:
        out_path = scene_root / rec.episode / rec.character / f"{rec.scene}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "episode": rec.episode,
            "character": rec.character,
            "scene": rec.scene,
            "n_subscenes": len(rec.subscenes),
            "subscenes": rec.subscenes,
            "traits": {
                trait: {
                    "mean_score": round(rec.mean_scores[trait], 6),
                }
                for trait in TRAITS
            },
        }
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)



def compute_global_summary(scene_records: Sequence[SceneRecord]) -> Tuple[List[dict], dict]:
    counts = {t: Counter() for t in TRAITS}
    sums = {t: 0.0 for t in TRAITS}
    total = len(scene_records)
    for rec in scene_records:
        for t in TRAITS:
            val = rec.mean_scores[t]
            sums[t] += val
            if val > 0:
                counts[t][1] += 1
            elif val < 0:
                counts[t][-1] += 1
            else:
                counts[t][0] += 1

    rows = []
    summary_json = {"total_scenes": total, "traits": {}}
    for t in TRAITS:
        c = counts[t]
        mean_score = sums[t] / total if total else float("nan")
        signal_rate = (c[1] + c[-1]) / total if total else float("nan")
        row = {
            "trait": t,
            "count_pos": c[1],
            "count_0": c[0],
            "count_neg": c[-1],
            "pct_pos": round(c[1] / total, 6) if total else "",
            "pct_0": round(c[0] / total, 6) if total else "",
            "pct_neg": round(c[-1] / total, 6) if total else "",
            "mean_score": round(mean_score, 6) if total else "",
            "signal_rate": round(signal_rate, 6) if total else "",
        }
        rows.append(row)
        summary_json["traits"][t] = row
    return rows, summary_json



def aggregate_scene_character_trait(scene_records: Sequence[SceneRecord]) -> List[dict]:
    rows: List[dict] = []
    for rec in sorted(scene_records, key=lambda r: (r.season_num, r.episode_num, r.scene_num, r.character)):
        for trait in TRAITS:
            rows.append(
                {
                    "episode": rec.episode,
                    "season_num": rec.season_num,
                    "episode_num": rec.episode_num,
                    "character": rec.character,
                    "scene": rec.scene,
                    "scene_num": rec.scene_num,
                    "n_subscenes": len(rec.subscenes),
                    "trait": trait,
                    "mean_score": round(rec.mean_scores[trait], 6),
                }
            )
    return rows



def aggregate_character_trait(scene_records: Sequence[SceneRecord]) -> List[dict]:
    grouped: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for rec in scene_records:
        for trait in TRAITS:
            grouped[(rec.character, trait)].append(rec.mean_scores[trait])

    rows: List[dict] = []
    for (character, trait), vals in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        n = len(vals)
        rows.append(
            {
                "character": character,
                "trait": trait,
                "n_scenes": n,
                "sum_score": round(sum(vals), 6),
                "mean_score": round(sum(vals) / n, 6) if n else "",
            }
        )
    return rows



def build_time_series(scene_rows: Sequence[dict]) -> Dict[Tuple[str, str], List[Tuple[str, float]]]:
    out: Dict[Tuple[str, str], List[Tuple[str, float]]] = defaultdict(list)
    for row in sorted(scene_rows, key=lambda r: (r["season_num"], r["episode_num"], r["scene_num"], r["character"], r["trait"])):
        out[(row["character"], row["trait"])].append((row["scene"], float(row["mean_score"])))
    return out



def detect_best_single_change(series: Sequence[float], labels: Sequence[str], min_len: int = 4) -> dict:
    n = len(series)
    if n < min_len:
        return {
            "n_points": n,
            "best_split_index": None,
            "split_after_scene": None,
            "pre_mean": None,
            "post_mean": None,
            "absolute_mean_shift": None,
            "weighted_shift_score": None,
        }
    best = None
    for split in range(1, n):
        left = series[:split]
        right = series[split:]
        left_mean = sum(left) / len(left)
        right_mean = sum(right) / len(right)
        abs_shift = abs(right_mean - left_mean)
        weight = (len(left) * len(right)) / (n * n)
        score = abs_shift * weight
        candidate = {
            "n_points": n,
            "best_split_index": split,
            "split_after_scene": labels[split - 1],
            "pre_mean": round(left_mean, 6),
            "post_mean": round(right_mean, 6),
            "absolute_mean_shift": round(abs_shift, 6),
            "weighted_shift_score": round(score, 6),
        }
        if best is None or candidate["weighted_shift_score"] > best["weighted_shift_score"]:
            best = candidate
    return best



def compare_windows(series: Sequence[float], labels: Sequence[str]) -> dict:
    n = len(series)
    if n == 0:
        return {
            "scene_first": None,
            "scene_last": None,
            "first_value": None,
            "last_value": None,
            "last_minus_first": None,
            "first_half_mean": None,
            "second_half_mean": None,
            "second_minus_first_half": None,
        }
    half = n // 2
    first_half = list(series[:half]) if half > 0 else []
    second_half = list(series[half:]) if half > 0 else []
    first_half_mean = sum(first_half) / len(first_half) if first_half else None
    second_half_mean = sum(second_half) / len(second_half) if second_half else None
    return {
        "scene_first": labels[0],
        "scene_last": labels[-1],
        "first_value": round(series[0], 6),
        "last_value": round(series[-1], 6),
        "last_minus_first": round(series[-1] - series[0], 6),
        "first_half_mean": round(first_half_mean, 6) if first_half_mean is not None else None,
        "second_half_mean": round(second_half_mean, 6) if second_half_mean is not None else None,
        "second_minus_first_half": round(second_half_mean - first_half_mean, 6) if first_half_mean is not None and second_half_mean is not None else None,
    }



def save_change_point_outputs(time_series: Dict[Tuple[str, str], List[Tuple[str, float]]], outdir: Path, min_len: int) -> None:
    rows = []
    nested = {}
    for (character, trait), pts in sorted(time_series.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        labels = [scene for scene, _ in pts]
        values = [val for _, val in pts]
        cp = detect_best_single_change(values, labels, min_len=min_len)
        comp = compare_windows(values, labels)
        row = {"character": character, "trait": trait, **cp, **comp}
        rows.append(row)
        nested.setdefault(character, {})[trait] = row
    write_csv(
        outdir / "change_points.csv",
        rows,
        [
            "character", "trait", "n_points", "best_split_index", "split_after_scene",
            "pre_mean", "post_mean", "absolute_mean_shift", "weighted_shift_score",
            "scene_first", "scene_last", "first_value", "last_value", "last_minus_first",
            "first_half_mean", "second_half_mean", "second_minus_first_half",
        ],
    )
    with (outdir / "change_points.json").open("w", encoding="utf-8") as f:
        json.dump(nested, f, ensure_ascii=False, indent=2)



def plot_character_timelines(time_series: Dict[Tuple[str, str], List[Tuple[str, float]]], outdir: Path) -> None:
    plot_dir = outdir / "plots" / "character_timelines"
    plot_dir.mkdir(parents=True, exist_ok=True)
    characters = sorted({character for character, _ in time_series})
    for character in characters:
        fig, ax = plt.subplots(figsize=(14, 5))
        max_len = 0
        xticks = None
        for trait in TRAITS:
            pts = time_series.get((character, trait), [])
            if not pts:
                continue
            scenes = [scene for scene, _ in pts]
            values = [val for _, val in pts]
            x = list(range(1, len(values) + 1))
            ax.plot(x, values, marker="o", linewidth=1.8, label=trait)
            if len(values) > max_len:
                max_len = len(values)
                xticks = scenes
        ax.axhline(0, linestyle="--", linewidth=1)
        ax.set_title(f"Scene-level mean trait trajectories: {character}")
        ax.set_xlabel("Scene order where character appears")
        ax.set_ylabel("Mean score")
        ax.set_ylim(-1.05, 1.05)
        if xticks:
            ax.set_xticks(range(1, max_len + 1))
            ax.set_xticklabels(xticks, rotation=45, ha="right")
        ax.legend(ncol=5, fontsize=9)
        fig.tight_layout()
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", character)
        fig.savefig(plot_dir / f"{safe_name}_traits.png", dpi=200)
        plt.close(fig)



def save_wide_tables(scene_rows: Sequence[dict], character_rows: Sequence[dict], outdir: Path) -> None:
    scene_mean_rows = {}
    for row in scene_rows:
        key = (row["episode"], row["scene"], row["character"])
        scene_mean_rows.setdefault(
            key,
            {"episode": row["episode"], "scene": row["scene"], "character": row["character"]},
        )[row["trait"]] = row["mean_score"]

    write_csv(outdir / "scene_character_mean_wide.csv", list(scene_mean_rows.values()), ["episode", "scene", "character", *TRAITS])

    char_mean_rows = {}
    for row in character_rows:
        key = row["character"]
        char_mean_rows.setdefault(key, {"character": key})[row["trait"]] = row["mean_score"]
    write_csv(outdir / "character_mean_wide.csv", list(char_mean_rows.values()), ["character", *TRAITS])



def main() -> None:
    args = parse_args()
    root = Path(args.root)
    input_root = Path(args.input_root)
    scene_root = Path(args.scene_root)
    analysis_outdir = Path(args.analysis_outdir)
    scene_root.mkdir(parents=True, exist_ok=True)
    analysis_outdir.mkdir(parents=True, exist_ok=True)

    records = discover_records(root, input_root, season_prefix=args.season)
    if not records:
        raise SystemExit("No subscene JSON files found.")

    scene_records = aggregate_scene_records(records)
    write_scene_jsons(scene_records, scene_root)

    global_rows, global_json = compute_global_summary(scene_records)
    write_csv(
        analysis_outdir / "global_trait_summary.csv",
        global_rows,
        ["trait", "count_pos", "count_0", "count_neg", "pct_pos", "pct_0", "pct_neg", "mean_score", "signal_rate"],
    )
    with (analysis_outdir / "global_trait_summary.json").open("w", encoding="utf-8") as f:
        json.dump(global_json, f, ensure_ascii=False, indent=2)

    scene_rows = aggregate_scene_character_trait(scene_records)
    write_csv(
        analysis_outdir / "scene_character_trait_aggregates.csv",
        scene_rows,
        ["episode", "season_num", "episode_num", "character", "scene", "scene_num", "n_subscenes", "trait", "mean_score"],
    )

    character_rows = aggregate_character_trait(scene_records)
    write_csv(
        analysis_outdir / "character_trait_aggregates.csv",
        character_rows,
        ["character", "trait", "n_scenes", "sum_score", "mean_score"],
    )

    save_wide_tables(scene_rows, character_rows, analysis_outdir)
    time_series = build_time_series(scene_rows)
    save_change_point_outputs(time_series, analysis_outdir, min_len=args.min_series_length)
    plot_character_timelines(time_series, analysis_outdir)

    manifest = {
        "input_root": str(input_root),
        "subscene_json_root": str(root),
        "scene_root": str(scene_root),
        "analysis_outdir": str(analysis_outdir),
        "total_subscenes": len(records),
        "total_scenes": len(scene_records),
        "episodes_covered": sorted({r.episode for r in records}, key=natural_episode_key),
        "characters_covered": sorted({r.character for r in records}),
        "scene_files_written": sorted(str(p.relative_to(scene_root)) for p in scene_root.rglob("*") if p.is_file()),
        "analysis_files_written": sorted(str(p.relative_to(analysis_outdir)) for p in analysis_outdir.rglob("*") if p.is_file()),
    }
    with (analysis_outdir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Wrote scene-level JSON files to: {scene_root.resolve()}")
    print(f"Wrote analysis outputs to: {analysis_outdir.resolve()}")


if __name__ == "__main__":
    main()
