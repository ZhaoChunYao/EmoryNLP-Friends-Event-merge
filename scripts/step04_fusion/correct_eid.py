#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path

IN_ROOT = Path(r"merge/result")
OUT_ROOT = Path(r"merge/result_id")

def normalize_file(in_path: Path, out_path: Path) -> None:
    with in_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    utterances = data.get("utterances")
    if not isinstance(utterances, list):
        raise ValueError(f"{in_path}: missing/invalid 'utterances' list")

    for u in utterances:
        uid = u.get("utterance_id")
        events = u.get("events")
        if not isinstance(uid, str) or not uid:
            raise ValueError(f"{in_path}: invalid utterance_id: {uid}")
        if not isinstance(events, list):
            raise ValueError(f"{in_path}: invalid events list for {uid}")

        for i, ev in enumerate(events, start=1):
            # 强制覆盖/规范化 event_id
            ev["event_id"] = f"{uid}_e{i}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    if not IN_ROOT.exists():
        raise FileNotFoundError(f"Input root not found: {IN_ROOT.resolve()}")

    wrote = 0
    skipped = 0

    # episode_* 下所有 json
    for ep_dir in sorted(IN_ROOT.glob("episode_*")):
        if not ep_dir.is_dir():
            continue

        out_ep_dir = OUT_ROOT / ep_dir.name

        json_files = sorted(ep_dir.glob("*.json"))
        if not json_files:
            continue

        for in_path in json_files:
            # 只处理形如 s01_e01_cxx.json 也行；你要全处理就别加过滤
            # if not in_path.name.lower().startswith("s01_e01_c"):
            #     continue

            out_path = out_ep_dir / in_path.name
            try:
                normalize_file(in_path, out_path)
                wrote += 1
                print(f"[OK] {in_path} -> {out_path}")
            except Exception as e:
                skipped += 1
                print(f"[SKIP] {in_path}: {e}")

    print("\nDone.")
    print(f"  wrote:   {wrote}")
    print(f"  skipped: {skipped}")
    print(f"Output root:", OUT_ROOT.resolve())

if __name__ == "__main__":
    main()