from pathlib import Path
import argparse
from openai import OpenAI

parser = argparse.ArgumentParser(description="Download a completed Batch API output as JSONL.")
parser.add_argument("batch_id")
parser.add_argument("output_jsonl", type=Path)
args = parser.parse_args()
client = OpenAI()
batch = client.batches.retrieve(args.batch_id)
if batch.status != "completed" or not batch.output_file_id:
    raise RuntimeError(f"Batch is {batch.status}; output_file_id={batch.output_file_id}")
content = client.files.content(batch.output_file_id)
args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
args.output_jsonl.write_bytes(content.read())
print(f"Saved {batch.output_file_id} to {args.output_jsonl}")
