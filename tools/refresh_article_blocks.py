#!/usr/bin/env python3
"""Replace the article's quoted run output with the committed logs, verbatim.

The article quotes four blocks of fleet.java output: the warm-up plus routing table, the warm
timing table, the ledger, and the all-remote counterfactual. Each is lifted straight out of
evidence/fleet-routing/{routed,all-remote}.log so a figure cannot drift from the run that produced
it. Hand-editing these blocks is how a stale number survives a re-measurement.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fleet_logs import latest_pair

ROOT = Path(__file__).resolve().parent.parent
ARTICLE = ROOT / "article.md"


def slice_between(text: str, start: str, end: str | None) -> str:
    begin = text.index(start)
    stop = text.index(end, begin) if end else len(text)
    return text[begin:stop].rstrip()


def replace_block(article: str, first_line: str, body: str) -> str:
    """Swap the untagged fenced block whose first line starts with `first_line`."""
    pattern = re.compile(r"^```\n(" + re.escape(first_line) + r".*?)^```", re.S | re.M)
    matches = list(pattern.finditer(article))
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one block starting {first_line!r}, found {len(matches)}")
    match = matches[0]
    return article[: match.start()] + "```\n" + body + "\n```" + article[match.end():]


def main() -> int:
    stamp, routed, remote = latest_pair()
    article = ARTICLE.read_text()

    article = replace_block(article, "WARMING", slice_between(routed, "WARMING", "\n== timing"))
    article = replace_block(
        article, "== timing, warm ==", slice_between(routed, "== timing, warm ==", "\n== ledger")
    )
    article = replace_block(article, "== ledger ==", slice_between(routed, "== ledger ==", None))
    article = replace_block(
        article, "PROMPT", slice_between(remote, "PROMPT", None)
    )

    ARTICLE.write_text(article)
    print(f"refreshed four output blocks from run {stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
