import re
import json
import csv
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple

from docx import Document


# 不参与 peak 计数的 speaker
EXCLUDED_SPEAKERS = {"Unknown Speaker", "#ALL#", "All", ""}


def read_docx_lines(docx_path: str) -> List[str]:
    doc = Document(docx_path)
    lines = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if text:
            lines.append(text)
    return lines


def parse_friends_docx(docx_path: str) -> Dict[str, Any]:
    """
    Parse lines like:
      Episode: s01_e01
      Scene: s01_e01_c01
      [s01_e01_c01_u001] Monica Geller: There's nothing to tell!
    """
    lines = read_docx_lines(docx_path)

    episode_id = None
    scenes: Dict[str, List[Dict[str, Any]]] = {}
    current_scene = None

    utt_pat = re.compile(r"^\[(?P<uid>[^\]]+)\]\s+(?P<speaker>.*?):\s*(?P<text>.*)$")

    for line in lines:
        if line.startswith("Episode:"):
            episode_id = line.split("Episode:", 1)[1].strip()
            continue

        if line.startswith("Scene:"):
            current_scene = line.split("Scene:", 1)[1].strip()
            scenes[current_scene] = []
            continue

        m = utt_pat.match(line)
        if m and current_scene is not None:
            uid = m.group("uid").strip()
            speaker = m.group("speaker").strip()
            text = m.group("text").strip()
            scenes[current_scene].append(
                {
                    "uid": uid,
                    "speaker": speaker,
                    "text": text,
                }
            )

    return {
        "episode_id": episode_id,
        "scenes": scenes,
    }


