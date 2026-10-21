#!/usr/bin/env python3
"""Render the article's popularity table from the committed download snapshot.

With --check, verify the article against the snapshot instead of printing: the table, the total,
the read date, the count of repositories that report nothing, and the rank and figure of the
embedding model the article singles out just below the table. Refreshing the snapshot reorders all
of it, and the table is pasted rather than generated because its rows carry no prose to mangle.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "evidence/huggingface-downloads.json"
TOP = 7


WORDS = {0: "none", 1: "one", 2: "two", 3: "three", 4: "four"}


def check(data: dict, reported: list[dict], missing: list[dict]) -> int:
    article = " ".join((ROOT / "article.md").read_text().split())
    total = len(reported) + len(missing)
    required: list[str | tuple[str, ...]] = [
        data["readAt"][:10],
        f"{len(reported)} repositories that report counts",
        f"{sum(r['downloads'] for r in reported):,} downloads",
        # Small counts are spelled out in the prose and printed as digits by this script.
        (f"{len(missing)} of the {total} report no count",
         f"{WORDS.get(len(missing), len(missing))} of the {total} report no count"),
        *(f"| {r['repo']} | {r['downloads']:,} | `{r['catalogEntries'][0]}` |"
          for r in reported[:TOP]),
    ]
    # The one row the article promotes into prose, by its rank as well as its figure: a refreshed
    # snapshot can leave the number right and the ordinal wrong.
    ordinals = {8: "eighth", 9: "ninth", 10: "tenth", 11: "eleventh"}
    for rank, row in enumerate(reported, 1):
        if rank <= TOP:
            continue
        if row["repo"] in article:
            required.append(f"{ordinals.get(rank, str(rank))} by downloads")
            required.append(f"{row['downloads']:,}")
            break

    missing_items = [
        item for item in required
        if not any(spelling.lower() in article.lower()
                   for spelling in (item if isinstance(item, tuple) else (item,)))]
    if missing_items:
        print("article.md no longer states these figures from the download snapshot:")
        for item in missing_items:
            print(f"  {item!r}")
        return 1
    print(f"PASS: article.md states all {len(required)} figures from the download snapshot")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="verify article.md against the snapshot instead of printing it")
    args = parser.parse_args()
    data = json.loads(SNAPSHOT.read_text())
    records = data["repositories"]
    reported = [r for r in records if isinstance(r["downloads"], int)]
    missing = [r for r in records if not isinstance(r["downloads"], int)]
    reported.sort(key=lambda r: r["downloads"], reverse=True)

    if args.check:
        return check(data, reported, missing)

    print(f"read at {data['readAt']}")
    print(f"{len(records)} repositories; {len(reported)} reported, {len(missing)} did not")
    print(f"total across reporting repositories: {sum(r['downloads'] for r in reported):,}")
    print("\nnot reporting:")
    for r in missing:
        print(f"  {r['sourceId']}  (status {r['status']})  entries={r['catalogEntries']}")

    print("\n| Upstream repository | 30-day downloads | Catalog entry |")
    print("| --- | --- | --- |")
    for r in reported[:TOP]:
        print(f"| {r['repo']} | {r['downloads']:,} | `{r['catalogEntries'][0]}` |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
