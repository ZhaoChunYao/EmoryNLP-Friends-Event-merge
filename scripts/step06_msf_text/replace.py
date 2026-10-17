import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from docx import Document


INPUT_ROOT = Path("big_five_input_utterance")
REPLACED_EPISODE_DIR = Path("replaced_episode")
OUTPUT_ROOT = Path("big_five_input_utterance_replaced")

SUBSCENE_UID_LINE_PATTERN = re.compile(
    r"^(?P<indent>\s*)\[(?P<uid>s\d{2}_e\d{2}_c\d{2}_u\d+)\]\s*(?P<speaker>[^:]*):\s*(?P<text>.*)$",
    re.IGNORECASE,
)

DOCX_UID_LINE_PATTERN = re.compile(
    r"^\[(?P<uid>s\d{2}_e\d{2}_c\d{2}_u\d+)\]\s*(?P<speaker>[^:]*):\s*(?P<text>.*)$",
    re.IGNORECASE,
)

EPISODE_LINE_PATTERN = re.compile(
    r"^Episode:\s*(?P<ep>s\d{2}_e\d{2})\s*$",
    re.IGNORECASE,
)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def extract_episode_id_from_subscene_text(text: str) -> Optional[str]:
    for line in text.splitlines():
        m = EPISODE_LINE_PATTERN.match(line.strip())
        if m:
            return m.group("ep").lower()
    return None


def parse_docx_episode(docx_path: Path) -> Dict[str, str]:
    """
    从 replaced_episode/*.docx 中直接读取:
      [s01_e01_c01_u050] Speaker: text

    返回:
      uid -> text

    只按 UID 取值，不做任何顺序或 scene 假设。
    """
    doc = Document(str(docx_path))
    uid_to_text: Dict[str, str] = {}

    for para in doc.paragraphs:
        line = para.text.strip()
        if not line:
            continue

        m = DOCX_UID_LINE_PATTERN.match(line)
        if not m:
            continue

        uid = m.group("uid").lower()
        text = m.group("text")
        uid_to_text[uid] = text

    return uid_to_text


def patch_subscene_text(
    subscene_text: str,
    uid_to_replaced_text: Dict[str, str],
) -> Tuple[str, int, int, int]:
    """
    返回:
      patched_text, total_uid_lines, replaced_count, missing_uid_count
    """
    out_lines: List[str] = []
    total_uid_lines = 0
    replaced_count = 0
    missing_uid_count = 0

    lines = subscene_text.splitlines()

    for line in lines:
        m = SUBSCENE_UID_LINE_PATTERN.match(line)
        if not m:
            out_lines.append(line)
            continue

        total_uid_lines += 1

        indent = m.group("indent")
        uid = m.group("uid").lower()
        speaker = m.group("speaker").strip()
        old_text = m.group("text")

        new_text = uid_to_replaced_text.get(uid)
        if new_text is None:
            missing_uid_count += 1
            out_lines.append(line)
            continue

        out_lines.append(f"{indent}[{uid}] {speaker}: {new_text}")

        if new_text != old_text:
            replaced_count += 1

    patched_text = "\n".join(out_lines)
    if subscene_text.endswith("\n"):
        patched_text += "\n"

    return patched_text, total_uid_lines, replaced_count, missing_uid_count


def patch_one_file(
    in_path: Path,
    out_path: Path,
    episode_cache: Dict[str, Dict[str, str]],
    replaced_episode_dir: Path,
) -> Tuple[int, int, int]:
    text = in_path.read_text(encoding="utf-8")
    episode_id = extract_episode_id_from_subscene_text(text)

    if not episode_id:
        ensure_dir(out_path.parent)
        out_path.write_text(text, encoding="utf-8")
        print(f"[WARN] No episode id in {in_path}, copied unchanged.")
        return 0, 0, 0

    if episode_id not in episode_cache:
        docx_path = replaced_episode_dir / f"friends_{episode_id}.docx"
        if not docx_path.exists():
            print(f"[WARN] Missing docx: {docx_path}")
            episode_cache[episode_id] = {}
        else:
            print(f"[INFO] Loading {docx_path}")
            episode_cache[episode_id] = parse_docx_episode(docx_path)
            print(f"[INFO] Loaded {len(episode_cache[episode_id])} uid-text pairs from {docx_path.name}")

    patched_text, total_uid_lines, replaced_count, missing_uid_count = patch_subscene_text(
        text,
        episode_cache[episode_id],
    )

    ensure_dir(out_path.parent)
    out_path.write_text(patched_text, encoding="utf-8")
    return total_uid_lines, replaced_count, missing_uid_count


def find_subscene_files(input_root: Path) -> List[Path]:
    return sorted(p for p in input_root.rglob("subscene_*.txt") if p.is_file())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_root", default=str(INPUT_ROOT))
    parser.add_argument("--replaced_episode_dir", default=str(REPLACED_EPISODE_DIR))
    parser.add_argument("--out_dir", default=str(OUTPUT_ROOT))
    args = parser.parse_args()

    input_root = Path(args.input_root)
    replaced_episode_dir = Path(args.replaced_episode_dir)
    out_dir = Path(args.out_dir)

    files = find_subscene_files(input_root)
    if not files:
        print("No subscene files found.")
        return

    episode_cache: Dict[str, Dict[str, str]] = {}

    grand_total_uid_lines = 0
    grand_replaced_count = 0
    grand_missing_uid_count = 0

    for in_path in files:
        rel = in_path.relative_to(input_root)
        out_path = out_dir / rel

        total_uid_lines, replaced_count, missing_uid_count = patch_one_file(
            in_path=in_path,
            out_path=out_path,
            episode_cache=episode_cache,
            replaced_episode_dir=replaced_episode_dir,
        )

        grand_total_uid_lines += total_uid_lines
        grand_replaced_count += replaced_count
        grand_missing_uid_count += missing_uid_count

        print(
            f"[OK] {out_path} | uid_lines={total_uid_lines} "
            f"replaced={replaced_count} missing_uid={missing_uid_count}"
        )

    print()
    print(
        f"Done. uid_lines={grand_total_uid_lines}, "
        f"replaced={grand_replaced_count}, "
        f"missing_uid={grand_missing_uid_count}"
    )


if __name__ == "__main__":
    main()
