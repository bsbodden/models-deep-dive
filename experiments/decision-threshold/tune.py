#!/usr/bin/env python3
"""Tune and audit the decision arm's escalation threshold from rows already committed.

Four stages, in order, each refusing to run before its prerequisite's artifact exists. The method
is the one in Hamel Husain's "How To Use Decision Models For Evals": requirement first, threshold
by cross-validation, calibration checked rather than assumed. The adaptation to this fleet, and
the decision rule, are in README.md; this file only measures.

Run: tune.py [stage1|stage2|stage3|stage4|all]
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ROUTING = ROOT / "experiments/routing-accuracy"
DATASETS = ("snips", "trec")
SHIPPED = 0.6
SEED = 20261021
FOLDS = 5
# The requirement, fixed before the analysis: of the questions the gate hands to a provider, at
# least 80% should be ones the local arm would have got wrong, and it should catch at least 80% of
# those mistakes. Both numbers are the post's worked example, kept rather than tuned to taste.
MIN_PRECISION = 0.80
MIN_RECALL = 0.80


def rows(arm: str, dataset: str) -> dict[str, dict]:
    path = ROUTING / f"results-decide-{arm}-{dataset}.jsonl"
    if not path.exists():
        raise SystemExit(f"missing raw rows: {path.relative_to(ROOT)}")
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["id"]] = row
    return out


def items(dataset: str) -> list[dict]:
    """One record per item: the local arm's answer and confidence, and the provider's answer."""
    local, api = rows("routed", dataset), rows("api", dataset)
    shared = sorted(set(local) & set(api))
    if len(shared) != len(local) or len(shared) != len(api):
        raise SystemExit(f"{dataset}: the two arms do not cover the same items "
                         f"({len(local)} local, {len(api)} api, {len(shared)} shared)")
    return [{
        "id": i,
        "gold": local[i]["gold"],
        "confidence": local[i]["confidence"],
        "localRight": local[i]["answer"] == local[i]["gold"],
        "apiRight": api[i]["answer"] == api[i]["gold"],
    } for i in shared]


def at(threshold: float, pool: list[dict]) -> dict:
    """The gate's behaviour at one threshold, over one pool of items.

    `escalated` is the gate's positive class; `localWrong` is the ground truth it is trying to
    predict. Accuracy is the combined arm's: the provider answers what was escalated.
    """
    tp = sum(1 for r in pool if r["confidence"] < threshold and not r["localRight"])
    fp = sum(1 for r in pool if r["confidence"] < threshold and r["localRight"])
    fn = sum(1 for r in pool if r["confidence"] >= threshold and not r["localRight"])
    tn = sum(1 for r in pool if r["confidence"] >= threshold and r["localRight"])
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None

    def f(beta: float) -> float | None:
        if not precision or not recall:
            return None
        b2 = beta * beta
        return (1 + b2) * precision * recall / (b2 * precision + recall)

    right = sum(1 for r in pool
                if (r["apiRight"] if r["confidence"] < threshold else r["localRight"]))
    return {
        "threshold": round(threshold, 2),
        "n": len(pool),
        "accuracy": round(100 * right / len(pool), 2),
        "escalatedShare": round(100 * (tp + fp) / len(pool), 2),
        "precision": None if precision is None else round(precision, 4),
        "recall": None if recall is None else round(recall, 4),
        "f1": None if f(1) is None else round(f(1), 4),
        "f2": None if f(2) is None else round(f(2), 4),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }


def thresholds() -> list[float]:
    return [i / 100 for i in range(0, 101)]


def write(name: str, payload: dict) -> None:
    (HERE / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"  wrote {name}")


def require(name: str) -> dict:
    path = HERE / name
    if not path.exists():
        raise SystemExit(f"stage refused: {name} does not exist yet; run the earlier stage first")
    return json.loads(path.read_text())


def stage1() -> None:
    """Does composing the two arms at 0.6 reproduce the arm that was measured at 0.6?"""
    print("== stage 1: validate the simulator against the measured gated arm")
    out = {"shippedThreshold": SHIPPED, "datasets": {}}
    for dataset in DATASETS:
        pool = items(dataset)
        simulated = at(SHIPPED, pool)
        gated = rows("gated0-6", dataset)
        measured_right = sum(1 for r in gated.values() if r["answer"] == r["gold"])
        measured = {
            "accuracy": round(100 * measured_right / len(gated), 2),
            "escalatedShare": round(
                100 * sum(1 for r in gated.values() if r.get("escalated")) / len(gated), 2),
            "n": len(gated),
        }
        # How far the same item's confidence moved between the two runs. This is the resolution
        # limit on any threshold: a gate set to three decimals is reading noise.
        local = rows("routed", dataset)
        drift = [abs(local[i]["confidence"] - gated[i]["confidence"])
                 for i in sorted(set(local) & set(gated)) if "confidence" in gated[i]]
        crossed = [i for i in sorted(set(local) & set(gated))
                   if "confidence" in gated[i]
                   and (local[i]["confidence"] < SHIPPED) != (gated[i]["confidence"] < SHIPPED)]
        out["datasets"][dataset] = {
            "simulated": simulated,
            "measured": measured,
            "accuracyGap": round(simulated["accuracy"] - measured["accuracy"], 2),
            "escalatedShareGap": round(
                simulated["escalatedShare"] - measured["escalatedShare"], 2),
            "confidenceDrift": {
                "n": len(drift),
                "median": round(statistics.median(drift), 4),
                "p90": round(sorted(drift)[int(0.9 * (len(drift) - 1))], 4),
                "max": round(max(drift), 4),
                "itemsCrossingShippedThreshold": len(crossed),
                "crossed": crossed,
            },
        }
        print(f"  {dataset}: simulated {simulated['accuracy']:.1f} at "
              f"{simulated['escalatedShare']:.0f}% escalated, measured {measured['accuracy']:.1f} "
              f"at {measured['escalatedShare']:.0f}%; {len(crossed)} items changed side of 0.6 "
              f"between runs (median confidence drift {statistics.median(drift):.4f})")

    # The kill criterion: a gap the drift cannot explain means the composition is not the gate.
    for dataset, found in out["datasets"].items():
        crossed = found["confidenceDrift"]["itemsCrossingShippedThreshold"]
        if abs(found["escalatedShareGap"]) > 100 * crossed / found["measured"]["n"] + 1e-9:
            raise SystemExit(
                f"{dataset}: the simulator escalates {found['escalatedShareGap']:+.1f} points "
                f"differently than the measured arm, and only {crossed} items changed side of the "
                "threshold between runs; the composition is not a model of the shipped gate")
    out["verdict"] = ("the composition reproduces the measured arm to within the items whose "
                      "confidence crossed the threshold between runs")
    write("stage1-simulator.json", out)


def stage2() -> None:
    print("== stage 2: sweep every threshold")
    require("stage1-simulator.json")
    out = {"step": 0.01, "datasets": {}}
    for dataset in DATASETS:
        pool = items(dataset)
        sweep = [at(t, pool) for t in thresholds()]
        best_f1 = max((r for r in sweep if r["f1"] is not None), key=lambda r: r["f1"])
        best_acc = max(sweep, key=lambda r: (r["accuracy"], -r["escalatedShare"]))
        out["datasets"][dataset] = {
            "sweep": sweep,
            "shipped": at(SHIPPED, pool),
            "bestF1": best_f1,
            "bestAccuracy": best_acc,
            "localOnly": at(0.0, pool),
            "allEscalated": at(1.01, pool),
        }
        print(f"  {dataset}: best F1 {best_f1['f1']:.3f} at {best_f1['threshold']:.2f}; "
              f"best accuracy {best_acc['accuracy']:.1f} at {best_acc['threshold']:.2f} "
              f"({best_acc['escalatedShare']:.0f}% escalated); shipped 0.60 gives "
              f"{at(SHIPPED, pool)['accuracy']:.1f} at {at(SHIPPED, pool)['escalatedShare']:.0f}%")
    write("stage2-sweep.json", out)


def folds_of(pool: list[dict]) -> list[list[dict]]:
    """Stratified folds on the label the gate predicts: the local arm was wrong."""
    rng = random.Random(SEED)
    wrong = [r for r in pool if not r["localRight"]]
    right = [r for r in pool if r["localRight"]]
    rng.shuffle(wrong)
    rng.shuffle(right)
    folds: list[list[dict]] = [[] for _ in range(FOLDS)]
    for index, row in enumerate(wrong + right):
        folds[index % FOLDS].append(row)
    return folds


def stage3() -> None:
    print("== stage 3: tune by stratified cross-validation")
    require("stage2-sweep.json")
    out = {"folds": FOLDS, "seed": SEED, "minPrecision": MIN_PRECISION,
           "minRecall": MIN_RECALL, "datasets": {}}
    for dataset in DATASETS:
        pool = items(dataset)
        folds = folds_of(pool)
        rounds = []
        for index in range(FOLDS):
            held = folds[index]
            train = [r for j, f in enumerate(folds) if j != index for r in f]
            scored = [at(t, train) for t in thresholds()]
            feasible = [r for r in scored
                        if r["precision"] is not None and r["recall"] is not None
                        and r["precision"] >= MIN_PRECISION and r["recall"] >= MIN_RECALL]
            if feasible:
                chosen = max(feasible, key=lambda r: (r["f1"], -r["escalatedShare"]))
                basis = "F1 subject to both constraints"
            else:
                usable = [r for r in scored if r["f1"] is not None]
                chosen = max(usable, key=lambda r: (r["f1"], -r["escalatedShare"]))
                basis = "F1 alone; no threshold satisfies both constraints on this training split"
            rounds.append({
                "fold": index,
                "selected": chosen["threshold"],
                "basis": basis,
                "train": chosen,
                "heldOut": at(chosen["threshold"], held),
                "heldOutAtShipped": at(SHIPPED, held),
            })
        selected = [r["selected"] for r in rounds]
        tuned_acc = [r["heldOut"]["accuracy"] for r in rounds]
        shipped_acc = [r["heldOutAtShipped"]["accuracy"] for r in rounds]
        tuned_share = [r["heldOut"]["escalatedShare"] for r in rounds]
        shipped_share = [r["heldOutAtShipped"]["escalatedShare"] for r in rounds]
        out["datasets"][dataset] = {
            "rounds": rounds,
            "selectedThresholds": selected,
            "selectedMedian": round(statistics.median(selected), 2),
            "heldOutAccuracy": {
                "tunedMean": round(statistics.fmean(tuned_acc), 2),
                "shippedMean": round(statistics.fmean(shipped_acc), 2),
                "delta": round(statistics.fmean(tuned_acc) - statistics.fmean(shipped_acc), 2),
            },
            "heldOutEscalatedShare": {
                "tunedMean": round(statistics.fmean(tuned_share), 2),
                "shippedMean": round(statistics.fmean(shipped_share), 2),
                "delta": round(statistics.fmean(tuned_share) - statistics.fmean(shipped_share), 2),
            },
            "constraintFeasible": all("subject to both" in r["basis"] for r in rounds),
        }
        found = out["datasets"][dataset]
        print(f"  {dataset}: folds chose {selected} (median {found['selectedMedian']:.2f}); "
              f"held-out accuracy {found['heldOutAccuracy']['tunedMean']:.1f} tuned against "
              f"{found['heldOutAccuracy']['shippedMean']:.1f} at 0.60, escalated share "
              f"{found['heldOutEscalatedShare']['tunedMean']:.0f}% against "
              f"{found['heldOutEscalatedShare']['shippedMean']:.0f}%")
    write("stage3-cv.json", out)


def brier(pool: list[dict], probability) -> float:
    return statistics.fmean((probability(r) - (1.0 if r["localRight"] else 0.0)) ** 2
                            for r in pool)


def platt(train: list[dict]) -> tuple[float, float]:
    """Platt scaling by IRLS on the log-odds of the reported confidence.

    Two parameters, so Newton's method on the log-likelihood converges in a handful of steps and
    needs no library. Probabilities are clipped before the logit, as the post's own recipe says,
    because a reported confidence of exactly 1 has no log-odds.
    """
    eps = 1e-6
    xs = [math.log(min(max(r["confidence"], eps), 1 - eps)
                   / (1 - min(max(r["confidence"], eps), 1 - eps))) for r in train]
    ys = [1.0 if r["localRight"] else 0.0 for r in train]
    a, b = 1.0, 0.0
    for _ in range(100):
        g = [0.0, 0.0]
        h = [[1e-9, 0.0], [0.0, 1e-9]]
        for x, y in zip(xs, ys):
            p = 1 / (1 + math.exp(-(a * x + b)))
            w = max(p * (1 - p), 1e-12)
            g[0] += (y - p) * x
            g[1] += (y - p)
            h[0][0] += w * x * x
            h[0][1] += w * x
            h[1][0] += w * x
            h[1][1] += w
        det = h[0][0] * h[1][1] - h[0][1] * h[1][0]
        if abs(det) < 1e-18:
            break
        da = (h[1][1] * g[0] - h[0][1] * g[1]) / det
        db = (h[0][0] * g[1] - h[1][0] * g[0]) / det
        a, b = a + da, b + db
        if abs(da) + abs(db) < 1e-10:
            break
    return a, b


def apply_platt(a: float, b: float, confidence: float) -> float:
    eps = 1e-6
    c = min(max(confidence, eps), 1 - eps)
    return 1 / (1 + math.exp(-(a * math.log(c / (1 - c)) + b)))


def stage4() -> None:
    print("== stage 4: is the confidence calibrated, and does Platt scaling improve it?")
    require("stage3-cv.json")
    out = {"bins": 10, "folds": FOLDS, "seed": SEED, "datasets": {}}
    for dataset in DATASETS:
        pool = items(dataset)
        bins = []
        ece = 0.0
        for index in range(10):
            low, high = index / 10, (index + 1) / 10
            inside = [r for r in pool
                      if (low <= r["confidence"] < high) or (index == 9 and r["confidence"] == 1.0)]
            if not inside:
                bins.append({"bin": [low, high], "n": 0})
                continue
            predicted = statistics.fmean(r["confidence"] for r in inside)
            observed = statistics.fmean(1.0 if r["localRight"] else 0.0 for r in inside)
            bins.append({"bin": [low, high], "n": len(inside),
                         "meanConfidence": round(predicted, 4),
                         "observedAccuracy": round(observed, 4),
                         "gap": round(predicted - observed, 4)})
            ece += len(inside) / len(pool) * abs(predicted - observed)

        folds = folds_of(pool)
        before, after, fits = [], [], []
        # Per-item squared errors, each from the fold that did not fit the scaling, so the paired
        # bootstrap below never scores an item against a curve that saw it.
        paired: list[tuple[float, float]] = []
        shipped_calibrated = []
        for index in range(FOLDS):
            held = folds[index]
            train = [r for j, f in enumerate(folds) if j != index for r in f]
            a, b = platt(train)
            fits.append({"fold": index, "a": round(a, 4), "b": round(b, 4),
                         # What the shipped threshold means once the score is calibrated: the
                         # probability of being right below which this gate escalates.
                         "shippedThresholdCalibrated": round(apply_platt(a, b, SHIPPED), 4)})
            shipped_calibrated.append(apply_platt(a, b, SHIPPED))
            before.append(brier(held, lambda r: r["confidence"]))
            after.append(brier(held, lambda r, a=a, b=b: apply_platt(a, b, r["confidence"])))
            for row in held:
                y = 1.0 if row["localRight"] else 0.0
                paired.append(((row["confidence"] - y) ** 2,
                               (apply_platt(a, b, row["confidence"]) - y) ** 2))
        rng = random.Random(SEED)
        deltas = []
        for _ in range(2000):
            sample = [paired[rng.randrange(len(paired))] for _ in range(len(paired))]
            deltas.append(statistics.fmean(y - x for x, y in sample))
        deltas.sort()
        ci = [round(deltas[int(0.025 * len(deltas))], 4),
              round(deltas[int(0.975 * len(deltas))], 4)]
        out["datasets"][dataset] = {
            "reliability": bins,
            "expectedCalibrationError": round(ece, 4),
            "meanConfidence": round(statistics.fmean(r["confidence"] for r in pool), 4),
            "observedAccuracy": round(
                statistics.fmean(1.0 if r["localRight"] else 0.0 for r in pool), 4),
            "brier": {
                "reported": round(statistics.fmean(before), 4),
                "plattScaled": round(statistics.fmean(after), 4),
                "delta": round(statistics.fmean(after) - statistics.fmean(before), 4),
                "foldsImproved": sum(1 for x, y in zip(before, after) if y < x),
                # Paired bootstrap over out-of-fold items, 2000 resamples: negative is better.
                "deltaCi95": ci,
            },
            "plattFits": fits,
            "shippedThresholdCalibratedMean": round(statistics.fmean(shipped_calibrated), 4),
        }
        found = out["datasets"][dataset]
        print(f"  {dataset}: mean confidence {found['meanConfidence']:.3f} against observed "
              f"accuracy {found['observedAccuracy']:.3f} (ECE {found['expectedCalibrationError']:.3f}); "
              f"held-out Brier {found['brier']['reported']:.4f} reported, "
              f"{found['brier']['plattScaled']:.4f} Platt-scaled, improved on "
              f"{found['brier']['foldsImproved']} of {FOLDS} folds")
    write("stage4-calibration.json", out)


STAGES = {"stage1": stage1, "stage2": stage2, "stage3": stage3, "stage4": stage4}


def main(argv: list[str]) -> int:
    which = argv[1] if len(argv) > 1 else "all"
    if which == "all":
        for stage in STAGES.values():
            stage()
        return 0
    if which not in STAGES:
        raise SystemExit(f"unknown stage {which!r}; one of {', '.join(STAGES)} or all")
    STAGES[which]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
