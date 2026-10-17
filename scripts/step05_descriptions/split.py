import json
from pathlib import Path

INPUT_FILE = "ep11_ep24_desc(Season_1).jsonl"
OUTPUT_ROOT = Path("merge/description")

def extract_episode_scene(custom_id: str):
    ep_part, scene_part = custom_id.split("__")
    return ep_part, scene_part

def extract_json_text(body):
    """
    在 output 数组中找到 type=message 的那一项，
    再从 content 里拿 output_text
    """
    for block in body["output"]:
        if block["type"] == "message":
            for content in block["content"]:
                if content["type"] == "output_text":
                    return content["text"]
    return None

def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)

            if item["response"]["status_code"] != 200:
                continue

            custom_id = item["custom_id"]
            episode_id, scene_id = extract_episode_scene(custom_id)

            body = item["response"]["body"]

            output_text = extract_json_text(body)
            if not output_text:
                print(f"⚠ No output_text for {custom_id}")
                continue

            try:
                data = json.loads(output_text)
            except json.JSONDecodeError:
                print(f"❌ JSON parse error in {custom_id}")
                continue

            ep_dir = OUTPUT_ROOT / episode_id
            ep_dir.mkdir(parents=True, exist_ok=True)

            out_path = ep_dir / f"{scene_id}.json"

            with open(out_path, "w", encoding="utf-8") as out_f:
                json.dump(data, out_f, indent=2, ensure_ascii=False)

            print(f"✓ Wrote {out_path}")

if __name__ == "__main__":
    main()