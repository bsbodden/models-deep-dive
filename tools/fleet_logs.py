#!/usr/bin/env python3
"""Pick the measurement pair the article is built from.

The live evidence/fleet-routing/{routed,all-remote}.log are the harness's working files: it
truncates them at the start of each attempt, so anything reading them while a run is in flight gets
half a log. The timestamped copies under runs/ are written only after a pair is accepted, so they
are immutable and complete.

Everything that generates article text reads the newest archived pair through here, which also
guarantees the quoted output blocks and the derived tables come from the same run rather than from
two different ones.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "evidence/fleet-routing/runs"


def latest_pair() -> tuple[str, str, str]:
    """(stamp, routed text, all-remote text) for the newest complete archived pair."""
    for routed in sorted(RUNS.glob("*-routed.log"), reverse=True):
        remote = routed.with_name(routed.name.replace("-routed", "-all-remote"))
        if not remote.exists():
            continue
        rt, bt = routed.read_text(), remote.read_text()
        if "== ledger ==" in rt and "== every prompt" in bt:
            return routed.name[:16], rt, bt
    raise SystemExit(f"no complete archived pair in {RUNS}")
