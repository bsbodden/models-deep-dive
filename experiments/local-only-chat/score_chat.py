#!/usr/bin/env python3
"""Score the local-only chat arms, and print the two verdicts README.md fixed before the run.

The measuring stick is imported, not copied: `score_qa`, `abstained`, `paired_interval` and
`verdict` come from ../routing-accuracy/score.py, the same code that failed this fleet's grounding
and decision declarations.

Headline is token F1, per README.md, because free-form dialogue answers are not spans. Exact match
is printed beside it and recorded, and the per-dataset answerable/unanswerable split is printed
because "worse at reading" and "never declines" are different faults with different fixes.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "routing-accuracy"
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(HERE.parent.parent / "tools"))

import measurements  # noqa: E402  the one record shape parity_gate.py reads
import score as stick  # noqa: E402  the frozen scorer, by path

HARNESS = HERE / "chat.java"

DATASETS = ("coqa", "quac")
FRONTIER = "frontier"
DECLARED_TODAY = "small"
HEADLINE = "tokenF1"
# README.md: an arm more than this many points of token F1 behind the best local arm does not carry
# the declaration. Same number as the gate's frontier margin, applied to a different reference.
LOCAL_MARGIN = 2.0


def rows_for(arm: str, dataset: str) -> dict | None:
    path = HERE / f"results-{arm}-{dataset}.jsonl"
    if not path.exists():
        return None
    rows = {}
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows or None


def describe(rows: dict, gold: dict) -> dict:
    scored = stick.score_qa(rows, gold)
    out = {
        "n": scored["n"],
        "exactMatch": round(scored["exactMatch"], 2),
        "tokenF1": round(scored["tokenF1"], 2),
        "medianMillis": round(statistics.median(r["millis"] for r in rows.values()), 1),
        "maxHeapMiB": max(r["heapMiB"] for r in rows.values()),
        "abstained": sum(1 for r in rows.values() if stick.abstained(r["answer"])),
        "perItem": scored["perItem"],
    }
    for kind, name in ((False, "answerable"), (True, "unanswerable")):
        subset = {k: v for k, v in rows.items() if gold[k]["unanswerable"] == kind}
        if not subset:
            continue
        part = stick.score_qa(subset, gold)
        out[name] = {
            "n": part["n"],
            "exactMatch": round(part["exactMatch"], 2),
            "tokenF1": round(part["tokenF1"], 2),
            "abstained": sum(1 for r in subset.values() if stick.abstained(r["answer"])),
        }
    return out


def main() -> int:
    report = {"resamples": stick.RESAMPLES, "seed": stick.SEED, "headline": HEADLINE,
              "localMargin": LOCAL_MARGIN, "scorer": "../routing-accuracy/score.py",
              "datasets": {}}
    lines, records = [], []
    coordinates = measurements.coordinates_from_harness(HARNESS)

    for dataset in DATASETS:
        sample = HERE / f"sample-{dataset}.json"
        gold = {i["id"]: i for i in json.loads(sample.read_text())}
        present = {}
        for path in sorted(HERE.glob(f"results-*-{dataset}.jsonl")):
            arm = path.name[len("results-"):-len(f"-{dataset}.jsonl")]
            rows = rows_for(arm, dataset)
            if rows:
                present[arm] = rows
        if not present:
            lines.append(f"{dataset}: no arms run")
            continue

        shared = set.intersection(*(set(r) for r in present.values()))
        present = {arm: {k: v for k, v in rows.items() if k in shared}
                   for arm, rows in present.items()}
        reference = next(iter(present.values()))
        for arm, rows in present.items():
            drift = [k for k in shared if rows[k]["promptSha256"] != reference[k]["promptSha256"]]
            if drift:
                raise SystemExit(f"{dataset}: {arm} differs from the other arms on "
                                 f"{len(drift)} of {len(shared)} prompts")

        arms = {arm: describe(rows, gold) for arm, rows in present.items()}
        locals_ = {arm: s for arm, s in arms.items() if arm != FRONTIER}

        # Verdict 1: the ceiling gap, against the frontier model the LOCAL_ONLY boundary forbids.
        if FRONTIER in arms:
            for arm, summary in locals_.items():
                delta = summary[HEADLINE] - arms[FRONTIER][HEADLINE]
                low, high = stick.paired_interval(summary, arms[FRONTIER], key=1)
                summary["ceilingGap"] = round(delta, 2)
                summary["ceilingInterval95"] = [round(low, 2), round(high, 2)]
                summary["ceilingVerdict"] = stick.verdict(delta, low, high)

        # Verdict 2: the declaration, against the best measured local arm.
        if locals_:
            best = max(locals_, key=lambda arm: locals_[arm][HEADLINE])
            # Every arm that shares the top score, not whichever one max() happened to see first:
            # two arms tied exactly in the neighbouring experiment, and calling one of them first
            # would have put dictionary order into a sentence.
            tied = sorted(arm for arm in locals_
                          if locals_[arm][HEADLINE] == locals_[best][HEADLINE])
            report.setdefault("bestLocal", {})[dataset] = tied
            for arm, summary in locals_.items():
                behind = locals_[best][HEADLINE] - summary[HEADLINE]
                summary["behindBestLocal"] = round(behind, 2)
                summary["carriesDeclaration"] = behind <= LOCAL_MARGIN

        if FRONTIER in arms:
            reference_record = {"arm": FRONTIER, "catalogIds": ["gpt-5.1"],
                                "value": arms[FRONTIER][HEADLINE]}
            # The report's entry is the list of tied arms; the record wants the single arm whose
            # score defines the top, which is `best`. Reading the list back into a dict lookup is
            # what broke the first run of this scorer after ties were introduced.
            tied_arms = report.get("bestLocal", {}).get(dataset, [])
            for arm, summary in locals_.items():
                records.append(measurements.record(
                    experiment="local-only-chat", capability_dataset=f"chat/{dataset}",
                    arm=arm, coordinate=coordinates.get(arm), metric=HEADLINE,
                    value=summary[HEADLINE], n=summary["n"],
                    artifact=f"results-{arm}-{dataset}.jsonl",
                    reference=reference_record, delta=summary.get("ceilingGap"),
                    ci95=summary.get("ceilingInterval95"),
                    extra={"exactMatch": summary["exactMatch"],
                           "medianMillis": summary["medianMillis"],
                           "maxHeapMiB": summary["maxHeapMiB"],
                           "abstained": summary["abstained"],
                           "bestLocal": {"arm": best,
                                         "arms": tied_arms,
                                         "value": locals_[best][HEADLINE],
                                         "behind": summary.get("behindBestLocal")},
                           "carriesDeclaration": summary.get("carriesDeclaration")}))

        for summary in arms.values():
            summary.pop("perItem", None)
        report["datasets"][dataset] = {"n": len(shared), "bestLocal": report.get(
            "bestLocal", {}).get(dataset), "arms": arms}

        for arm in sorted(arms):
            s = arms[arm]
            head = (f"{dataset}/{arm}: n={s['n']} F1 {s['tokenF1']:.1f} EM {s['exactMatch']:.1f} "
                    f"abstained {s['abstained']} median {s['medianMillis']:.0f} ms "
                    f"heap {s['maxHeapMiB']} MiB")
            if "ceilingGap" in s:
                head += (f" | ceiling {s['ceilingGap']:+.1f} "
                         f"[{s['ceilingInterval95'][0]:+.1f}, {s['ceilingInterval95'][1]:+.1f}]")
            if "behindBestLocal" in s:
                head += (f" | {s['behindBestLocal']:.1f} behind best local -> "
                         f"{'carries' if s['carriesDeclaration'] else 'loses'} the declaration")
            lines.append(head)
            for name in ("answerable", "unanswerable"):
                if name in s:
                    p = s[name]
                    lines.append(f"    {name}: n={p['n']} F1 {p['tokenF1']:.1f} "
                                 f"abstained {p['abstained']}")

    # The declaration moves only if both datasets agree on who carries it.
    carriers = {}
    for dataset, block in report["datasets"].items():
        carriers[dataset] = sorted(
            arm for arm, s in block["arms"].items() if s.get("carriesDeclaration"))
    if len(carriers) == len(DATASETS) and all(carriers.values()):
        agreed = sorted(set.intersection(*(set(v) for v in carriers.values())))
        report["declaration"] = {
            "perDataset": carriers,
            "agreed": agreed,
            "declaredToday": DECLARED_TODAY,
            "call": ("keep" if DECLARED_TODAY in agreed
                     else ("move to " + agreed[0] if agreed else "no arm carries it on both")),
        }
        lines.append(f"declaration: both datasets -> {agreed or 'nobody'}; "
                     f"today's arm is {DECLARED_TODAY} -> {report['declaration']['call']}")
    else:
        report["declaration"] = {"perDataset": carriers, "call": "INCOMPLETE"}
        lines.append("declaration: INCOMPLETE, not every dataset has been measured")

    (HERE / "RESULTS.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    written = measurements.write(HERE, records)
    print("\n".join(lines))
    print(f"\nwrote {HERE / 'RESULTS.json'} and {written.name} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
