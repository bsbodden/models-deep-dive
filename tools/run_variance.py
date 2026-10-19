#!/usr/bin/env python3
"""Print the run-to-run spread across every archived measurement pair.

One implementation only: this prints exactly the block that article_figures.py writes into the
article, so the run record and the article cannot disagree about the same number. Committed as
evidence/fleet-routing/VARIANCE.txt by tools/measure_fleet.sh.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from article_figures import variance_region

if __name__ == "__main__":
    print(variance_region())
