#!/usr/bin/env python3
"""Fail if FINDINGS.md states a figure the stage artifacts do not contain.

FINDINGS.md is prose and stays hand-written; what it must not be is hand-computed. Every figure
listed here is rebuilt from the artifact it belongs to and looked for in the text, in the forms the
prose is allowed to use (a probability as `0.82` or as `82%`).
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def forms(value: float, places: int) -> tuple[str, ...]:
    out = [f"{value:.{places}f}"]
    if 0.0 < value < 1.0:
        out.append(f"{round(value * 100)}%")
        out.append(f"{value * 100:.1f}")
    return tuple(out)


def main() -> int:
    text = (HERE / "FINDINGS.md").read_text()
    stages = {name: json.loads((HERE / f"stage{name}.json").read_text())
              for name in ("1-simulator", "2-sweep", "3-cv", "4-calibration")}
    required: list[tuple[str, tuple[str, ...]]] = []
    for dataset in ("snips", "trec"):
        d1 = stages["1-simulator"]["datasets"][dataset]
        d2 = stages["2-sweep"]["datasets"][dataset]
        d3 = stages["3-cv"]["datasets"][dataset]
        d4 = stages["4-calibration"]["datasets"][dataset]
        required += [
            (f"{dataset} simulated accuracy", forms(d1["simulated"]["accuracy"], 1)),
            (f"{dataset} measured accuracy", forms(d1["measured"]["accuracy"], 1)),
            (f"{dataset} median drift", forms(d1["confidenceDrift"]["median"], 4)),
            (f"{dataset} max drift", forms(d1["confidenceDrift"]["max"], 4)),
            (f"{dataset} items crossing 0.6",
             (str(d1["confidenceDrift"]["itemsCrossingShippedThreshold"]),)),
            (f"{dataset} precision at 0.6", forms(d2["shipped"]["precision"], 3)),
            (f"{dataset} recall at 0.6", forms(d2["shipped"]["recall"], 3)),
            (f"{dataset} best F1", forms(d2["bestF1"]["f1"], 3)),
            (f"{dataset} best-F1 threshold", (f"{d2['bestF1']['threshold']:.2f}",)),
            (f"{dataset} tuned held-out accuracy", forms(d3["heldOutAccuracy"]["tunedMean"], 1)),
            (f"{dataset} shipped held-out accuracy",
             forms(d3["heldOutAccuracy"]["shippedMean"], 1)),
            (f"{dataset} mean confidence", forms(d4["meanConfidence"], 3)),
            (f"{dataset} observed accuracy", forms(d4["observedAccuracy"], 3)),
            (f"{dataset} ECE", forms(d4["expectedCalibrationError"], 3)),
            (f"{dataset} Brier reported", forms(d4["brier"]["reported"], 4)),
            (f"{dataset} Brier Platt-scaled", forms(d4["brier"]["plattScaled"], 4)),
            (f"{dataset} calibrated meaning of 0.6",
             forms(d4["shippedThresholdCalibratedMean"], 2)),
        ]
    missing = [(label, spellings) for label, spellings in required
               if not any(s in text for s in spellings)]
    if missing:
        print("FINDINGS.md does not state these figures from the artifacts:")
        for label, spellings in missing:
            print(f"  {label}: expected one of {spellings}")
        return 1
    print(f"PASS: FINDINGS.md states all {len(required)} figures from the stage artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
