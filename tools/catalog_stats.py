#!/usr/bin/env python3
"""Derive every catalog figure the article states from the published catalog.

Reads evidence/modeljars-catalog.json -- the exact body served by
https://modeljars.org/catalog.json -- and prints the counts the article quotes. Nothing in that
section of the article is typed by hand; if this script cannot derive it, it does not go in.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "evidence/modeljars-catalog.json"
# Decimal SI units, as storage sizes are conventionally quoted and as the article states them.
GB = 1_000_000_000
MB = 1_000_000


def tally(entries: list[dict], key: str) -> Counter:
    counts: Counter = Counter()
    for entry in entries:
        value = entry.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            counts.update(value)
        else:
            counts[value] += 1
    return counts


def show(label: str, counts: Counter, limit: int | None = None) -> None:
    items = counts.most_common(limit)
    body = ", ".join(f"{name} ({count})" for name, count in items)
    print(f"{label}: {len(counts)} distinct -- {body}")


def main() -> int:
    entries = json.loads(CATALOG.read_text())
    # The two composite entries declare requiredWeightBytes rather than sizeBytes, because their
    # weights are another catalogued model's. Counting them would double-count those bytes, so the
    # size figures cover the 101 entries that own their artifact.
    sizes = [e["sizeBytes"] for e in entries if e.get("sizeBytes")]
    shared = [e["id"] for e in entries if not e.get("sizeBytes")]
    assert len(sizes) + len(shared) == len(entries)
    repos = {e["sourceId"] for e in entries if e.get("sourceId")}

    print(f"entries: {len(entries)}")
    print(f"upstream repositories (distinct sourceId): {len(repos)}")
    print(f"total size: {sum(sizes) / GB:.1f} GB across {len(sizes)} entries that own their artifact")
    print(f"sharing another entry's weights: {shared}")
    print(f"smallest: {min(sizes) / MB:.1f} MB")
    print(f"largest: {max(sizes) / GB:.1f} GB")
    print(f"median: {median(sizes) / GB:.2f} GB")

    show("format", tally(entries, "format"))
    show("capability", tally(entries, "capabilities"))
    show("architecture", tally(entries, "architecture"))
    show("quantization", tally(entries, "quantization"))
    show("license", tally(entries, "license"))
    counts = tally(entries, "domains")
    show("domain", counts)

    # Licences beyond the five the article names individually.
    licenses = tally(entries, "license")
    named = {"Apache-2.0", "LicenseRef-Gemma", "MIT", "LicenseRef-Llama-3.2", "LicenseRef-LFM-1.0"}
    rest = {k: v for k, v in licenses.items() if k not in named}
    noncommercial = [k for k in rest if "noncommercial" in k.lower() or "non-commercial" in k.lower()]
    print(f"single-model licence terms beyond the five named: {len(rest)} -- "
          + ", ".join(f"{k} ({v})" for k, v in sorted(rest.items()))
          + f"; non-commercial among them: {len(noncommercial)}")

    for field, label in (
        ("ragQualifications", "RAG"),
        ("embeddingQualifications", "embedding"),
        ("performanceProfiles", "performance profile"),
        ("rerankingQualifications", "reranking"),
        ("speechQualifications", "speech"),
        ("toolQualifications", "tool"),
        ("compositionQualifications", "composition"),
    ):
        n = sum(1 for e in entries if e.get(field))
        print(f"entries carrying {label} qualifications: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
