import json
from pathlib import Path

# ===== paths =====
BATCH_OUTPUT_JSONL = "big5_utterance.jsonl"
OUTPUT_ROOT = "big_five_output_utterance_anon"

# 如果你想严格对齐输入根目录名字，也可以改成：
# OUTPUT_ROOT = "big_five_input_anon_json"


def extract_output_text(body: dict) -> str | None:
    """
    Safely extract output_text from responses API body
    without assuming fixed output index.
    """
    for block in body.get("output", []):
        if block.get("type") == "message":
            for content in block.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text")
    return None


def parse_custom_id(custom_id: str):
    """
    custom_id format:
    s01_e01__Rachel Green__subscene_002

    Returns:
    episode, character, subscene
    """
    parts = custom_id.split("__")
    if len(parts) != 3:
        raise ValueError(f"Invalid custom_id format: {custom_id}")
    return parts[0], parts[1], parts[2]


def main():
    input_path = Path(BATCH_OUTPUT_JSONL)
    output_root = Path(OUTPUT_ROOT)
    output_root.mkdir(parents=True, exist_ok=True)

    total = 0
    success = 0
    failed = 0

    with input_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            total += 1

            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[Line {line_no}] JSON decode error in jsonl line: {e}")
                failed += 1
                continue

            custom_id = item.get("custom_id")
            if not custom_id:
                print(f"[Line {line_no}] Missing custom_id")
                failed += 1
                continue

            try:
                episode, character, subscene = parse_custom_id(custom_id)
            except ValueError as e:
                print(f"[Line {line_no}] {e}")
                failed += 1
                continue

            out_dir = output_root / episode / character
            out_dir.mkdir(parents=True, exist_ok=True)

            out_file = out_dir / f"{subscene}.json"

            error_obj = item.get("error")
            response = item.get("response")

            # Case 1: top-level batch error
            if error_obj is not None:
                fail_payload = {
                    "custom_id": custom_id,
                    "status": "failed",
                    "error": error_obj,
                }
                with out_file.open("w", encoding="utf-8") as wf:
                    json.dump(fail_payload, wf, ensure_ascii=False, indent=2)
                failed += 1
                continue

            # Case 2: missing response
            if response is None:
                fail_payload = {
                    "custom_id": custom_id,
                    "status": "failed",
                    "error": "Missing response field"
                }
                with out_file.open("w", encoding="utf-8") as wf:
                    json.dump(fail_payload, wf, ensure_ascii=False, indent=2)
                failed += 1
                continue

            status_code = response.get("status_code")
            body = response.get("body", {})

            # Case 3: non-200 response
            if status_code != 200:
                fail_payload = {
                    "custom_id": custom_id,
                    "status": "failed",
                    "status_code": status_code,
                    "body_error": body.get("error"),
                    "body": body,
                }
                with out_file.open("w", encoding="utf-8") as wf:
                    json.dump(fail_payload, wf, ensure_ascii=False, indent=2)
                failed += 1
                continue

            # Case 4: response body contains error
            if body.get("error") is not None:
                fail_payload = {
                    "custom_id": custom_id,
                    "status": "failed",
                    "status_code": status_code,
                    "body_error": body.get("error"),
                }
                with out_file.open("w", encoding="utf-8") as wf:
                    json.dump(fail_payload, wf, ensure_ascii=False, indent=2)
                failed += 1
                continue

            output_text = extract_output_text(body)
            if output_text is None:
                fail_payload = {
                    "custom_id": custom_id,
                    "status": "failed",
                    "error": "No output_text found in response.body.output"
                }
                with out_file.open("w", encoding="utf-8") as wf:
                    json.dump(fail_payload, wf, ensure_ascii=False, indent=2)
                failed += 1
                continue

            try:
                parsed = json.loads(output_text)
            except json.JSONDecodeError as e:
                fail_payload = {
                    "custom_id": custom_id,
                    "status": "failed",
                    "error": f"output_text is not valid JSON: {e}",
                    "raw_output_text": output_text,
                }
                with out_file.open("w", encoding="utf-8") as wf:
                    json.dump(fail_payload, wf, ensure_ascii=False, indent=2)
                failed += 1
                continue

            with out_file.open("w", encoding="utf-8") as wf:
                json.dump(parsed, wf, ensure_ascii=False, indent=2)

            success += 1

    print(f"Done.")
    print(f"Total:   {total}")
    print(f"Success: {success}")
    print(f"Failed:  {failed}")
    print(f"Output:  {output_root.resolve()}")


if __name__ == "__main__":
    main()