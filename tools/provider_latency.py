#!/usr/bin/env python3
"""Summarise repeated provider calls on one identical prompt.

A hosted model's latency is not deterministic: the same input can take two seconds or twenty,
depending on queueing the caller cannot see. One sample is an anecdote. This reduces the committed
samples to a range, so the article can quote what was observed and how many times, rather than a
single number that looks like a property of the model.
"""

from __future__ import annotations

import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "evidence/fleet-routing/appendix-providers.log"


def main() -> int:
    text = LOG.read_text()
    models = dict.fromkeys(re.findall(r"^(\S+)\s+run\d+", text, re.M))
    print(f"{'model':<16}{'n':>3}{'min':>9}{'median':>9}{'max':>9}{'spread':>9}   cost (identical input)")
    for model in models:
        ms = [int(v) for v in re.findall(rf"^{re.escape(model)}\s+run\d+\s+(\d+) ms", text, re.M)]
        cost = [float(c) for c in re.findall(rf"^{re.escape(model)}.*\$([\d.]+)", text, re.M)]
        if not ms:
            continue
        print(f"{model:<16}{len(ms):>3}{min(ms):>8,}{int(statistics.median(ms)):>9,}"
              f"{max(ms):>9,}{max(ms)/min(ms):>8.1f}x   ${statistics.median(cost):.6f}"
              f"  (varies by ${max(cost)-min(cost):.6f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
