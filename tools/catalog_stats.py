#!/usr/bin/env python3
"""Derive every catalog figure the article states from the published catalog.

Reads evidence/modeljars-catalog.json -- the exact body served by
https://modeljars.org/catalog.json -- and prints the counts the article quotes. Nothing in that
section of the article is typed by hand; if this script cannot derive it, it does not go in.
"""

from __future__ import annotations

import argparse
import json
import re
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


def grouped(counts: Counter, name: str) -> tuple[str, ...]:
    """Every spelling the article may use for one tally entry, each stating the count.

    The table lists most entries as `qwen2 (21)` and collapses ties into `gemma3 and lfm2 (4
    each)`. Both forms are accepted, and both carry the number -- a spelling that matched the name
    alone would let a changed count through for whichever family is written first.
    """
    count = counts[name]
    siblings = [other for other, c in counts.items() if c == count and other != name]
    spellings = [f"{name} ({count})", f"{name} ({count} each)"]
    for sibling in siblings:
        spellings.append(f"{name} and {sibling} ({count} each)")
        spellings.append(f"{sibling} and {name} ({count} each)")
    return tuple(spellings)


def check(entries: list[dict], sizes: list[int], repos: set) -> int:
    """Fail if the article states a catalog figure this script no longer derives.

    The catalog section was derived once and then pasted, which holds exactly until the published
    catalog is refreshed: a new entry moves a dozen counts and nothing in the repository notices.
    The prose here is curated -- it groups co-extensive capabilities and names five licences out of
    eleven -- so it is checked rather than regenerated, in the shape the article writes it.
    """
    # Newlines are collapsed: the article wraps at a hundred columns, so a figure and its noun are
    # routinely on different lines and a substring check on the raw text fails on the wrap rather
    # than on the number.
    raw = (ROOT / "article.md").read_text()
    # Scoped to the catalog section, because the same figure appears elsewhere in the article: a
    # drifted count in this table passed the first version of this check on the strength of the
    # conclusion still quoting the old one.
    start = raw.index("## What the catalog holds today")
    end = raw.index("\n## ", start + 1)
    article = " ".join(raw[start:end].split())
    whole = " ".join(raw.split())
    caps = tally(entries, "capabilities")
    arch = tally(entries, "architecture")
    quant = tally(entries, "quantization")
    lic = tally(entries, "license")
    dom = tally(entries, "domains")
    quals = {
        label: sum(1 for e in entries if e.get(field))
        for field, label in (("ragQualifications", "RAG"),
                             ("embeddingQualifications", "embedding"),
                             ("performanceProfiles", "performance profile"),
                             ("toolQualifications", "tool"),
                             ("speechQualifications", "speech"))
    }
    named = {"Apache-2.0", "LicenseRef-Gemma", "MIT", "LicenseRef-Llama-3.2", "LicenseRef-LFM-1.0"}
    rest = {k: v for k, v in lic.items() if k not in named}

    required = [
        f"{len(entries)} entries",
        f"{len(repos)} upstream",
        f"{sum(sizes) / GB:.1f} GB",
        f"{len(sizes)} that declare a size",
        f"{min(sizes) / MB:.1f} MB",
        f"{max(sizes) / GB:.1f} GB",
        f"{median(sizes) / GB:.2f} GB",
        # Format, written as "97 GGUF, 3 safetensors, ...".
        *(f"{count} {name}" for name, count in tally(entries, "format").items()),
        # Capability, where the article groups the pairs that are co-extensive in the data.
        f"{caps['chat']} chat and text-generation",
        f"{caps['text-embedding']} text-embedding and semantic-search",
        f"{caps['code-completion']} code-completion",
        f"{caps['tool-calling']} tool-calling",
        f"{caps['reranking']} each reranking",
        # Architecture and quantization, written as "name (count)" -- except where the article
        # groups two families that share a count, as "gemma3 and lfm2 (4 each)". Both spellings
        # carry the same number, so both are accepted.
        f"{len(arch)} distinct families",
        *(grouped(arch, name) for name, _count in arch.most_common(11)),
        f"{len(quant)} schemes",
        *(grouped(quant, name) for name, _count in quant.most_common(4)),
        *(grouped(dom, name) for name, _count in dom.most_common(5)),
        # Licences, written by their short names.
        f"{lic['Apache-2.0']} Apache-2.0",
        f"{lic['LicenseRef-Gemma']} Gemma",
        f"{lic['MIT']} MIT",
        f"{lic['LicenseRef-Llama-3.2']} Llama-3.2",
        f"{lic['LicenseRef-LFM-1.0']} LFM-1.0",
        f"{len(rest)} single-model",
        *(f"{count} entries carry {label} qualifications" if label == "RAG"
          else f"{count} have a {label}" if label == "performance profile"
          else f"{count} carry {label}" for label, count in quals.items()),
    ]
    missing = [item for item in required
               if not any(spelling.lower() in article.lower()
                          for spelling in (item if isinstance(item, tuple) else (item,)))]
    if missing:
        print("the catalog section of article.md no longer states these derived figures:")
        for item in missing:
            print(f"  {item!r}")
        return 1

    # Anywhere in the article, "N entries" has to be a count this catalog supports. The conclusion
    # states the entry count too, and a figure quoted twice drifts in one place first.
    allowed = {len(entries), len(sizes)} | set(quals.values())
    quoted = {int(m) for m in re.findall(r"(\d+) entries", whole)}
    wrong = sorted(quoted - allowed)
    if wrong:
        print(f"article.md states '{wrong[0]} entries', which no count in the published catalog "
              f"supports; derived counts: {sorted(allowed)}")
        return 1
    print(f"PASS: article.md states all {len(required)} derived catalog figures")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="verify article.md against these figures instead of printing them")
    args = parser.parse_args()
    entries = json.loads(CATALOG.read_text())
    # The two composite entries declare requiredWeightBytes rather than sizeBytes, because their
    # weights are another catalogued model's. Counting them would double-count those bytes, so the
    # size figures cover the 101 entries that own their artifact.
    sizes = [e["sizeBytes"] for e in entries if e.get("sizeBytes")]
    shared = [e["id"] for e in entries if not e.get("sizeBytes")]
    assert len(sizes) + len(shared) == len(entries)
    repos = {e["sourceId"] for e in entries if e.get("sourceId")}

    if args.check:
        return check(entries, sizes, repos)

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
