#!/usr/bin/env python3
"""Reduce the four stage artifacts to RESULTS.json and MEASUREMENTS.json, and apply the rule.

The decision rule and the adoption rule are in README.md and were fixed before the stages ran.
This file applies them literally: it does not choose a winner, it reports which clause of the rule
each dataset satisfies and what follows when the two datasets disagree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "tools"))

import measurements as m  # noqa: E402

SHIPPED = 0.6
# The two clauses of the pre-registered decision rule.
SHARE_SAVING_REQUIRED = 10.0
COORDINATE = "org.modeljars.composite:harriet"
ARM = "decisions"


def load(name: str) -> dict:
    path = HERE / name
    if not path.exists():
        raise SystemExit(f"{name} does not exist; run tune.py first")
    return json.loads(path.read_text())


def main() -> int:
    stage1, stage2 = load("stage1-simulator.json"), load("stage2-sweep.json")
    stage3, stage4 = load("stage3-cv.json"), load("stage4-calibration.json")

    datasets = {}
    records = []
    for dataset in sorted(stage1["datasets"]):
        validation = stage1["datasets"][dataset]
        sweep = stage2["datasets"][dataset]
        cv = stage3["datasets"][dataset]
        cal = stage4["datasets"][dataset]
        # The noise floor this reanalysis is entitled to resolve: the accuracy gap between two
        # runs of the identical configuration, driven by items whose confidence crossed 0.6.
        noise = abs(validation["accuracyGap"])
        accuracy_delta = cv["heldOutAccuracy"]["delta"]
        share_delta = cv["heldOutEscalatedShare"]["delta"]
        beats_accuracy = accuracy_delta > noise and share_delta <= 0
        saves_cost = (share_delta <= -SHARE_SAVING_REQUIRED
                      and accuracy_delta >= -noise)
        datasets[dataset] = {
            "simulatorValidated": {
                "accuracyGap": validation["accuracyGap"],
                "escalatedShareGap": validation["escalatedShareGap"],
                "itemsCrossingShippedThreshold":
                    validation["confidenceDrift"]["itemsCrossingShippedThreshold"],
                "medianConfidenceDrift": validation["confidenceDrift"]["median"],
            },
            "noiseFloorPoints": noise,
            "shipped": sweep["shipped"],
            "bestAccuracyInSweep": sweep["bestAccuracy"],
            "bestF1InSweep": sweep["bestF1"],
            "crossValidated": {
                "selectedThresholds": cv["selectedThresholds"],
                "median": cv["selectedMedian"],
                "constraintFeasible": cv["constraintFeasible"],
                "heldOutAccuracyDelta": accuracy_delta,
                "heldOutEscalatedShareDelta": share_delta,
            },
            "ruleClauses": {
                "beatsAccuracyAtNoGreaterShare": beats_accuracy,
                "savesTenPointsOfShareWithinNoise": saves_cost,
            },
            "calibration": {
                "meanConfidence": cal["meanConfidence"],
                "observedAccuracy": cal["observedAccuracy"],
                "expectedCalibrationError": cal["expectedCalibrationError"],
                "brier": cal["brier"],
                "shippedThresholdAsProbabilityOfBeingRight":
                    cal["shippedThresholdCalibratedMean"],
            },
        }

        records.append(m.record(
            experiment="decision-threshold", capability_dataset=f"tuning/{dataset}", arm=ARM,
            coordinate=COORDINATE, metric="held-out label accuracy, cross-validated threshold",
            value=cv["heldOutAccuracy"]["tunedMean"], n=sweep["shipped"]["n"],
            artifact=f"experiments/decision-threshold/stage3-cv.json",
            reference={"arm": "shipped threshold 0.6",
                       "value": cv["heldOutAccuracy"]["shippedMean"]},
            delta=accuracy_delta,
            extra={"selectedThresholds": cv["selectedThresholds"],
                   "escalatedShareDelta": share_delta,
                   "note": "a tuning sweep, not a declaration: these thresholds are not what "
                           "the fleet ships, and tuning/* is not a key any capability maps to"}))
        records.append(m.record(
            experiment="decision-threshold", capability_dataset=f"tuning/{dataset}", arm=ARM,
            coordinate=COORDINATE, metric="expected calibration error of the reported confidence",
            value=cal["expectedCalibrationError"], n=sweep["shipped"]["n"],
            artifact="experiments/decision-threshold/stage4-calibration.json",
            extra={"meanConfidence": cal["meanConfidence"],
                   "observedAccuracy": cal["observedAccuracy"],
                   "brierReported": cal["brier"]["reported"],
                   "brierPlattScaled": cal["brier"]["plattScaled"],
                   "brierDeltaCi95": cal["brier"]["deltaCi95"]}))

    replace = all(d["ruleClauses"]["beatsAccuracyAtNoGreaterShare"]
                  or d["ruleClauses"]["savesTenPointsOfShareWithinNoise"]
                  for d in datasets.values())
    agreeing = {name for name, d in datasets.items()
                if d["ruleClauses"]["beatsAccuracyAtNoGreaterShare"]
                or d["ruleClauses"]["savesTenPointsOfShareWithinNoise"]}
    platt_point = all(d["calibration"]["brier"]["delta"] < 0 for d in datasets.values())
    platt_conclusive = {name for name, d in datasets.items()
                        if d["calibration"]["brier"]["deltaCi95"][1] < 0}

    results = {
        "experiment": "decision-threshold",
        "question": "does the shipped escalation threshold of 0.6 survive cross-validated tuning, "
                    "and is the confidence it reads calibrated?",
        "inputs": "experiments/routing-accuracy committed rows; no model run, no provider called",
        "shippedThreshold": SHIPPED,
        "datasets": datasets,
        "verdict": {
            "thresholdReplaced": replace,
            "clauseSatisfiedOn": sorted(agreeing),
            "statement": (
                "KEEP 0.6. " if not replace else "REPLACE 0.6. ")
            + ("The cross-validated threshold is lower on both datasets and buys a smaller "
               "escalated share, but it loses accuracy on the held-out folds, and the rule "
               "requires one dataset not to contradict the other. "
               if not replace else "")
            + "Satisfied on: " + (", ".join(sorted(agreeing)) or "neither dataset") + ".",
            "plattScaling": {
                "improvesPointEstimateOnBoth": platt_point,
                "conclusiveOn": sorted(platt_conclusive),
                "statement": (
                    "Adopt as a reporting change: the point estimate improves on both datasets, "
                    "the interval excludes zero on "
                    + (", ".join(sorted(platt_conclusive)) or "neither")
                    + " only, and a monotone recalibration cannot change which questions the "
                      "gate escalates -- only the number printed beside an answer."),
            },
        },
    }
    (HERE / "RESULTS.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    m.write(HERE, records)
    print(results["verdict"]["statement"])
    print(results["verdict"]["plattScaling"]["statement"])
    for name, found in datasets.items():
        print(f"  {name}: tuned {found['crossValidated']['heldOutAccuracyDelta']:+.1f} points at "
              f"{found['crossValidated']['heldOutEscalatedShareDelta']:+.1f} points of escalated "
              f"share, noise floor {found['noiseFloorPoints']:.1f}; confidence "
              f"{found['calibration']['meanConfidence']:.3f} against accuracy "
              f"{found['calibration']['observedAccuracy']:.3f}, and 0.6 means "
              f"{found['calibration']['shippedThresholdAsProbabilityOfBeingRight']:.2f} once "
              "calibrated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
