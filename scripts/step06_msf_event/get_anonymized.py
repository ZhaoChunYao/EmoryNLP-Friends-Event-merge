import json
import argparse
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional


INPUT_ROOT = Path("big_five_input")
OUTPUT_ROOT = Path("big_five_input_anon")
SEASON_JSON_DIR = Path(".")

SUBSCENE_FILE_PATTERN = re.compile(r"^subscene_\d+\.txt$", re.IGNORECASE)
EPISODE_IN_NAME_PATTERN = re.compile(r"s(?P<season>\d{2})_e(?P<episode>\d{2})", re.IGNORECASE)
UID_PATTERN = re.compile(r"\[(s\d{2}_e\d{2}_c\d{2}_u\d+)\]")
MAIN_SPEAKER_PATTERN = re.compile(r"^Main speaker:\s*(.*)$", re.IGNORECASE)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_season_arg(season: str) -> str:
    season = season.strip().lower()
    if season == "all":
        return "all"
    if season.isdigit():
        return f"{int(season):02d}"
    raise ValueError("season must be 'all' or an integer like 1 / 10")


def season_json_path(season_2digit: str, season_json_dir: Path) -> Path:
    return season_json_dir / f"friends_season_{season_2digit}.json"


def extract_episode_id_from_path(path: Path, input_root: Path) -> Optional[str]:
    """
    Expect path like:
      big_five_input/s01_e01/Chandler Bing/subscene_001.txt
    Return:
      s01_e01
    """
    try:
        rel = path.relative_to(input_root)
    except ValueError:
        return None

    parts = rel.parts
    if len(parts) < 3:
        return None

    episode_dir = parts[0]
    if EPISODE_IN_NAME_PATTERN.search(episode_dir):
        return episode_dir

    return None


def extract_season_from_episode_id(episode_id: str) -> Optional[str]:
    m = EPISODE_IN_NAME_PATTERN.search(episode_id)
    if not m:
        return None
    return m.group("season")


