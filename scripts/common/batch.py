from pathlib import Path
import argparse
from openai import OpenAI

parser = argparse.ArgumentParser(description="Upload a JSONL and create a Batch API job.")
parser.add_argument("input_jsonl", type=Path)
parser.add_argument("--endpoint", default="/v1/responses")
parser.add_argument("--completion-window", default="24h")
args = parser.parse_args()
if not args.input_jsonl.is_file():
    raise FileNotFoundError(args.input_jsonl)
client = OpenAI()
upload = client.files.create(file=args.input_jsonl.open("rb"), purpose="batch")
batch = client.batches.create(input_file_id=upload.id, endpoint=args.endpoint, completion_window=args.completion_window)
print(f"Batch ID: {batch.id}")
print(f"Input file ID: {upload.id}")
print(f"Status: {batch.status}")
