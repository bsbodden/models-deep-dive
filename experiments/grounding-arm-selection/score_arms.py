#!/usr/bin/env python3
"""Score the candidate grounding arms against the frontier arm measured in the same run.

The measuring stick is imported, not copied: `normalise`, `abstained`, `score_qa`,
`paired_interval` and `verdict` all come from ../routing-accuracy/score.py, so an arm that wins
here wins under exactly the code that failed the 1B arm. The thresholds live there too
(ACCEPT_WITHIN, REJECT_BEYOND) and are printed with the verdict rather than restated.

Reads every results-<arm>-<dataset>.jsonl present and reports what it finds; a missing arm is
"not run", never an omission that flatters the arms that did run.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent if len(sys.argv) < 2 else Path(sys.argv[1]).resolve()
SOURCE = Path(__file__).resolve().parent.parent / "routing-accuracy"
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(SOURCE.parent.parent / "tools"))

import measurements  # noqa: E402  the one record shape parity_gate.py reads
import score as stick  # noqa: E402  the frozen scorer, by path

DATASETS = ("squad2", "hotpotqa")
FRONTIER = "frontier"
CONTROL = "llama1b"
HARNESS = Path(__file__).resolve().parent / "arms.java"
# Two arms are not re-measured here, and this is where that decision lives. The frozen experiment
# measured the 1B and gpt-5.1 over the same 100 items with the same prompts, and the 1B returned
# byte-identical answers when this harness re-ran it on another host -- so a re-run would spend an
# hour of a paid host reproducing two files that already exist. The prompt-hash check below is what
# makes the reuse safe: if the imported rows were built from a different prompt, nothing is scored.
IMPORTED = {
    CONTROL: "results-qa-routed-{dataset}.jsonl",
    FRONTIER: "results-qa-api-{dataset}.jsonl",
}
# The frozen experiment's own numbers for the control arm, from ../routing-accuracy/RESULTS.json.
# The README's third kill criterion: the control must land within 5 points of these or the run is
# void and the harness is wrong, not the model.
CONTROL_VOID_MARGIN = 5.0


def read_rows(path: Path) -> dict:
    rows = {}
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def rows_for(arm: str, dataset: str) -> tuple[dict, str] | tuple[None, None]:
    """One arm's rows and the artifact they came from, merging item windows if that is how they
    were measured.

    A sample too large for one supervised run is measured in windows -- `results-<arm>-<dataset>
    .from50.jsonl` -- and two windows are two hosts and two weight loads. Merging them silently
    would hide a drift between the two, so an item measured twice has to agree, exactly, or
    nothing is scored.
    """
    whole = HERE / f"results-{arm}-{dataset}.jsonl"
    windows = sorted(HERE.glob(f"results-{arm}-{dataset}.from*.jsonl"))
    if not whole.exists() and not windows:
        imported = IMPORTED.get(arm)
        if imported:
            path = SOURCE / imported.format(dataset=dataset)
            return (read_rows(path), f"../routing-accuracy/{path.name}") if path.exists() \
                else (None, None)
        return None, None
    rows, artifacts = {}, []
    for path in ([whole] if whole.exists() else []) + windows:
        artifacts.append(path.name)
        for item_id, row in read_rows(path).items():
            previous = rows.get(item_id)
            if previous is not None and (previous["answer"] != row["answer"]
                                         or previous["promptSha256"] != row["promptSha256"]):
                raise SystemExit(
                    f"{arm}/{dataset}: item {item_id} was measured twice and the windows "
                    f"disagree; {artifacts} cannot be merged")
            rows[item_id] = row
    return (rows or None), " + ".join(artifacts)


def frozen_control() -> dict:
    frozen = json.loads((SOURCE / "RESULTS.json").read_text())
    out = {}
    for dataset in DATASETS:
        stage = frozen.get("stages", {}).get(f"qa/{dataset}")
        if stage:
            out[dataset] = stage["routed"]
    return out


def describe(arm: str, rows: dict, gold: dict) -> dict:
    scored = stick.score_qa(rows, gold)
    out = {
        "n": scored["n"],
        "exactMatch": round(scored["exactMatch"], 2),
        "tokenF1": round(scored["tokenF1"], 2),
        "medianMillis": round(statistics.median(r["millis"] for r in rows.values()), 1),
        # The imported arms were collected by a harness that did not record heap, so this is
        # absent rather than zero: an arm whose memory nobody measured must not look frugal.
        "maxHeapMiB": max((r["heapMiB"] for r in rows.values() if "heapMiB" in r), default=None),
        "local": all(r.get("local") for r in rows.values()),
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
    report = {"resamples": stick.RESAMPLES, "seed": stick.SEED,
              "acceptWithin": stick.ACCEPT_WITHIN, "rejectBeyond": stick.REJECT_BEYOND,
              "scorer": "../routing-accuracy/score.py", "datasets": {}}
    lines, void, records = [], [], []
    frozen = frozen_control()
    coordinates = measurements.coordinates_from_harness(HARNESS)

    for dataset in DATASETS:
        gold = {i["id"]: i for i in json.loads((SOURCE / f"sample-{dataset}.json").read_text())}
        present, artifacts = {}, {}
        # Every arm the harness can run, plus the two imported ones, rather than whatever files
        # happen to be here: an arm that was configured and produced nothing is a gap to report,
        # not an arm to leave out of the table.
        for arm in sorted(set(coordinates) | set(IMPORTED)):
            rows, artifact = rows_for(arm, dataset)
            if rows:
                present[arm] = rows
                artifacts[arm] = artifact
        if not present:
            lines.append(f"{dataset}: no arms run")
            continue

        shared = set.intersection(*(set(r) for r in present.values()))
        present = {arm: {k: v for k, v in rows.items() if k in shared}
                   for arm, rows in present.items()}

        # Byte-identical prompts across arms, or the comparison is between two questions.
        reference = next(iter(present.values()))
        for arm, rows in present.items():
            drift = [k for k in shared if rows[k]["promptSha256"] != reference[k]["promptSha256"]]
            if drift:
                raise SystemExit(f"{dataset}: {arm} differs from the other arms on "
                                 f"{len(drift)} of {len(shared)} prompts")

        arms = {arm: describe(arm, rows, gold) for arm, rows in present.items()}

        if CONTROL in arms and dataset in frozen:
            drifted = arms[CONTROL]["exactMatch"] - frozen[dataset]
            arms[CONTROL]["frozenExactMatch"] = frozen[dataset]
            arms[CONTROL]["driftFromFrozen"] = round(drifted, 2)
            if abs(drifted) > CONTROL_VOID_MARGIN:
                void.append(f"{dataset}: control arm moved {drifted:+.1f} points from the frozen "
                            f"{frozen[dataset]:.1f}; run is VOID for this dataset")

        reference_arm = arms.get(FRONTIER)
        for arm, summary in arms.items():
            if arm == FRONTIER or reference_arm is None:
                continue
            delta = summary["exactMatch"] - reference_arm["exactMatch"]
            low, high = stick.paired_interval(summary, reference_arm)
            summary["deltaExactMatch"] = round(delta, 2)
            summary["interval95"] = [round(low, 2), round(high, 2)]
            summary["verdict"] = stick.verdict(delta, low, high)

        # Who is first among the local arms, and by how much. The fleet's grounded prompts are
        # LOCAL_ONLY, so this ordering -- not the distance to a model the router may not pick for
        # them -- is what a declaration under that boundary rests on. The distance to gpt-5.1 is
        # recorded too, in the same record, because a boundary is a cost and the cost is the gap.
        locals_ = {arm: summary for arm, summary in arms.items() if arm != FRONTIER}
        best_local = max(locals_, key=lambda arm: locals_[arm]["exactMatch"]) if locals_ else None
        # A tie is a tie. max() returns whichever arm it saw first, and on HotpotQA the two local
        # arms score exactly the same, so naming one of them "first" would be an artifact of
        # dictionary order appearing in a sentence.
        tied = (sorted(arm for arm in locals_
                       if locals_[arm]["exactMatch"] == locals_[best_local]["exactMatch"])
                if best_local else [])
        if best_local:
            report.setdefault("bestLocal", {})[dataset] = tied
            for arm, summary in locals_.items():
                behind = locals_[best_local]["exactMatch"] - summary["exactMatch"]
                summary["behindBestLocal"] = round(behind, 2)
                summary["carriesDeclaration"] = behind <= stick.ACCEPT_WITHIN

        if FRONTIER in arms:
            reference_record = {"arm": FRONTIER, "catalogIds": ["gpt-5.1"],
                                "value": arms[FRONTIER]["exactMatch"]}
            for arm, summary in arms.items():
                if arm == FRONTIER:
                    continue
                records.append(measurements.record(
                    experiment="grounding-arm-selection",
                    capability_dataset=f"qa/{dataset}", arm=arm,
                    coordinate=coordinates.get(arm), metric="exactMatch",
                    value=summary["exactMatch"], n=summary["n"], artifact=artifacts[arm],
                    reference=reference_record, delta=summary.get("deltaExactMatch"),
                    ci95=summary.get("interval95"),
                    extra={"tokenF1": summary["tokenF1"],
                           "medianMillis": summary["medianMillis"],
                           "maxHeapMiB": summary["maxHeapMiB"],
                           "verdict": summary.get("verdict"),
                           "abstained": summary.get("answerable", {}).get("abstained", 0)
                           + summary.get("unanswerable", {}).get("abstained", 0),
                           "carriesDeclaration": summary.get("carriesDeclaration"),
                           "bestLocal": {
                               "arm": best_local,
                               "arms": tied,
                               "value": locals_[best_local]["exactMatch"] if best_local else None,
                               "behind": summary.get("behindBestLocal")}}))

        for summary in arms.values():
            summary.pop("perItem", None)
        report["datasets"][dataset] = {"n": len(shared), "arms": arms,
                                       "artifacts": artifacts}

        for arm in sorted(arms):
            s = arms[arm]
            head = (f"{dataset}/{arm}: n={s['n']} EM {s['exactMatch']:.1f} "
                    f"F1 {s['tokenF1']:.1f} median {s['medianMillis']:.0f} ms "
                    f"heap {s['maxHeapMiB'] or '-'} MiB")
            if "deltaExactMatch" in s:
                head += (f" | {s['deltaExactMatch']:+.1f} vs {FRONTIER} "
                         f"[{s['interval95'][0]:+.1f}, {s['interval95'][1]:+.1f}] "
                         f"{s['verdict']}")
            if "behindBestLocal" in s:
                head += (" | first among local arms" if s["behindBestLocal"] == 0
                         else f" | {s['behindBestLocal']:.1f} behind {best_local}")
            lines.append(head)
            for name in ("answerable", "unanswerable"):
                if name in s:
                    p = s[name]
                    lines.append(f"    {name}: n={p['n']} EM {p['exactMatch']:.1f} "
                                 f"abstained {p['abstained']}")

    # Per-dataset verdicts combine under the README's rule: adopt only if every dataset accepts.
    for arm in sorted({a for d in report["datasets"].values() for a in d["arms"]} - {FRONTIER}):
        calls = [d["arms"][arm].get("verdict") for d in report["datasets"].values()
                 if arm in d["arms"] and "verdict" in d["arms"][arm]]
        if not calls or len(calls) < len(report["datasets"]):
            overall = "INCOMPLETE"
        elif all(c == "ACCEPT" for c in calls):
            overall = "ADOPT"
        elif any(c == "REJECT" for c in calls):
            overall = "REJECT"
        else:
            overall = "INCONCLUSIVE"
        report.setdefault("overall", {})[arm] = {"perDataset": calls, "call": overall}
        lines.append(f"overall/{arm}: {' + '.join(calls) or 'no datasets'} -> {overall}")

    if void:
        report["void"] = void
        lines.extend(void)

    (HERE / "RESULTS.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    written = measurements.write(HERE, records)
    print("\n".join(lines))
    print(f"\nwrote {HERE / 'RESULTS.json'} and {written.name} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