def build_utterance_index(season_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Build:
      utterance_id -> utterance_object
    from season json.
    """
    index: Dict[str, Dict[str, Any]] = {}

    for ep in season_data.get("episodes", []):
        for scene in ep.get("scenes", []):
            for utt in scene.get("utterances", []):
                uid = utt.get("utterance_id")
                if isinstance(uid, str) and uid.strip():
                    index[uid.strip()] = utt

    return index


def flatten_character_entities(character_entities: Any) -> Set[str]:
    """
    character_entities is a list of lists.
    Inner item examples:
      [start, end, "Chandler Bing"]
      [start, end, "Jack Geller", "Judy Geller"]
    """
    names: Set[str] = set()

    if not isinstance(character_entities, list):
        return names

    for outer in character_entities:
        if not isinstance(outer, list):
            continue
        for item in outer:
            if not isinstance(item, list):
                continue
            if len(item) < 3:
                continue
            for x in item[2:]:
                if isinstance(x, str):
                    x = x.strip()
                    if x:
                        names.add(x)

    return names


def normalize_speakers_field(speakers: Any) -> Set[str]:
    names: Set[str] = set()

    if isinstance(speakers, str):
        s = speakers.strip()
        if s:
            names.add(s)
        return names

    if isinstance(speakers, list):
        for s in speakers:
            if isinstance(s, str):
                s = s.strip()
                if s:
                    names.add(s)
        return names

    return names


def extract_uids_from_text(text: str) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for uid in UID_PATTERN.findall(text):
        if uid not in seen:
            seen.add(uid)
            ordered.append(uid)
    return ordered


def parse_main_speaker(text: str) -> Optional[str]:
    for line in text.splitlines():
        m = MAIN_SPEAKER_PATTERN.match(line.strip())
        if m:
            name = m.group(1).strip()
            return name if name else None
    return None


def collect_names_for_subscene(
    uids: List[str],
    utterance_index: Dict[str, Dict[str, Any]],
) -> Set[str]:
    """
    Collect names from:
      - character_entities
      - speakers
    """
    names: Set[str] = set()

    for uid in uids:
        utt = utterance_index.get(uid)
        if not utt:
            continue

        names.update(flatten_character_entities(utt.get("character_entities", [])))
        names.update(normalize_speakers_field(utt.get("speakers", [])))

    return names


def build_name_mapping(
    text: str,
    main_speaker: Optional[str],
    all_names: Set[str],
) -> Dict[str, str]:
    """
    Main speaker -> TargetSpeaker
    Others -> Speaker_01, Speaker_02, ...
    Only map names that actually appear in text.
    """
    names_in_text = [name for name in all_names if name and name in text]

    mapping: Dict[str, str] = {}

    if main_speaker and main_speaker in names_in_text:
        mapping[main_speaker] = "TargetSpeaker"

    others = [n for n in names_in_text if n != main_speaker]
    others = sorted(others, key=lambda n: (text.find(n), -len(n), n))

    counter = 1
    for name in others:
        if name in mapping:
            continue
        mapping[name] = f"Speaker_{counter:02d}"
        counter += 1

    return mapping


def apply_string_replacements(text: str, mapping: Dict[str, str]) -> str:
    """
    Replace longer names first.
    """
    out = text
    for src, dst in sorted(mapping.items(), key=lambda kv: (-len(kv[0]), kv[0])):
        out = out.replace(src, dst)
    return out


def find_all_subscene_files(input_root: Path, season_filter: str) -> List[Path]:
    files: List[Path] = []

    if not input_root.exists():
        return files

    for path in sorted(input_root.rglob("subscene_*.txt")):
        if not path.is_file():
            continue

        episode_id = extract_episode_id_from_path(path, input_root)
        if not episode_id:
            continue

        season = extract_season_from_episode_id(episode_id)
        if not season:
            continue

        if season_filter != "all" and season != season_filter:
            continue

        files.append(path)

    return files


def group_files_by_season(
    files: List[Path],
    input_root: Path,
) -> Dict[str, List[Path]]:
    grouped: Dict[str, List[Path]] = {}

    for path in files:
        episode_id = extract_episode_id_from_path(path, input_root)
        if not episode_id:
            continue

        season = extract_season_from_episode_id(episode_id)
        if not season:
            continue

        grouped.setdefault(season, []).append(path)

    return grouped


def anonymize_one_file(
    in_path: Path,
    out_path: Path,
    utterance_index: Dict[str, Dict[str, Any]],
) -> Tuple[int, int]:
    text = in_path.read_text(encoding="utf-8")

    uids = extract_uids_from_text(text)
    main_speaker = parse_main_speaker(text)
    all_names = collect_names_for_subscene(uids, utterance_index)
    mapping = build_name_mapping(text, main_speaker, all_names)
    anon_text = apply_string_replacements(text, mapping)

    ensure_dir(out_path.parent)
    out_path.write_text(anon_text, encoding="utf-8")

    return len(uids), len(mapping)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_root", default=str(INPUT_ROOT))
    parser.add_argument("--out_dir", default=str(OUTPUT_ROOT))
    parser.add_argument("--season_json_dir", default=str(SEASON_JSON_DIR))
    parser.add_argument(
        "--season",
        default="1",
        help="Season to process: 'all', '1', '10', etc.",
    )
    args = parser.parse_args()

    input_root = Path(args.input_root)
    out_dir = Path(args.out_dir)
    season_json_dir = Path(args.season_json_dir)
    season_filter = normalize_season_arg(args.season)

    ensure_dir(out_dir)

    all_files = find_all_subscene_files(input_root, season_filter)
    if not all_files:
        print("No matching subscene files found.")
        return

    grouped = group_files_by_season(all_files, input_root)

    season_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for season_2digit in sorted(grouped.keys()):
        json_path = season_json_path(season_2digit, season_json_dir)
        if not json_path.exists():
            print(f"[WARN] Season JSON not found: {json_path}")
            continue

        print(f"[INFO] Loading season json: {json_path}")
        season_data = load_json(json_path)
        utterance_index = build_utterance_index(season_data)
        season_cache[season_2digit] = utterance_index

        for in_path in grouped[season_2digit]:
            rel = in_path.relative_to(input_root)
            out_path = out_dir / rel
            uid_count, mapped_count = anonymize_one_file(
                in_path=in_path,
                out_path=out_path,
                utterance_index=utterance_index,
            )
            print(f"[OK] {out_path} | uids={uid_count} mapped_names={mapped_count}")

    print("\nDone.")


if __name__ == "__main__":
    main()