def get_countable_utts(scene_utts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Only these utterances are used for MSF counting."""
    return [u for u in scene_utts if u["speaker"] not in EXCLUDED_SPEAKERS]


def sliding_counts(countable_utts: List[Dict[str, Any]], speaker: str, window_size: int) -> List[int]:
    counts = []
    n = len(countable_utts)
    if n < window_size:
        return counts

    for start in range(0, n - window_size + 1):
        window = countable_utts[start:start + window_size]
        c = sum(1 for u in window if u["speaker"] == speaker)
        counts.append(c)
    return counts


def find_peak_regions(counts: List[int], threshold: int) -> List[Tuple[int, int]]:
    """
    Merge consecutive windows with count >= threshold into one peak region.
    Return list of (start_window_idx, end_window_idx), inclusive.
    """
    regions = []
    in_region = False
    start = None

    for i, c in enumerate(counts):
        if c >= threshold and not in_region:
            in_region = True
            start = i
        elif c < threshold and in_region:
            regions.append((start, i - 1))
            in_region = False
            start = None

    if in_region:
        regions.append((start, len(counts) - 1))

    return regions


def expand_region_with_context(
    region_start_w: int,
    region_end_w: int,
    n_windows: int,
    context_windows: int,
) -> Tuple[int, int]:
    """
    Expand peak region by context windows on both sides.
    Return expanded window span [start_w, end_w], inclusive.
    """
    start_w = max(0, region_start_w - context_windows)
    end_w = min(n_windows - 1, region_end_w + context_windows)
    return start_w, end_w


def window_span_to_countable_utt_span(
    window_start_idx: int,
    window_end_idx: int,
    window_size: int,
) -> Tuple[int, int]:
    """
    Convert window span [w_start, w_end] into utterance span on countable utterances.
    If window size = 5:
      window 10 covers countable utterances [10..14]
      window 12 covers countable utterances [12..16]
    Merged utterance span = [10..16]
    """
    utt_start = window_start_idx
    utt_end = window_end_idx + window_size - 1
    return utt_start, utt_end


def countable_span_to_raw_uid_span(
    countable_utts: List[Dict[str, Any]],
    raw_scene_utts: List[Dict[str, Any]],
    countable_start_idx: int,
    countable_end_idx: int,
) -> Tuple[str, str, int, int]:
    """
    Convert countable utterance span back to raw utterance indices / uid span,
    so Unknown Speaker etc. between them are preserved in the final subscene.
    """
    start_uid = countable_utts[countable_start_idx]["uid"]
    end_uid = countable_utts[countable_end_idx]["uid"]

    raw_uid_to_idx = {u["uid"]: i for i, u in enumerate(raw_scene_utts)}
    raw_start_idx = raw_uid_to_idx[start_uid]
    raw_end_idx = raw_uid_to_idx[end_uid]

    return start_uid, end_uid, raw_start_idx, raw_end_idx


def msf_on_scene(
    scene_id: str,
    scene_utts: List[Dict[str, Any]],
    window_size: int = 5,
    threshold: int = 2,
    context_windows: int = 1,
) -> Dict[str, Any]:
    """
    Peak-region MSF:
      - count only non-excluded speakers
      - curve per speaker
      - consecutive windows with count >= threshold => one peak region
      - one peak region => one subscene
      - subscene = peak-region utterance span + context windows
    """
    countable_utts = get_countable_utts(scene_utts)
    speakers = sorted({u["speaker"] for u in countable_utts})

    regions_output = []
    subscenes_output = []

    n_countable = len(countable_utts)
    n_windows = max(0, n_countable - window_size + 1)

    if n_windows <= 0:
        return {
            "scene_id": scene_id,
            "peak_regions": [],
            "subscenes": [],
        }

    for speaker in speakers:
        counts = sliding_counts(countable_utts, speaker, window_size)
        peak_regions = find_peak_regions(counts, threshold)

        for region_idx, (r_start, r_end) in enumerate(peak_regions):
            # expand peak region by context windows
            exp_w_start, exp_w_end = expand_region_with_context(
                region_start_w=r_start,
                region_end_w=r_end,
                n_windows=n_windows,
                context_windows=context_windows,
            )

            # convert expanded window span to countable utt span
            countable_start_idx, countable_end_idx = window_span_to_countable_utt_span(
                exp_w_start, exp_w_end, window_size
            )

            # map countable span back to raw scene span so we preserve Unknown Speaker lines
            raw_start_uid, raw_end_uid, raw_start_idx, raw_end_idx = countable_span_to_raw_uid_span(
                countable_utts=countable_utts,
                raw_scene_utts=scene_utts,
                countable_start_idx=countable_start_idx,
                countable_end_idx=countable_end_idx,
            )

            raw_subscene_utts = scene_utts[raw_start_idx:raw_end_idx + 1]

            region_info = {
                "scene_id": scene_id,
                "main_speaker": speaker,
                "region_index_for_speaker": region_idx,
                "curve": counts,
                "threshold": threshold,
                "peak_region_window_start": r_start,
                "peak_region_window_end": r_end,
                "expanded_window_start": exp_w_start,
                "expanded_window_end": exp_w_end,
                "countable_uid_span": [
                    countable_utts[countable_start_idx]["uid"],
                    countable_utts[countable_end_idx]["uid"],
                ],
                "raw_uid_span": [raw_start_uid, raw_end_uid],
                "max_count_in_region": max(counts[r_start:r_end + 1]),
            }
            regions_output.append(region_info)

            subscene_info = {
                "scene_id": scene_id,
                "main_speaker": speaker,
                "region_index_for_speaker": region_idx,
                "peak_region_window_span": [r_start, r_end],
                "expanded_window_span": [exp_w_start, exp_w_end],
                "max_count_in_region": max(counts[r_start:r_end + 1]),
                "subscene_uid_span": [raw_start_uid, raw_end_uid],
                "utterances": raw_subscene_utts,
            }
            subscenes_output.append(subscene_info)

    return {
        "scene_id": scene_id,
        "peak_regions": regions_output,
        "subscenes": subscenes_output,
    }


def run_msf(
    docx_path: str,
    window_size: int = 5,
    threshold: int = 2,
    context_windows: int = 1,
) -> Dict[str, Any]:
    parsed = parse_friends_docx(docx_path)

    results = {
        "episode_id": parsed["episode_id"],
        "params": {
            "window_size": window_size,
            "threshold": threshold,
            "context_windows": context_windows,
            "excluded_speakers": sorted(EXCLUDED_SPEAKERS),
        },
        "scenes": {},
        "all_peak_regions": [],
        "all_subscenes": [],
    }

    for scene_id, scene_utts in parsed["scenes"].items():
        scene_result = msf_on_scene(
            scene_id=scene_id,
            scene_utts=scene_utts,
            window_size=window_size,
            threshold=threshold,
            context_windows=context_windows,
        )
        results["scenes"][scene_id] = scene_result
        results["all_peak_regions"].extend(scene_result["peak_regions"])
        results["all_subscenes"].extend(scene_result["subscenes"])

    return results


def write_outputs(results: Dict[str, Any], out_dir: str) -> None:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    with open(out_path / "msf_subscenes.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    debug_obj = {
        "episode_id": results["episode_id"],
        "params": results["params"],
        "all_peak_regions": results["all_peak_regions"],
    }
    with open(out_path / "msf_debug_peaks.json", "w", encoding="utf-8") as f:
        json.dump(debug_obj, f, ensure_ascii=False, indent=2)

    with open(out_path / "msf_subscenes.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "episode_id",
            "scene_id",
            "main_speaker",
            "region_index_for_speaker",
            "peak_region_window_start",
            "peak_region_window_end",
            "expanded_window_start",
            "expanded_window_end",
            "max_count_in_region",
            "subscene_start_uid",
            "subscene_end_uid",
            "subscene_text",
        ])

        for ss in results["all_subscenes"]:
            utt_text = "\n".join(
                f'[{u["uid"]}] {u["speaker"]}: {u["text"]}'
                for u in ss["utterances"]
            )
            writer.writerow([
                results["episode_id"],
                ss["scene_id"],
                ss["main_speaker"],
                ss["region_index_for_speaker"],
                ss["peak_region_window_span"][0],
                ss["peak_region_window_span"][1],
                ss["expanded_window_span"][0],
                ss["expanded_window_span"][1],
                ss["max_count_in_region"],
                ss["subscene_uid_span"][0],
                ss["subscene_uid_span"][1],
                utt_text,
            ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--docx",
        type=str,
        default="episode/friends_s01_e01.docx",
        help="Path to friends episode .docx, e.g. episode/friends_s01_e01.docx",
    )
    parser.add_argument("--out_dir", type=str, default="msf_output")
    parser.add_argument("--window_size", type=int, default=5)
    parser.add_argument("--threshold", type=int, default=2)
    parser.add_argument("--context_windows", type=int, default=1)
    args = parser.parse_args()

    results = run_msf(
        docx_path=args.docx,
        window_size=args.window_size,
        threshold=args.threshold,
        context_windows=args.context_windows,
    )
    write_outputs(results, args.out_dir)

    print(f"Episode: {results['episode_id']}")
    print(f"Total peak regions: {len(results['all_peak_regions'])}")
    print(f"Total subscenes: {len(results['all_subscenes'])}")
    print(f"Saved to: {args.out_dir}")


if __name__ == "__main__":
    main()