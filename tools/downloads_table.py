#!/usr/bin/env python3
"""Render the article's popularity table from the committed download snapshot."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "evidence/huggingface-downloads.json"
TOP = 7


def main() -> int:
    data = json.loads(SNAPSHOT.read_text())
    records = data["repositories"]
    reported = [r for r in records if isinstance(r["downloads"], int)]
    missing = [r for r in records if not isinstance(r["downloads"], int)]
    reported.sort(key=lambda r: r["downloads"], reverse=True)

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
