#!/usr/bin/env python3
"""Aggregate Big Five subscene outputs and save analysis artifacts.

Expected input layout:
    big_five_output_anon/
        s01_e01/
            Character Name/
                subscene_001.json
                ...

Each JSON file should look like:
    {
      "EXT": {"score": 1, "evidence": "..."},
      ...
    }

Outputs are written under ./analysis by default.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TRAITS = ["EXT", "AGR", "CON", "NEU", "OPN"]
EPISODE_RE = re.compile(r"^s(\d+)_e(\d+)$", re.IGNORECASE)


@dataclass
class SubsceneRecord:
    episode: str
    season_num: int
    episode_num: int
    character: str
    subscene: str
    scores: Dict[str, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Big Five subscene outputs")
    parser.add_argument("--root", default="big_five_output_anon", help="Root input directory")
    parser.add_argument("--outdir", default="analysis", help="Output directory")
    parser.add_argument("--season", default=None, help="Optional season prefix to restrict, e.g. s01")
    parser.add_argument("--min-series-length", type=int, default=4, help="Minimum episode count for change-point detection")
    return parser.parse_args()


def natural_episode_key(name: str) -> Tuple[int, int, str]:
    m = EPISODE_RE.match(name)
    if m:
        return (int(m.group(1)), int(m.group(2)), name)
    return (10**9, 10**9, name)


def discover_records(root: Path, season_prefix: Optional[str] = None) -> List[SubsceneRecord]:
    records: List[SubsceneRecord] = []
    if not root.exists():
        raise FileNotFoundError(f"Input root does not exist: {root}")

    for episode_dir in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: natural_episode_key(p.name)):
        if season_prefix and not episode_dir.name.startswith(season_prefix):
            continue
        match = EPISODE_RE.match(episode_dir.name)
        season_num, episode_num = (int(match.group(1)), int(match.group(2))) if match else (-1, -1)
        for character_dir in sorted([p for p in episode_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
            for json_path in sorted(character_dir.glob("*.json")):
                with json_path.open("r", encoding="utf-8") as f:
                    payload = json.load(f)
                scores = {}
                for trait in TRAITS:
                    trait_obj = payload.get(trait)
                    if not isinstance(trait_obj, dict) or "score" not in trait_obj:
                        raise ValueError(f"Missing trait score for {trait} in {json_path}")
                    score = int(trait_obj["score"])
                    if score not in (-1, 0, 1):
                        raise ValueError(f"Unexpected score {score} for {trait} in {json_path}")
                    scores[trait] = score
                records.append(
                    SubsceneRecord(
                        episode=episode_dir.name,
                        season_num=season_num,
                        episode_num=episode_num,
                        character=character_dir.name,
                        subscene=json_path.stem,
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


def compute_global_summary(records: Sequence[SubsceneRecord]) -> Tuple[List[dict], dict]:
    counts = {t: Counter() for t in TRAITS}
    sums = {t: 0 for t in TRAITS}
    total = len(records)
    for rec in records:
        for t in TRAITS:
            s = rec.scores[t]
            counts[t][s] += 1
            sums[t] += s

    rows = []
    summary_json = {"total_subscenes": total, "traits": {}}
    for t in TRAITS:
        c = counts[t]
        mean_score = sums[t] / total if total else float("nan")
        signal_rate = (c[1] + c[-1]) / total if total else float("nan")
        row = {
            "trait": t,
            "count_pos1": c[1],
            "count_0": c[0],
            "count_neg1": c[-1],
            "pct_pos1": round(c[1] / total, 6) if total else "",
            "pct_0": round(c[0] / total, 6) if total else "",
            "pct_neg1": round(c[-1] / total, 6) if total else "",
            "mean_score": round(mean_score, 6) if total else "",
            "signal_rate": round(signal_rate, 6) if total else "",
        }
        rows.append(row)
        summary_json["traits"][t] = row
    return rows, summary_json


def aggregate_episode_character_trait(records: Sequence[SubsceneRecord]) -> List[dict]:
    grouped: Dict[Tuple[str, str, str], List[int]] = defaultdict(list)
    season_episode_nums: Dict[str, Tuple[int, int]] = {}
    for rec in records:
        season_episode_nums[rec.episode] = (rec.season_num, rec.episode_num)
        for trait in TRAITS:
            grouped[(rec.episode, rec.character, trait)].append(rec.scores[trait])

    rows: List[dict] = []
    for (episode, character, trait), vals in sorted(
        grouped.items(), key=lambda kv: (natural_episode_key(kv[0][0]), kv[0][1], kv[0][2])
    ):
        n = len(vals)
        pos = sum(1 for v in vals if v == 1)
        zero = sum(1 for v in vals if v == 0)
        neg = sum(1 for v in vals if v == -1)
        score_sum = sum(vals)
        mean = score_sum / n if n else float("nan")
        probs = {1: pos / n if n else float("nan"), 0: zero / n if n else float("nan"), -1: neg / n if n else float("nan")}
        max_prob = max(probs.values()) if n else float("nan")
        mode_candidates = sorted([lab for lab, p in probs.items() if p == max_prob], reverse=True)
        mode_score = mode_candidates[0] if mode_candidates else None
        rows.append(
            {
                "episode": episode,
                "season_num": season_episode_nums[episode][0],
                "episode_num": season_episode_nums[episode][1],
                "character": character,
                "trait": trait,
                "n_subscenes": n,
                "sum_score": score_sum,
                "mean_score": round(mean, 6),
                "p_pos1": round(probs[1], 6),
                "p_0": round(probs[0], 6),
                "p_neg1": round(probs[-1], 6),
                "probability_label": mode_score,
            }
        )
    return rows


def aggregate_character_trait(records: Sequence[SubsceneRecord]) -> List[dict]:
    grouped: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for rec in records:
        for trait in TRAITS:
            grouped[(rec.character, trait)].append(rec.scores[trait])

    rows: List[dict] = []
    for (character, trait), vals in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        n = len(vals)
        pos = sum(1 for v in vals if v == 1)
        zero = sum(1 for v in vals if v == 0)
        neg = sum(1 for v in vals if v == -1)
        probs = {1: pos / n if n else float("nan"), 0: zero / n if n else float("nan"), -1: neg / n if n else float("nan")}
        max_prob = max(probs.values()) if n else float("nan")
        mode_candidates = sorted([lab for lab, p in probs.items() if p == max_prob], reverse=True)
        rows.append(
            {
                "character": character,
                "trait": trait,
                "n_subscenes": n,
                "sum_score": sum(vals),
                "mean_score": round(sum(vals) / n, 6) if n else "",
                "p_pos1": round(probs[1], 6),
                "p_0": round(probs[0], 6),
                "p_neg1": round(probs[-1], 6),
                "probability_label": mode_candidates[0] if mode_candidates else "",
            }
        )
    return rows


def build_time_series(episode_rows: Sequence[dict]) -> Dict[Tuple[str, str], List[Tuple[str, float]]]:
    out: Dict[Tuple[str, str], List[Tuple[str, float]]] = defaultdict(list)
    for row in sorted(episode_rows, key=lambda r: (r["season_num"], r["episode_num"], r["character"], r["trait"])):
        out[(row["character"], row["trait"])].append((row["episode"], float(row["mean_score"])))
    return out


def detect_best_single_change(series: Sequence[float], episodes: Sequence[str], min_len: int = 4) -> dict:
    n = len(series)
    if n < min_len:
        return {
            "n_points": n,
            "best_split_index": None,
            "split_after_episode": None,
            "pre_mean": None,
            "post_mean": None,
            "absolute_mean_shift": None,
            "weighted_shift_score": None,
        }
    best = None
    for split in range(1, n):
        left = series[:split]
        right = series[split:]
        if len(left) < 1 or len(right) < 1:
            continue
        left_mean = sum(left) / len(left)
        right_mean = sum(right) / len(right)
        abs_shift = abs(right_mean - left_mean)
        weight = (len(left) * len(right)) / (n * n)
        score = abs_shift * weight
        candidate = {
            "n_points": n,
            "best_split_index": split,
            "split_after_episode": episodes[split - 1],
            "pre_mean": round(left_mean, 6),
            "post_mean": round(right_mean, 6),
            "absolute_mean_shift": round(abs_shift, 6),
            "weighted_shift_score": round(score, 6),
        }
        if best is None or candidate["weighted_shift_score"] > best["weighted_shift_score"]:
            best = candidate
    return best or {
        "n_points": n,
        "best_split_index": None,
        "split_after_episode": None,
        "pre_mean": None,
        "post_mean": None,
        "absolute_mean_shift": None,
        "weighted_shift_score": None,
    }


def compare_windows(series: Sequence[float], episodes: Sequence[str]) -> dict:
    n = len(series)
    if n == 0:
        return {
            "episode_first": None,
            "episode_last": None,
            "first_value": None,
            "last_value": None,
            "last_minus_first": None,
            "first_half_mean": None,
            "second_half_mean": None,
            "second_minus_first_half": None,
            "first_vs_second_half": None,
            "first_vs_last": None,
        }
    half = n // 2
    first_half = list(series[:half]) if half > 0 else []
    second_half = list(series[half:]) if half > 0 else []
    first_value = series[0]
    last_value = series[-1]
    first_half_mean = sum(first_half) / len(first_half) if first_half else None
    second_half_mean = sum(second_half) / len(second_half) if second_half else None
    return {
        "episode_first": episodes[0],
        "episode_last": episodes[-1],
        "first_value": round(first_value, 6),
        "last_value": round(last_value, 6),
        "last_minus_first": round(last_value - first_value, 6),
        "first_half_mean": round(first_half_mean, 6) if first_half_mean is not None else None,
        "second_half_mean": round(second_half_mean, 6) if second_half_mean is not None else None,
        "second_minus_first_half": round(second_half_mean - first_half_mean, 6) if first_half_mean is not None and second_half_mean is not None else None,
        "first_vs_second_half": round(second_half_mean - first_value, 6) if second_half_mean is not None else None,
        "first_vs_last": round(last_value - first_value, 6),
    }


def save_change_point_outputs(time_series: Dict[Tuple[str, str], List[Tuple[str, float]]], outdir: Path, min_len: int) -> None:
    rows = []
    nested = {}
    for (character, trait), pts in sorted(time_series.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        episodes = [ep for ep, _ in pts]
        values = [val for _, val in pts]
        cp = detect_best_single_change(values, episodes, min_len=min_len)
        comp = compare_windows(values, episodes)
        row = {
            "character": character,
            "trait": trait,
            **cp,
            **comp,
        }
        rows.append(row)
        nested.setdefault(character, {})[trait] = row
    write_csv(
        outdir / "change_points.csv",
        rows,
        [
            "character", "trait", "n_points", "best_split_index", "split_after_episode",
            "pre_mean", "post_mean", "absolute_mean_shift", "weighted_shift_score",
            "episode_first", "episode_last", "first_value", "last_value", "last_minus_first",
            "first_half_mean", "second_half_mean", "second_minus_first_half",
            "first_vs_second_half", "first_vs_last",
        ],
    )
    with (outdir / "change_points.json").open("w", encoding="utf-8") as f:
        json.dump(nested, f, ensure_ascii=False, indent=2)


def plot_character_timelines(time_series: Dict[Tuple[str, str], List[Tuple[str, float]]], outdir: Path) -> None:
    plot_dir = outdir / "plots" / "character_timelines"
    plot_dir.mkdir(parents=True, exist_ok=True)
    characters = sorted({character for character, _ in time_series})
    for character in characters:
        fig, ax = plt.subplots(figsize=(12, 5))
        max_len = 0
        xticks = None
        for trait in TRAITS:
            pts = time_series.get((character, trait), [])
            if not pts:
                continue
            episodes = [ep for ep, _ in pts]
            values = [val for _, val in pts]
            x = list(range(1, len(values) + 1))
            ax.plot(x, values, marker="o", linewidth=1.8, label=trait)
            if len(values) > max_len:
                max_len = len(values)
                xticks = episodes
        ax.axhline(0, linestyle="--", linewidth=1)
        ax.set_title(f"Episode-level mean trait trajectories: {character}")
        ax.set_xlabel("Episode order where character appears")
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


def save_wide_tables(episode_rows: Sequence[dict], character_rows: Sequence[dict], outdir: Path) -> None:
    # Episode x character wide table using mean/sum/probability label.
    mean_rows = {}
    sum_rows = {}
    label_rows = {}
    prob_rows = {}
    for row in episode_rows:
        key = (row["episode"], row["character"])
        mean_rows.setdefault(key, {"episode": row["episode"], "character": row["character"]})[row["trait"]] = row["mean_score"]
        sum_rows.setdefault(key, {"episode": row["episode"], "character": row["character"]})[row["trait"]] = row["sum_score"]
        label_rows.setdefault(key, {"episode": row["episode"], "character": row["character"]})[row["trait"]] = row["probability_label"]
        prob_rows.setdefault(key, {"episode": row["episode"], "character": row["character"]})[f"{row['trait']}_p_pos1"] = row["p_pos1"]
        prob_rows[key][f"{row['trait']}_p_0"] = row["p_0"]
        prob_rows[key][f"{row['trait']}_p_neg1"] = row["p_neg1"]

    write_csv(outdir / "episode_character_mean_wide.csv", list(mean_rows.values()), ["episode", "character", *TRAITS])
    write_csv(outdir / "episode_character_sum_wide.csv", list(sum_rows.values()), ["episode", "character", *TRAITS])
    write_csv(outdir / "episode_character_probability_label_wide.csv", list(label_rows.values()), ["episode", "character", *TRAITS])
    prob_fields = ["episode", "character"] + [f"{t}_p_{lab}" for t in TRAITS for lab in ("pos1", "0", "neg1")]
    write_csv(outdir / "episode_character_probabilities_wide.csv", list(prob_rows.values()), prob_fields)

    char_mean_rows = {}
    char_sum_rows = {}
    char_label_rows = {}
    char_prob_rows = {}
    for row in character_rows:
        key = row["character"]
        char_mean_rows.setdefault(key, {"character": key})[row["trait"]] = row["mean_score"]
        char_sum_rows.setdefault(key, {"character": key})[row["trait"]] = row["sum_score"]
        char_label_rows.setdefault(key, {"character": key})[row["trait"]] = row["probability_label"]
        char_prob_rows.setdefault(key, {"character": key})[f"{row['trait']}_p_pos1"] = row["p_pos1"]
        char_prob_rows[key][f"{row['trait']}_p_0"] = row["p_0"]
        char_prob_rows[key][f"{row['trait']}_p_neg1"] = row["p_neg1"]

    write_csv(outdir / "character_mean_wide.csv", list(char_mean_rows.values()), ["character", *TRAITS])
    write_csv(outdir / "character_sum_wide.csv", list(char_sum_rows.values()), ["character", *TRAITS])
    write_csv(outdir / "character_probability_label_wide.csv", list(char_label_rows.values()), ["character", *TRAITS])
    char_prob_fields = ["character"] + [f"{t}_p_{lab}" for t in TRAITS for lab in ("pos1", "0", "neg1")]
    write_csv(outdir / "character_probabilities_wide.csv", list(char_prob_rows.values()), char_prob_fields)


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    records = discover_records(root, season_prefix=args.season)
    if not records:
        raise SystemExit("No subscene JSON files found.")

    global_rows, global_json = compute_global_summary(records)
    write_csv(
        outdir / "global_trait_summary.csv",
        global_rows,
        [
            "trait", "count_pos1", "count_0", "count_neg1",
            "pct_pos1", "pct_0", "pct_neg1", "mean_score", "signal_rate",
        ],
    )
    with (outdir / "global_trait_summary.json").open("w", encoding="utf-8") as f:
        json.dump(global_json, f, ensure_ascii=False, indent=2)

    episode_rows = aggregate_episode_character_trait(records)
    write_csv(
        outdir / "episode_character_trait_aggregates.csv",
        episode_rows,
        [
            "episode", "season_num", "episode_num", "character", "trait", "n_subscenes",
            "sum_score", "mean_score", "p_pos1", "p_0", "p_neg1", "probability_label",
        ],
    )

    character_rows = aggregate_character_trait(records)
    write_csv(
        outdir / "character_trait_aggregates.csv",
        character_rows,
        [
            "character", "trait", "n_subscenes", "sum_score", "mean_score",
            "p_pos1", "p_0", "p_neg1", "probability_label",
        ],
    )

    save_wide_tables(episode_rows, character_rows, outdir)
    time_series = build_time_series(episode_rows)
    save_change_point_outputs(time_series, outdir, min_len=args.min_series_length)
    plot_character_timelines(time_series, outdir)

    manifest = {
        "input_root": str(root),
        "output_dir": str(outdir),
        "total_subscenes": len(records),
        "episodes_covered": sorted({r.episode for r in records}, key=natural_episode_key),
        "characters_covered": sorted({r.character for r in records}),
        "files_written": sorted(str(p.relative_to(outdir)) for p in outdir.rglob("*") if p.is_file()),
    }
    with (outdir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Wrote analysis outputs to: {outdir.resolve()}")


if __name__ == "__main__":
    main()
