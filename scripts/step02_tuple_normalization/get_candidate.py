import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EPISODE_ROOT = Path("final_direct")
OUT_ROOT = Path("final_direct/tuples")

# 兼容 s01_e3 / s01_e03 两种
EP_DIR_RE = re.compile(r"^s01_e(\d{1,2})$")

# scene 文件：scene_008.json / scene008.json / scene_8.json 都尽量兼容
SCENE_RE = re.compile(r"^(scene_?\d+)\.json$", re.IGNORECASE)


def parse_episode_num(dirname: str) -> Optional[int]:
    m = EP_DIR_RE.match(dirname)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def canonical_ep_name(ep_num: int) -> str:
    # 输出目录用 candidates_ep03 这样的名字
    return f"candidates_ep{ep_num:02d}"


def find_scene_files(ep_dir: Path) -> List[Path]:
    files: List[Path] = []
    for p in ep_dir.iterdir():
        if p.is_file() and SCENE_RE.match(p.name):
            files.append(p)
    return sorted(files, key=lambda x: x.name)


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def to_parsed_tuples_text(tuples: List[Dict[str, Any]]) -> str:
    lines = []
    for t in tuples:
        verb = t.get("verb")
        subj = t.get("subject")
        obj = t.get("object")  # None stays None
        uid = t.get("uid")
        lines.append(repr((verb, subj, obj, uid)))
    lines.append("")  # trailing newline
    return "\n".join(lines)


def scene_out_filename(scene_json_name: str) -> Optional[str]:
    """
    scene_008.json -> parsed_scene_008.txt
    scene008.json  -> parsed_scene008.txt  （保留原格式，避免你后续对齐困难）
    """
    m = SCENE_RE.match(scene_json_name)
    if not m:
        return None
    scene_stem = m.group(1)  # e.g. scene_008 or scene008
    return f"parsed_{scene_stem}.txt"


def safe_write(path: Path, text: str, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main(overwrite: bool = False) -> None:
    if not EPISODE_ROOT.exists():
        raise FileNotFoundError(f"Missing input dir: {EPISODE_ROOT.resolve()}")

    total_scenes = 0
    wrote = 0
    skipped = 0
    errors = 0

    for ep_dir in sorted(EPISODE_ROOT.iterdir(), key=lambda x: x.name):
        if not ep_dir.is_dir():
            continue

        ep_num = parse_episode_num(ep_dir.name)
        if ep_num is None or not (11 <= ep_num <= 24):
            continue

        out_ep_dir = OUT_ROOT / canonical_ep_name(ep_num)

        scene_files = find_scene_files(ep_dir)
        if not scene_files:
            continue

        for scene_path in scene_files:
            total_scenes += 1
            out_name = scene_out_filename(scene_path.name)
            if not out_name:
                skipped += 1
                print(f"[SKIP] Unrecognized scene filename: {scene_path}")
                continue

            out_path = out_ep_dir / out_name

            try:
                data = load_json(scene_path)
                tuples = data.get("tuples")

                if not isinstance(tuples, list):
                    skipped += 1
                    print(f"[SKIP] {scene_path} (no 'tuples' list)")
                    continue

                text = to_parsed_tuples_text(tuples)
                safe_write(out_path, text, overwrite=overwrite)

                wrote += 1
                print(f"[OK] {scene_path} -> {out_path}")

            except FileExistsError as e:
                skipped += 1
                print(f"[SKIP] {e}")
            except Exception as e:
                errors += 1
                print(f"[ERR] {scene_path}: {e}")

    print("\nDone.")
    print(f"  scenes_seen: {total_scenes}")
    print(f"  wrote:       {wrote}")
    print(f"  skipped:     {skipped}")
    print(f"  errors:      {errors}")
    print(f"Output root: {OUT_ROOT.resolve()}")


if __name__ == "__main__":
    # 默认不覆盖（安全）
    main(overwrite=True)