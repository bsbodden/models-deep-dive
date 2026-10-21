#!/usr/bin/env python3
"""Score a rubric arm on the held-out hundred, in aggregate, and nothing else.

Deliberately narrow. It prints label accuracy, the median confidence where the arm was right
against where it was wrong, and the share of items a 0.6 gate would escalate -- the three numbers
README.md's decision rule is written against. It does **not** print per-item errors or a confusion
table for a held-out arm, because the point of the held-out hundred is that nobody has read its
mistakes before the intervention is written. `--confusions` prints them, for after the verdict.

The labels and the scorer come from ../routing-accuracy: same measuring stick as everything else.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "routing-accuracy"
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(HERE.parent.parent / "tools"))

import measurements  # noqa: E402
import score as stick  # noqa: E402

GATE = 0.6  # the threshold fleet.java ships


def rows_for(arm: str, dataset: str) -> dict | None:
    path = HERE / f"results-decide-{arm}-{dataset}-heldout.jsonl"
    if not path.exists():
        return None
    return {json.loads(line)["id"]: json.loads(line)
            for line in path.read_text().splitlines() if line.strip()}


def main() -> int:
    show_confusions = "--confusions" in sys.argv
    manifest = json.loads((SOURCE / "MANIFEST.json").read_text())
    report, records, lines = {}, [], []

    for dataset in ("snips", "trec"):
        gold = {i["id"]: i for i in
                json.loads((HERE / f"sample-{dataset}-heldout.json").read_text())}
        labels = manifest["labelSets"][dataset]
        for arm in sorted({path.name.split("-")[2] for path in
                           HERE.glob(f"results-decide-*-{dataset}-heldout.jsonl")}):
            rows = rows_for(arm, dataset)
            if not rows:
                continue
            scored = stick.score_labels(rows, gold, labels)
            right = [rows[k]["confidence"] for k, (hit, _) in scored["perItem"].items()
                     if hit == 1.0 and "confidence" in rows[k]]
            wrong = [rows[k]["confidence"] for k, (hit, _) in scored["perItem"].items()
                     if hit == 0.0 and "confidence" in rows[k]]
            below = sum(1 for row in rows.values() if row.get("confidence", 1.0) < GATE)
            summary = {
                "n": scored["n"],
                "accuracy": round(scored["accuracy"], 2),
                "unparseable": scored["unparseable"],
                "medianConfidenceRight": round(statistics.median(right), 3) if right else None,
                "medianConfidenceWrong": round(statistics.median(wrong), 3) if wrong else None,
                "wouldEscalateAt06": round(100 * below / len(rows), 1),
            }
            report.setdefault(dataset, {})[arm] = summary
            lines.append(
                f"{dataset}-heldout/{arm}: n={summary['n']} accuracy {summary['accuracy']:.1f}"
                f", confidence {summary['medianConfidenceRight']} right against "
                f"{summary['medianConfidenceWrong']} wrong, {summary['wouldEscalateAt06']:.0f}% "
                f"below the {GATE} gate")
            records.append(measurements.record(
                experiment="decision-rubric-tuning",
                capability_dataset=f"decide/{dataset}-heldout", arm=arm, coordinate=None,
                metric="accuracy", value=summary["accuracy"], n=summary["n"],
                artifact=f"results-decide-{arm}-{dataset}-heldout.jsonl",
                extra={"catalogIds": sorted({row["selected"] for row in rows.values()
                                             if row.get("selected")}),
                       "medianConfidenceRight": summary["medianConfidenceRight"],
                       "medianConfidenceWrong": summary["medianConfidenceWrong"],
                       "wouldEscalateAt06": summary["wouldEscalateAt06"]}))
            if show_confusions:
                confusions = Counter(
                    (gold[k]["label"], rows[k]["answer"].strip())
                    for k, (hit, _) in scored["perItem"].items() if hit == 0.0)
                for (want, got), count in confusions.most_common():
                    lines.append(f"    {want} read as {got}: {count}")

        measured = SOURCE / f"results-decide-routed-{dataset}.jsonl"
        if measured.exists() and "routed" in report.get(dataset, {}):
            development = stick.score_labels(
                {json.loads(line)["id"]: json.loads(line)
                 for line in measured.read_text().splitlines() if line.strip()},
                {i["id"]: i for i in json.loads((SOURCE / f"sample-{dataset}.json").read_text())},
                labels)
            gap = report[dataset]["routed"]["accuracy"] - development["accuracy"]
            report[dataset]["developmentAccuracy"] = round(development["accuracy"], 2)
            report[dataset]["heldOutMinusDevelopment"] = round(gap, 2)
            lines.append(
                f"    baseline on the development hundred: {development['accuracy']:.1f}; "
                f"held-out minus development {gap:+.1f}"
                + ("  -- beyond the 8-point kill criterion, the samples are not interchangeable"
                   if abs(gap) > 8 else ""))

    (HERE / "RESULTS.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    written = measurements.write(HERE, records)
    print("\n".join(lines))
    print(f"\nwrote {HERE / 'RESULTS.json'} and {written.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
