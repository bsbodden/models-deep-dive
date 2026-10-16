#!/usr/bin/env python3
"""Snapshot HuggingFace 30-day download counts for every upstream repository in the catalog.

Writes evidence/huggingface-downloads.json: one record per repository with the count the API
reported and the UTC instant it was read, so the article's popularity table is reproducible from a
committed artifact rather than from a number someone remembered.
"""

from __future__ import annotations

import datetime
import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "evidence/modeljars-catalog.json"
OUT = ROOT / "evidence/huggingface-downloads.json"


def main() -> int:
    entries = json.loads(CATALOG.read_text())
    repos = sorted({e["sourceId"] for e in entries if e.get("sourceId")})
    by_repo: dict[str, list[str]] = {}
    for entry in entries:
        by_repo.setdefault(entry.get("sourceId", ""), []).append(entry["id"])

    read_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    records = []
    for source in repos:
        repo = source.removeprefix("hf://")
        record = {"sourceId": source, "repo": repo, "catalogEntries": sorted(by_repo[source])}
        try:
            with urllib.request.urlopen(
                f"https://huggingface.co/api/models/{repo}", timeout=30
            ) as response:
                body = json.load(response)
            # `downloads` is the trailing-30-day figure the API reports; absent for some repos.
            record["downloads"] = body.get("downloads")
            record["downloadsAllTime"] = body.get("downloadsAllTime")
            record["status"] = 200
        except urllib.error.HTTPError as error:
            record["downloads"] = None
            record["status"] = error.code
        except Exception as error:  # network trouble is data, not a crash
            record["downloads"] = None
            record["status"] = f"{type(error).__name__}: {error}"
        records.append(record)
        print(f"{record['status']}\t{record['downloads']}\t{repo}", flush=True)

    OUT.write_text(json.dumps({"readAt": read_at, "repositories": records}, indent=2) + "\n")
    reported = [r for r in records if isinstance(r["downloads"], int)]
    print(f"\nread at {read_at}")
    print(f"{len(records)} repositories, {len(reported)} reported a count, "
          f"total {sum(r['downloads'] for r in reported):,} downloads in thirty days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
