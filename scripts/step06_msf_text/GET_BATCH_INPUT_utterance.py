import json
import argparse
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any


MSF_OUTPUT_DIR = Path("msf_output")
BIG_FIVE_OUTPUT_DIR = Path("big_five_input_utterance")

EPISODE_DIR_PATTERN = re.compile(r"^friends_s\d{2}_e\d{2}$", re.IGNORECASE)
EPISODE_SEASON_PATTERN = re.compile(r"^friends_s(?P<season>\d{2})_e\d{2}$", re.IGNORECASE)


def load_json(json_path: Path) -> Dict[str, Any]:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name


def normalize_season_arg(season: str) -> str:
    season = season.strip().lower()
    if season == "all":
        return "all"

    if season.isdigit():
        return f"{int(season):02d}"

    raise ValueError("season must be 'all' or an integer like 1 / 10")


def episode_matches_season(episode_dir_name: str, season_filter: str) -> bool:
    if season_filter == "all":
        return True

    m = EPISODE_SEASON_PATTERN.match(episode_dir_name)
    if not m:
        return False

    return m.group("season") == season_filter


def format_subscene_text(
    episode_id: str,
    speaker_subscene_index: int,
    subscene: Dict[str, Any],
) -> str:
    scene_id = str(subscene.get("scene_id", "")).strip()
    main_speaker = str(subscene.get("main_speaker", "")).strip()
    uid_span = subscene.get("subscene_uid_span", ["", ""])
    peak_span = subscene.get("peak_region_window_span", ["", ""])
    utterances = subscene.get("utterances", [])

    lines: List[str] = []
    lines.append(f"Episode: {episode_id}")
    lines.append(f"Scene: {scene_id}")
    lines.append(f"Subscene index for speaker: {speaker_subscene_index:03d}")
    lines.append(f"Main speaker: {main_speaker}")
    lines.append(f"UID span: {uid_span[0]} → {uid_span[1]}")
    lines.append(f"Peak window: {peak_span[0]} → {peak_span[1]}")
    lines.append("")
    lines.append("Dialogue:")

    if not isinstance(utterances, list):
        utterances = []

    for utt in utterances:
        if not isinstance(utt, dict):
            continue

        uid = str(utt.get("uid", "")).strip()
        speaker = str(utt.get("speaker", "")).strip()
        text = str(utt.get("text", "")).strip()

        if not uid:
            continue

        lines.append(f"  [{uid}] {speaker}: {text}")

    lines.append("")
    return "\n".join(lines)


def process_episode_json(msf_json_path: Path, output_root: Path) -> None:
    data = load_json(msf_json_path)

    episode_id = data.get("episode_id") or msf_json_path.parent.name
    all_subscenes = data.get("all_subscenes", [])

    if not isinstance(all_subscenes, list):
        print(f"[WARN] Invalid all_subscenes in {msf_json_path}")
        return

    speaker_counters: Dict[str, int] = defaultdict(int)

    for subscene in all_subscenes:
        if not isinstance(subscene, dict):
            continue

        scene_id = str(subscene.get("scene_id", "")).strip()
        main_speaker = str(subscene.get("main_speaker", "")).strip()

        if not scene_id or not main_speaker:
            print(f"[WARN] Skip malformed subscene in {msf_json_path}")
            continue

        speaker_counters[main_speaker] += 1
        subscene_idx = speaker_counters[main_speaker]

        text = format_subscene_text(
            episode_id=episode_id,
            speaker_subscene_index=subscene_idx,
            subscene=subscene,
        )

        speaker_dir = output_root / episode_id / safe_name(main_speaker)
        ensure_dir(speaker_dir)

        out_path = speaker_dir / f"subscene_{subscene_idx:03d}.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)

        print(f"[OK] {out_path}")


def find_episode_jsons(msf_output_dir: Path, season_filter: str) -> List[Path]:
    paths: List[Path] = []

    if not msf_output_dir.exists():
        return paths

    for child in sorted(msf_output_dir.iterdir()):
        if not child.is_dir():
            continue
        if not EPISODE_DIR_PATTERN.match(child.name):
            continue
        if not episode_matches_season(child.name, season_filter):
            continue

        json_path = child / "msf_subscenes.json"
        if json_path.exists():
            paths.append(json_path)

    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--msf_output_dir", default=str(MSF_OUTPUT_DIR))
    parser.add_argument("--out_dir", default=str(BIG_FIVE_OUTPUT_DIR))
    parser.add_argument(
        "--season",
        default="1",
        help="Season to process: 'all', '1', '10', etc.",
    )
    args = parser.parse_args()

    msf_output_dir = Path(args.msf_output_dir)
    out_dir = Path(args.out_dir)
    season_filter = normalize_season_arg(args.season)

    ensure_dir(out_dir)

    episode_jsons = find_episode_jsons(msf_output_dir, season_filter)
    if not episode_jsons:
        print("No msf_subscenes.json files found.")
        return

    print(f"Found {len(episode_jsons)} episode JSON files.\n")

    for msf_json_path in episode_jsons:
        print(f"Processing: {msf_json_path}")
        process_episode_json(
            msf_json_path=msf_json_path,
            output_root=out_dir,
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
