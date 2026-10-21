#!/usr/bin/env python3
"""Cut a held-out sample for the rubric experiment, provably disjoint from the measured one.

Disjointness is built rather than derived. The first attempt tried to reproduce
`../routing-accuracy/fetch_datasets.py`'s shuffle and take `items[100:200]` from it, and the check
below caught that it could not: that script consumes one shared `Random(20261019)` across four
corpora, so the generator state at the SNIPS shuffle is not a fresh seed and 176 of the 100 ids came
out different. So this excludes the committed sample's ids outright, shuffles what is left with its
own declared seed, and keeps the first hundred. No item can appear in both by construction, and the
check that found the first bug stayed in.

Why a new sample at all: the errors in the first hundred have been read, item by item, by
`../routing-accuracy/error_analysis.py` and by me. Any rubric written from them is written with the
test set in view, and measuring the result on those same items would report how well a rubric fits
errors it was shown. The first hundred are the development set from here on. These are the ones that
decide anything.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "routing-accuracy"
sys.path.insert(0, str(SOURCE))

MEASURED_SEED = 20261019   # the seed ../routing-accuracy cut its sample with
SEED = 20261021            # this sample's own seed, declared before it was drawn
SAMPLE_SIZE = 100
SNIPS_INTENTS = ["AddToPlaylist", "BookRestaurant", "GetWeather", "PlayMusic",
                 "RateBook", "SearchCreativeWork", "SearchScreeningEvent"]
SNIPS_URL = ("https://raw.githubusercontent.com/sonos/nlu-benchmark/master/"
             "2017-06-custom-intent-engines/{intent}/validate_{intent}.json")


def pinned_sha(key: str) -> str:
    """The SHA-256 the measured experiment recorded for a source, before it read a single item."""
    manifest = json.loads((SOURCE / "MANIFEST.json").read_text())
    try:
        return manifest["sources"][key]["sha256"]
    except KeyError:
        raise SystemExit(f"../routing-accuracy/MANIFEST.json has no pin for {key}") from None


def fetch_pinned(url: str, key: str) -> bytes:
    """Download and refuse anything whose bytes are not the ones that were measured.

    The SNIPS files were hashed by the measured experiment but not kept on disk, so this re-fetches
    them and checks the digest. A corpus that changed upstream fails here rather than silently
    producing a held-out set drawn from a different population than the development set.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "decision-rubric-tuning/1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read()
    digest = hashlib.sha256(body).hexdigest()
    if digest != pinned_sha(key):
        raise SystemExit(
            f"{url} now hashes to {digest[:16]}, not the pinned {pinned_sha(key)[:16]}: the "
            "corpus changed and these two samples would not be from the same population")
    return body


def snips_items() -> list[dict]:
    items = []
    for intent in SNIPS_INTENTS:
        body = fetch_pinned(SNIPS_URL.format(intent=intent), f"snips/{intent}")
        parsed = json.loads(body.decode("utf-8", errors="replace"))
        for entry in parsed[intent]:
            text = "".join(part["text"] for part in entry["data"])
            items.append({"id": f"snips-{intent}-{len(items)}",
                          "text": text.strip(), "label": intent})
    return items


def trec_items() -> list[dict]:
    raw = SOURCE / "data" / "trec.raw"
    if not raw.exists():
        raise SystemExit(f"{raw} is missing: run ../routing-accuracy/fetch_datasets.py first")
    body = raw.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    if digest != pinned_sha("trec"):
        raise SystemExit(f"{raw} hashes to {digest[:16]}, not the pinned {pinned_sha('trec')[:16]}")
    items = []
    for index, line in enumerate(body.decode("latin-1").splitlines()):
        label, _, text = line.partition(" ")
        items.append({"id": f"trec-{index}", "text": text.strip(),
                      "label": label.split(":")[0]})
    return items


def main() -> int:
    manifest = {"seed": SEED, "measuredSeed": MEASURED_SEED, "sampleSize": SAMPLE_SIZE,
                "slice": "every item not in ../routing-accuracy's committed sample, shuffled with "
                         "this file's own seed, first 100",
                "samples": {}}
    for name, builder in (("snips", snips_items), ("trec", trec_items)):
        items = builder()
        committed = SOURCE / f"sample-{name}.json"
        if not committed.exists():
            raise SystemExit(f"{committed} is missing; there is nothing to be disjoint from")
        measured_ids = {i["id"] for i in json.loads(committed.read_text())}
        if not measured_ids <= {i["id"] for i in items}:
            raise SystemExit(
                f"{name}: the committed sample contains ids this corpus does not, so the two were "
                "not drawn from the same download")
        remaining = [i for i in items if i["id"] not in measured_ids]
        rng = random.Random(SEED)
        rng.shuffle(remaining)
        heldout = remaining[:SAMPLE_SIZE]
        overlap = measured_ids & {i["id"] for i in heldout}
        if overlap:
            raise SystemExit(f"{name}: {len(overlap)} held-out items are in the measured sample")
        path = HERE / f"sample-{name}-heldout.json"
        body = json.dumps(heldout, indent=1, sort_keys=True).encode()
        path.write_bytes(body)
        manifest["samples"][name] = {
            "file": path.name,
            "items": len(heldout),
            "drawnFrom": len(remaining),
            "corpus": len(items),
            "sha256": hashlib.sha256(body).hexdigest(),
            "measuredSampleIds": len(measured_ids),
            "overlapWithMeasured": 0,
        }
        print(f"{name}: {len(heldout)} held-out items drawn from the {len(remaining)} the measured "
              f"sample did not take, out of {len(items)}; overlap 0")
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {HERE / 'MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
