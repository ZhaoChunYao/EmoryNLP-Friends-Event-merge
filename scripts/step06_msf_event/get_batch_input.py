import json
import argparse
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional


MSF_OUTPUT_DIR = Path("msf_output")
DESCRIPTION_ROOT = Path("description")
BIG_FIVE_OUTPUT_DIR = Path("big_five_input")

EPISODE_DIR_PATTERN = re.compile(r"^friends_s\d{2}_e\d{2}$", re.IGNORECASE)
SCENE_ID_PATTERN = re.compile(r"^(s\d{2}_e\d{2}_c\d{2})$", re.IGNORECASE)
EVENT_ID_PATTERN = re.compile(r"^(?P<uid>s\d{2}_e\d{2}_c\d{2}_u\d+)_e(?P<idx>\d+)$", re.IGNORECASE)
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


def build_uid_to_events_from_desc_json(scene_desc_json: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Parse description json schema:

    {
      "events": [
        {
          "event_id": "s01_e01_c01_u002_e1",
          "description": "Joey Tribbiani says Monica Geller ..."
        },
        ...
      ]
    }

    Convert to:
      {
        "s01_e01_c01_u002": [
          "Joey Tribbiani says Monica Geller ...",
          ...
        ]
      }
    """
    uid_to_events_tmp: Dict[str, List[tuple[int, str]]] = defaultdict(list)

    events = scene_desc_json.get("events", [])
    if not isinstance(events, list):
        return {}

    for item in events:
        if not isinstance(item, dict):
            continue

        event_id = str(item.get("event_id", "")).strip()
        description = str(item.get("description", "")).strip()

        if not event_id or not description:
            continue

        m = EVENT_ID_PATTERN.match(event_id)
        if not m:
            continue

        uid = m.group("uid")
        idx = int(m.group("idx"))
        uid_to_events_tmp[uid].append((idx, description))

    uid_to_events: Dict[str, List[str]] = {}
    for uid, pairs in uid_to_events_tmp.items():
        pairs.sort(key=lambda x: x[0])
        uid_to_events[uid] = [desc for _, desc in pairs]

    return uid_to_events


def find_desc_json_for_scene(scene_id: str, description_root: Path) -> Optional[Path]:
    """
    Search recursively under description_root for scene_id.json
    Example:
      scene_id = s01_e01_c01
      search for **/s01_e01_c01.json
    """
    if not SCENE_ID_PATTERN.match(scene_id):
        return None

    matches = sorted(description_root.rglob(f"{scene_id}.json"))
    if not matches:
        return None

    return matches[0]


def format_subscene_text(
    episode_id: str,
    speaker_subscene_index: int,
    subscene: Dict[str, Any],
    uid_to_events: Dict[str, List[str]],
) -> str:
    scene_id = subscene.get("scene_id", "")
    main_speaker = subscene.get("main_speaker", "")
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

    for utt in utterances:
        uid = str(utt.get("uid", "")).strip()
        speaker = str(utt.get("speaker", "")).strip()
        text = str(utt.get("text", ""))

        if not uid:
            continue

        descs = uid_to_events.get(uid, [])

        if descs:
            lines.append(f"  [{uid}]")
            for i, desc in enumerate(descs, 1):
                lines.append(f"  {i}. {desc}")
        else:
            # fallback to original utterance for ALL no-desc cases
            lines.append(f"  [{uid}] {speaker}: {text}")

    lines.append("")
    return "\n".join(lines)


def process_episode_json(msf_json_path: Path, description_root: Path, output_root: Path) -> None:
    data = load_json(msf_json_path)

    episode_id = data.get("episode_id") or msf_json_path.parent.name
    all_subscenes = data.get("all_subscenes", [])

    if not isinstance(all_subscenes, list):
        print(f"[WARN] Invalid all_subscenes in {msf_json_path}")
        return

    speaker_counters: Dict[str, int] = defaultdict(int)
    scene_desc_cache: Dict[str, Dict[str, List[str]]] = {}

    for subscene in all_subscenes:
        scene_id = str(subscene.get("scene_id", "")).strip()
        main_speaker = str(subscene.get("main_speaker", "")).strip()

        if not scene_id or not main_speaker:
            print(f"[WARN] Skip malformed subscene in {msf_json_path}")
            continue

        if scene_id not in scene_desc_cache:
            desc_path = find_desc_json_for_scene(scene_id, description_root)
            if desc_path is None:
                print(f"[WARN] Description JSON not found for scene: {scene_id}")
                scene_desc_cache[scene_id] = {}
            else:
                desc_json = load_json(desc_path)
                scene_desc_cache[scene_id] = build_uid_to_events_from_desc_json(desc_json)

        uid_to_events = scene_desc_cache[scene_id]

        speaker_counters[main_speaker] += 1
        subscene_idx = speaker_counters[main_speaker]

        text = format_subscene_text(
            episode_id=episode_id,
            speaker_subscene_index=subscene_idx,
            subscene=subscene,
            uid_to_events=uid_to_events,
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
    parser.add_argument("--description_root", default=str(DESCRIPTION_ROOT))
    parser.add_argument("--out_dir", default=str(BIG_FIVE_OUTPUT_DIR))
    parser.add_argument(
        "--season",
        default="1",
        help="Season to process: 'all', '1', '10', etc.",
    )
    args = parser.parse_args()

    msf_output_dir = Path(args.msf_output_dir)
    description_root = Path(args.description_root)
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
            description_root=description_root,
            output_root=out_dir,
        )

    print("\nDone.")


if __name__ == "__main__":
    main()