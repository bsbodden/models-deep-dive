#!/usr/bin/env python3
"""Pin CoQA dev and QuAC val, then cut the frozen 100-item samples this experiment scores.

Nothing here is authored by us. Both files are downloaded from the authors' own hosts, hashed, and
recorded in MANIFEST.json before any item is read.

Three sampling decisions, all made here and all visible in the committed sample:

* **One turn per dialogue.** Turns inside a dialogue share a passage and a history, so a hundred
  turns from ten dialogues is ten observations wearing a hundred hats. One turn is drawn per
  dialogue, from a hundred distinct dialogues, with this project's seed.
* **Uniform over turns.** The drawn turn is uniform within the dialogue -- the sample is not
  balanced for answerable against unanswerable, because engineering that mix would be choosing the
  difficulty. The resulting counts are printed and recorded.
* **Gold history.** The preceding turns are shown with the dataset's own answers, which is the
  published convention for both datasets: it measures this turn rather than compounding an earlier
  arm's error into every later one.

QuAC appends the literal token `CANNOTANSWER` to every passage, an artifact of its span-based setup
that tells a generative model where to look. It is stripped from the passage here, for every arm
equally, and the turn's gold is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import random
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "data"
SAMPLE_SIZE = 100
SEED = 20261019  # the seed every sample in this article's experiments is cut with

SOURCES = {
    "coqa": "https://downloads.cs.stanford.edu/nlp/data/coqa/coqa-dev-v1.0.json",
    "quac": "https://s3.amazonaws.com/my89public/quac/val_v0.2.json",
}
COQA_UNKNOWN = "unknown"
QUAC_UNANSWERABLE = "CANNOTANSWER"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "local-only-chat/1"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def coqa_items(payload: bytes, rng: random.Random) -> list[dict]:
    data = json.loads(payload.decode("utf-8"))["data"]
    items = []
    for dialogue in data:
        turns = dialogue["questions"]
        answers = {answer["turn_id"]: answer for answer in dialogue["answers"]}
        extra = dialogue.get("additional_answers", {})
        pick = rng.randrange(len(turns))
        turn = turns[pick]
        gold = [answers[turn["turn_id"]]["input_text"].strip()]
        for annotator in sorted(extra):
            for answer in extra[annotator]:
                if answer["turn_id"] == turn["turn_id"]:
                    gold.append(answer["input_text"].strip())
        history = []
        for earlier in turns[:pick]:
            history.append({"question": earlier["input_text"].strip(),
                            "answer": answers[earlier["turn_id"]]["input_text"].strip()})
        items.append({
            "id": f"{dialogue['id']}#{turn['turn_id']}",
            "paragraphs": [dialogue["story"].strip()],
            "history": history,
            "question": turn["input_text"].strip(),
            "answers": [g for g in dict.fromkeys(gold) if g],
            # CoQA's convention for a question the passage does not answer is the answer "unknown".
            "unanswerable": gold[0].lower() == COQA_UNKNOWN,
        })
    return items


def quac_items(payload: bytes, rng: random.Random) -> list[dict]:
    data = json.loads(payload.decode("utf-8"))["data"]
    items = []
    for entry in data:
        for paragraph in entry["paragraphs"]:
            passage = paragraph["context"]
            if passage.rstrip().endswith(QUAC_UNANSWERABLE):
                passage = passage.rstrip()[: -len(QUAC_UNANSWERABLE)].rstrip()
            turns = paragraph["qas"]
            pick = rng.randrange(len(turns))
            turn = turns[pick]
            gold = [turn["orig_answer"]["text"].strip()]
            gold += [answer["text"].strip() for answer in turn["answers"]]
            unanswerable = gold[0] == QUAC_UNANSWERABLE
            gold = [g for g in dict.fromkeys(gold) if g and g != QUAC_UNANSWERABLE]
            history = []
            for earlier in turns[:pick]:
                answer = earlier["orig_answer"]["text"].strip()
                history.append({
                    "question": earlier["question"].strip(),
                    "answer": "I don't know." if answer == QUAC_UNANSWERABLE else answer,
                })
            items.append({
                "id": turn["id"],
                "paragraphs": [passage],
                "history": history,
                "question": turn["question"].strip(),
                "answers": gold,
                "unanswerable": unanswerable,
            })
    return items


def main() -> int:
    RAW.mkdir(exist_ok=True)
    manifest = {"seed": SEED, "sampleSize": SAMPLE_SIZE, "sources": {}, "samples": {}}
    rng = random.Random(SEED)

    payloads = {}
    for name, url in SOURCES.items():
        cached = RAW / f"{name}.raw"
        body = cached.read_bytes() if cached.exists() else fetch(url)
        cached.write_bytes(body)
        payloads[name] = body
        manifest["sources"][name] = {
            "url": url, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        print(f"{name}: {len(body):,} bytes  sha256 {manifest['sources'][name]['sha256'][:16]}")

    for name, build in (("coqa", coqa_items), ("quac", quac_items)):
        items = build(payloads[name], rng)
        rng.shuffle(items)
        sample = items[:SAMPLE_SIZE]
        unanswerable = sum(1 for item in sample if item["unanswerable"])
        path = HERE / f"sample-{name}.json"
        path.write_text(json.dumps(sample, indent=1) + "\n")
        manifest["samples"][name] = {
            "file": path.name,
            "items": len(sample),
            "drawnFrom": len(items),
            "unanswerable": unanswerable,
            "medianHistoryTurns": sorted(len(i["history"]) for i in sample)[len(sample) // 2],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        print(f"{name}: {len(sample)} items from {len(items)} dialogues, "
              f"{unanswerable} unanswerable, median {manifest['samples'][name]['medianHistoryTurns']}"
              f" history turns")

    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {HERE / 'MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
