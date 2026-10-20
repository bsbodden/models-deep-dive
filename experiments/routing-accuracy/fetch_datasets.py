#!/usr/bin/env python3
"""Fetch the four public datasets, pin them by SHA-256, and cut the frozen samples.

Nothing here is written by us. Each source is downloaded, hashed, and recorded in MANIFEST.json
before any item is read, so a later run can prove it scored the same items. The sample is cut with
a fixed seed and committed, because a sample drawn again per run is a different experiment each
time.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "data"
SAMPLE_SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 100
SEED = 20261019

SOURCES = {
    "squad2": "https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v2.0.json",
    "trec": "https://cogcomp.seas.upenn.edu/Data/QA/QC/TREC_10.label",
}
# The rows API returns JSON, so reading HotpotQA costs no parquet dependency. The original
# curtis.ml.cmu.edu download for this split no longer resolves.
HOTPOT_ROWS = ("https://datasets-server.huggingface.co/rows?dataset=hotpotqa%2Fhotpot_qa"
               "&config=distractor&split=validation&offset={offset}&length={length}")
SNIPS_INTENTS = ["AddToPlaylist", "BookRestaurant", "GetWeather", "PlayMusic",
                 "RateBook", "SearchCreativeWork", "SearchScreeningEvent"]
SNIPS_URL = ("https://raw.githubusercontent.com/sonos/nlu-benchmark/master/"
             "2017-06-custom-intent-engines/{intent}/validate_{intent}.json")


def fetch(url: str, token: str | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "routing-accuracy/1"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def main() -> int:
    import os
    RAW.mkdir(exist_ok=True)
    manifest = {"seed": SEED, "sampleSize": SAMPLE_SIZE, "sources": {}}

    payloads = {}
    for name, url in SOURCES.items():
        token = os.environ.get("HF_TOKEN") if "huggingface" in url else None
        body = fetch(url, token)
        (RAW / f"{name}.raw").write_bytes(body)
        payloads[name] = body
        manifest["sources"][name] = {
            "url": url, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        print(f"{name}: {len(body):,} bytes")

    snips = {}
    for intent in SNIPS_INTENTS:
        body = fetch(SNIPS_URL.format(intent=intent))
        snips[intent] = body
        manifest["sources"][f"snips/{intent}"] = {
            "url": SNIPS_URL.format(intent=intent), "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest()}
    print(f"snips: {len(snips)} intent files")

    # ---- grounded QA ---------------------------------------------------------------------
    rng = random.Random(SEED)

    squad = json.loads(payloads["squad2"].decode("utf-8"))
    squad_items = []
    for article in squad["data"]:
        for paragraph in article["paragraphs"]:
            for qa in paragraph["qas"]:
                squad_items.append({
                    "id": qa["id"],
                    "question": qa["question"],
                    "paragraphs": [paragraph["context"]],
                    # An unanswerable item's gold answer is abstention. Scoring one of these as a
                    # miss for saying nothing would reward a model that always guesses.
                    "answers": sorted({a["text"] for a in qa["answers"]}),
                    "unanswerable": bool(qa.get("is_impossible")),
                })
    rng.shuffle(squad_items)
    # Half unanswerable, half answerable: the published dev split is roughly balanced and the
    # abstention half is the half a grounding policy is supposed to get right.
    answerable = [i for i in squad_items if not i["unanswerable"]][: SAMPLE_SIZE // 2]
    impossible = [i for i in squad_items if i["unanswerable"]][: SAMPLE_SIZE - SAMPLE_SIZE // 2]
    squad_sample = answerable + impossible
    rng.shuffle(squad_sample)

    hotpot_rows = []
    hotpot_pages = []
    while len(hotpot_rows) < SAMPLE_SIZE * 3:
        url = HOTPOT_ROWS.format(offset=len(hotpot_rows), length=100)
        body = fetch(url, os.environ.get("HF_TOKEN"))
        hotpot_pages.append(hashlib.sha256(body).hexdigest())
        page = json.loads(body.decode("utf-8"))["rows"]
        if not page:
            break
        hotpot_rows += [row["row"] for row in page]
    manifest["sources"]["hotpotqa"] = {
        "url": HOTPOT_ROWS.format(offset=0, length=100),
        "pages": len(hotpot_pages), "rows": len(hotpot_rows), "pageSha256": hotpot_pages}
    print(f"hotpotqa: {len(hotpot_rows)} rows over {len(hotpot_pages)} pages")
    hotpot_items = []
    for row in hotpot_rows:
        context = row["context"]
        paragraphs = [f"{title}. {''.join(sentences)}"
                      for title, sentences in zip(context["title"], context["sentences"])]
        hotpot_items.append({
            "id": row["id"],
            "question": row["question"],
            "paragraphs": paragraphs,
            "answers": [row["answer"]],
            "unanswerable": False,
        })
    rng.shuffle(hotpot_items)
    hotpot_sample = hotpot_items[:SAMPLE_SIZE]

    # ---- closed decisions ---------------------------------------------------------------
    snips_items = []
    for intent, body in snips.items():
        parsed = json.loads(body.decode("utf-8", errors="replace"))
        for entry in parsed[intent]:
            text = "".join(part["text"] for part in entry["data"])
            snips_items.append({"id": f"snips-{intent}-{len(snips_items)}",
                                "text": text.strip(), "label": intent})
    rng.shuffle(snips_items)
    snips_sample = snips_items[:SAMPLE_SIZE]

    trec_lines = payloads["trec"].decode("latin-1").splitlines()
    trec_items = []
    for index, line in enumerate(trec_lines):
        label, _, text = line.partition(" ")
        coarse = label.split(":")[0]
        trec_items.append({"id": f"trec-{index}", "text": text.strip(), "label": coarse})
    rng.shuffle(trec_items)
    trec_sample = trec_items[:SAMPLE_SIZE]

    samples = {"squad2": squad_sample, "hotpotqa": hotpot_sample,
               "snips": snips_sample, "trec": trec_sample}
    for name, items in samples.items():
        path = HERE / f"sample-{name}.json"
        body = json.dumps(items, indent=1, sort_keys=True).encode()
        path.write_bytes(body)
        manifest.setdefault("samples", {})[name] = {
            "items": len(items), "file": path.name, "sha256": hashlib.sha256(body).hexdigest()}
        print(f"sample {name}: {len(items)} items")

    labels = {"snips": sorted(SNIPS_INTENTS),
              "trec": sorted({i["label"] for i in trec_items})}
    manifest["labelSets"] = labels
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("MANIFEST.json written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
