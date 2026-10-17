import os
import json

INPUT_ROOT = "big_five_input_utterance_anon"
OUTPUT_FILE = "big_five_batch_input.jsonl"

MODEL = "gpt-5"

PROMPT = """Task
Multiparty Personality Recognition requires determining the main
speaker's personality from a short conversation using binary Big Five traits.

Judge the personality tendency expressed in this dialogue,
not the speaker's overall long-term personality.

Agreeableness (AGR): trustworthy, straightforward, generous vs. unreliable, complicated, meager, and boastful
Conscientiousness (CON): efficient and organized vs. sloppy and careless
Extroversion (EXT): outgoing, talkative, and energetic vs. reserved and solitary
Openness (OPN): inventive and curious vs. dogmatic and cautious
Neuroticism (NEU): sensitive and nervous vs. secure and confident

The dialogue is represented as utterances from the conversation.

Base judgments on concrete events. When behavior strongly indicates a
trait, prioritize the behavior over reflections or explanations.

Trait orientation
1  = evidence for the first side of the definition
-1 = evidence for the opposite side
0  = neither side is supported

Use -1 rather than 0 when opposite side evidence exists.

Output the result as JSON with fields EXT, AGR, CON, NEU, OPN.
Each field must contain:
- score (integer: -1, 0, or 1)
- evidence (string)

INPUT:

{var}
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "EXT": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "evidence": {"type": "string"}
            },
            "required": ["score", "evidence"],
            "additionalProperties": False
        },
        "AGR": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "evidence": {"type": "string"}
            },
            "required": ["score", "evidence"],
            "additionalProperties": False
        },
        "CON": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "evidence": {"type": "string"}
            },
            "required": ["score", "evidence"],
            "additionalProperties": False
        },
        "NEU": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "evidence": {"type": "string"}
            },
            "required": ["score", "evidence"],
            "additionalProperties": False
        },
        "OPN": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "evidence": {"type": "string"}
            },
            "required": ["score", "evidence"],
            "additionalProperties": False
        }
    },
    "required": ["EXT", "AGR", "CON", "NEU", "OPN"],
    "additionalProperties": False
}


def generate_batch():
    total = 0
    allowed_episodes = {"s01_e01", "s01_e02"}

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for episode in sorted(os.listdir(INPUT_ROOT)):
            if episode not in allowed_episodes:
                continue

            episode_path = os.path.join(INPUT_ROOT, episode)

            if not os.path.isdir(episode_path):
                continue

            for character in sorted(os.listdir(episode_path)):
                char_path = os.path.join(episode_path, character)

                if not os.path.isdir(char_path):
                    continue

                for fname in sorted(os.listdir(char_path)):
                    if not fname.endswith(".txt"):
                        continue

                    fpath = os.path.join(char_path, fname)

                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read().strip()

                    prompt = PROMPT.replace("{var}", content)
                    custom_id = f"{episode}__{character}__{fname.replace('.txt','')}"

                    request = {
                        "custom_id": custom_id,
                        "method": "POST",
                        "url": "/v1/responses",
                        "body": {
                            "model": MODEL,
                            "input": prompt,
                            "text": {
                                "format": {
                                    "type": "json_schema",
                                    "name": "big_five_result",
                                    "strict": True,
                                    "schema": SCHEMA
                                }
                            }
                        }
                    }

                    out.write(json.dumps(request, ensure_ascii=False) + "\n")
                    total += 1

    print(f"Batch file written to {OUTPUT_FILE}")
    print(f"Total requests: {total}")


if __name__ == "__main__":
    generate_batch()
