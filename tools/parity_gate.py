#!/usr/bin/env python3
"""Fail when the fleet declares a capability its measurements do not support.

The rule, stated by the person who owns this code: for the tasks a small model is supposed to
succeed at, it must be close to or better than the frontier model. This turns that into a check
rather than a hope.

A capability declaration in `code/fleet.java` is an application saying "this model may serve this
work". Nothing verified those claims until the accuracy experiments ran, and what they found was a
gap of 16 to 35 points against gpt-5.1 on four public datasets. So every declared (arm, capability)
pair has to name the evidence it rests on, in `PARITY-BASIS.json`, and this gate checks the
evidence rather than the claim.

There are three kinds of basis, and no fourth:

* **frontier** -- the fleet may send this work to gpt-5.1, so the declaration is kept only while
  the measured arm is within the margin of gpt-5.1 on every dataset that speaks for the capability.
* **best-local** -- the fleet's requirement for this capability sets `LOCAL_ONLY`, so gpt-5.1 is
  not a candidate the router is allowed to pick and the alternative is a different local model or
  no service. The declaration goes to the local arm the measurement puts first, and the gap to
  gpt-5.1 is still measured and still printed, because a boundary is a cost and a reader is
  entitled to its size. The gate refuses this basis for a capability whose fleet requirement does
  not actually set the boundary, which it reads from `fleet.java` rather than from the basis file.
* **latency-only** -- the work has no accuracy axis at all, which is true of exactly one thing
  here: a liveness check, whose only correct answer is a few tokens saying the session is alive.
  The gate refuses this basis for any capability a public dataset in these experiments scores, and
  requires the latency evidence it names to exist.

There is no "waived". A declaration either names evidence this gate can check or it is a violation.

Exit code is the number of violations, so CI fails on it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import measurements  # noqa: E402

EXPERIMENTS = ROOT / "experiments"
BASIS = ROOT / "PARITY-BASIS.json"
MARGIN = 2.0  # points behind the frontier reference, from the experiments' own decision rule

# Which measured dataset speaks for which declared capability. A dataset measures a task; it does
# not measure a capability name this application invented, so the mapping is written down rather
# than guessed from a string match.
SPEAKS_FOR = {
    "grounding": ("qa/squad2", "qa/hotpotqa"),
    # A narrower claim, mapped to the dataset that measures it and nothing else. SQuAD v2 is one
    # short passage with half its questions unanswerable, which is the shape this fleet's retrieval
    # produces -- three one-sentence notes, top two retrieved. HotpotQA is ten paragraphs and a
    # two-hop join, which it never produces, and which no local arm in this catalog comes within 23
    # points of the frontier model on. Both entries exist on purpose: a fleet that declares
    # `grounding` is still held to both datasets, and one that declares the narrow name is making a
    # narrower claim and says so in the name rather than in a footnote.
    "grounding-single-passage": ("qa/squad2",),
    "decision": ("decide/snips", "decide/trec"),
    "chat": ("chat/coqa", "chat/quac"),
}


def fleet_source() -> str:
    return (ROOT / "code/fleet.java").read_text()


def declared_capabilities() -> dict[str, set[str]]:
    """Each local arm's declared capabilities, read from the demo rather than restated here."""
    source = fleet_source()
    # The endregion that follows the marker, not the first one in the file: there are earlier
    # regions, so slicing to the first match returned an empty string and this gate passed while
    # measuring nothing at all. A parser that finds nothing must say so rather than agree.
    start = source.index("// region: locals")
    region = source[start : source.index("// endregion", start)]
    arms: dict[str, set[str]] = {}
    for match in re.finditer(
        r"var (\w+) =\s*discovered\(catalog, (\w+)\)(.*?)\.build\(\);", region, re.S
    ):
        arm, body = match.group(1), match.group(3)
        declared = set()
        for call in re.finditer(r"\.(?:add)?[Cc]apabilities\(([^)]*)\)", body):
            declared.update(re.findall(r'"([^"]+)"', call.group(1)))
        if declared:
            arms[arm] = declared
    if not arms:
        raise SystemExit(
            "parity gate found no capability declarations in code/fleet.java's locals region; "
            "the parser is broken and a gate that measures nothing must fail, not pass")
    return arms


def declared_quality() -> dict[str, dict[str, float]]:
    """Each arm's declared quality numbers, as `fleet.java` writes them.

    This fleet carried four of these as hand-typed guesses, and they measured 16 to 35 points
    optimistic. Deleting them was the first fix; the second is that a number here is now checkable,
    so the gate reads them and refuses any that an experiment's measurement does not support.
    """
    source = fleet_source()
    start = source.index("// region: locals")
    region = source[start : source.index("// endregion", start)]
    declared: dict[str, dict[str, float]] = {}
    for match in re.finditer(
        r"var (\w+) =\s*discovered\(catalog, \w+\)(.*?)\.build\(\);", region, re.S
    ):
        arm, body = match.group(1), match.group(2)
        for call in re.finditer(r"\.quality\(([^;]*?)\)\s*(?:\.|$)", body, re.S):
            for task, value in re.findall(r'"([^"]+)"\s*,\s*([0-9.]+)', call.group(1)):
                declared.setdefault(arm, {})[task] = float(value)
    return declared


def fleet_model_ids() -> dict[str, str]:
    """Each arm's catalog id, as `fleet.java` declares it: `var small = discovered(catalog,
    SMALL_ID)` plus `static final String SMALL_ID = "qwen3_0_6b_q4_0"`."""
    source = fleet_source()
    constants = dict(re.findall(r'static final String (\w+_ID)\s*=\s*"([^"]+)"', source))
    start = source.index("// region: locals")
    region = source[start : source.index("// endregion", start)]
    ids = {}
    for arm, constant in re.findall(r"var (\w+) =\s*discovered\(catalog, (\w+)\)", region):
        if constant not in constants:
            raise SystemExit(f"fleet.java's {arm} arm uses {constant}, which this gate could not "
                             "find as a string constant; the parser is broken")
        ids[arm] = constants[constant]
    return ids


def local_only_capabilities() -> set[str]:
    """The capabilities whose fleet requirement sets a local-only data boundary.

    Read from the requirements region of `fleet.java`, because "this work may not leave the
    machine" is the fact that decides whether a frontier comparison is the right one, and a basis
    file claiming it would be a claim about code that the code should be asked about instead.
    """
    source = fleet_source()
    start = source.index("// region: requirements")
    region = source[start : source.index("// endregion", start)]
    found = set()
    for match in re.finditer(
            r"var \w+ =\s*(?:RoutingRequirements\.builder\(\))(.*?)\.build\(\);", region, re.S):
        body = match.group(1)
        if "RoutingDataBoundary.LOCAL_ONLY" in body:
            found.update(re.findall(r'requireCapability\("([^"]+)"\)', body))
    return found


def escalation_default() -> float | None:
    """The confidence below which the shipped fleet escalates a decision, or None if it does not.

    The gate reads it because a declaration measured with the gate on is a claim about a fleet
    that ships with the gate on. A fleet whose default is zero has not been measured by an arm
    whose default was 0.6.
    """
    match = re.search(
        r'System\.getProperty\("fleet\.decisions\.escalateBelowConfidence",\s*"([0-9.]+)"\)',
        fleet_source())
    if not match:
        return None
    value = float(match.group(1))
    return value or None


def identity_ok(entry: dict, fleet_id: str, record: dict) -> tuple[bool, str]:
    """Whether the measured arm is the model the fleet declares, and the line to print about it."""
    catalog_ids = record.get("catalogIds") or []
    if fleet_id in catalog_ids:
        return True, f"{fleet_id} measured directly"
    coordinate = record.get("coordinate")
    if coordinate and measurements.same_weights(fleet_id, coordinate):
        return True, f"{fleet_id} = {coordinate.split(':')[1]}"
    stated = entry.get("identity")
    if stated:
        return True, f"{fleet_id} via {record['arm']}: {stated}"
    return False, (f"{fleet_id} is not among the models that produced {record['arm']}"
                   f" ({catalog_ids or coordinate or 'nothing recorded'})")


def main() -> int:
    if not BASIS.exists():
        print(f"no basis file: {BASIS.relative_to(ROOT)} is missing", file=sys.stderr)
        return 1
    basis = json.loads(BASIS.read_text()).get("declarations", {})
    records = measurements.read_all(EXPERIMENTS)
    if not records:
        print("no measurements: no experiment has written a MEASUREMENTS.json", file=sys.stderr)
        return 1
    fleet_ids = fleet_model_ids()
    boundary = local_only_capabilities()
    escalates_below = escalation_default()

    violations = []
    rows: list[dict] = []
    markdown = "--markdown" in sys.argv
    if not markdown and "--json" not in sys.argv:
        print(f"{'arm':12}{'capability':26}{'dataset':14}{'basis':12}{'value':>7}{'vs':>8}"
              f"{'delta':>7}  verdict")

    def row(arm, capability, dataset, basis_name, value, against, delta, verdict, note="",
            interval=None):
        rows.append({"arm": arm, "capability": capability, "dataset": dataset,
                     "basis": basis_name, "value": value, "against": against, "delta": delta,
                     "verdict": verdict, "note": note, "interval": interval})
        if markdown or "--json" in sys.argv:
            return
        print(f"{arm:12}{capability:26}{dataset:14}{basis_name:12}"
              f"{value:>7}{against:>8}{delta:>7}  {verdict}")
        if note:
            print(f"{'':12}{'':26}{'':14}{'':12}{'':>7}{'':>8}{'':>7}  {note}")

    for arm, capabilities in sorted(declared_capabilities().items()):
        for capability in sorted(capabilities):
            key = f"{arm}/{capability}"
            entry = basis.get(key)
            datasets = SPEAKS_FOR.get(capability, ())
            if not entry:
                row(arm, capability, "-", "-", "-", "-", "-", "NO BASIS RECORDED")
                violations.append(
                    f"{arm} declares {capability} and PARITY-BASIS.json records no basis for it")
                continue
            kind = entry.get("basis")
            measured_by = entry.get("measuredBy", {})
            experiment, measured_arm = measured_by.get("experiment"), measured_by.get("arm")

            if kind == "latency-only":
                if datasets:
                    row(arm, capability, "-", kind, "-", "-", "-", "REFUSED")
                    violations.append(
                        f"{arm} declares {capability} on a latency-only basis, but "
                        f"{', '.join(datasets)} scores it; measure it or drop the declaration")
                    continue
                evidence = ROOT / measured_by.get("evidence", "")
                if not measured_by.get("evidence") or not evidence.exists():
                    row(arm, capability, "-", kind, "-", "-", "-", "EVIDENCE MISSING")
                    violations.append(
                        f"{arm} declares {capability} on a latency-only basis and the latency "
                        f"evidence it names ({measured_by.get('evidence', 'none')}) is not there")
                    continue
                row(arm, capability, "-", kind, "-", "-", "-",
                    f"ok: latency in {measured_by['evidence']}")
                continue

            if kind == "best-local" and capability not in boundary:
                row(arm, capability, "-", kind, "-", "-", "-", "REFUSED")
                violations.append(
                    f"{arm} declares {capability} on a best-local basis, but fleet.java's "
                    f"{capability} requirement does not set RoutingDataBoundary.LOCAL_ONLY, so "
                    "gpt-5.1 is a candidate and the frontier comparison is the one that counts")
                continue

            if kind not in ("frontier", "best-local"):
                row(arm, capability, "-", str(kind), "-", "-", "-", "UNKNOWN BASIS")
                violations.append(f"{arm}/{capability} records basis {kind!r}, which this gate "
                                  "does not know how to check")
                continue

            if not datasets:
                row(arm, capability, "-", kind, "-", "-", "-", "NOTHING MEASURES IT")
                violations.append(
                    f"{arm} declares {capability} and no dataset in these experiments measures it")
                continue

            for dataset in datasets:
                found = [r for r in records
                         if r["capabilityDataset"] == dataset
                         and r["arm"] == measured_arm
                         and (not experiment or r["experiment"] == experiment)]
                if not found:
                    row(arm, capability, dataset, kind, "-", "-", "-", "NOT RUN")
                    violations.append(
                        f"{arm}/{capability}: {dataset} has no measurement of arm "
                        f"{measured_arm!r} in {experiment or 'any experiment'}")
                    continue
                if len(found) > 1:
                    row(arm, capability, dataset, kind, "-", "-", "-", "AMBIGUOUS")
                    violations.append(
                        f"{arm}/{capability}: {dataset} has {len(found)} measurements of arm "
                        f"{measured_arm!r}; the basis file has to name one experiment")
                    continue
                record = found[0]
                ok, identity = identity_ok(entry, fleet_ids[arm], record)
                if not ok:
                    row(arm, capability, dataset, kind, f"{record['value']:.1f}", "-", "-",
                        "WRONG MODEL")
                    violations.append(f"{arm}/{capability} on {dataset}: {identity}")
                    continue

                reference = record.get("reference", {})
                against = reference.get("value")
                delta = record.get("delta")
                if delta is None or against is None:
                    row(arm, capability, dataset, kind, f"{record['value']:.1f}", "-", "-",
                        "NO REFERENCE")
                    violations.append(
                        f"{arm}/{capability} on {dataset}: the measurement records no comparison "
                        "with the frontier reference, so the gap is unknown")
                    continue

                if kind == "frontier":
                    within = delta >= -MARGIN
                    verdict = "ok" if within else "FAIL"
                    if not within:
                        violations.append(
                            f"{arm} declares {capability} but is {abs(delta):.1f} points behind "
                            f"the frontier model on {dataset} (margin {MARGIN})")
                else:
                    carries = record.get("carriesDeclaration")
                    best = (record.get("bestLocal") or {})
                    # "behind" only when it is behind. The first version said "9.0 behind gpt-5.1"
                    # about an arm that was nine points ahead of it.
                    distance = (f"{abs(delta):.1f} behind gpt-5.1" if delta < 0
                                else f"{delta:.1f} ahead of gpt-5.1" if delta > 0
                                else "level with gpt-5.1")
                    verdict = (f"ok: first among local arms, {distance}" if carries else
                               f"FAIL: {best.get('behind')} behind {best.get('arm')}")
                    if not carries:
                        violations.append(
                            f"{arm} declares {capability} but on {dataset} it is "
                            f"{best.get('behind')} points behind {best.get('arm')}, the local arm "
                            "the measurement puts first")

                if record.get("thresholds"):
                    if escalates_below is None:
                        verdict += "; FAIL: measured with escalation, fleet ships without it"
                        violations.append(
                            f"{arm}/{capability} on {dataset} was measured by an arm that "
                            f"escalates below confidence {record['thresholds']}, but fleet.java "
                            "defaults fleet.decisions.escalateBelowConfidence to 0, so the shipped "
                            "fleet is not the thing that was measured")
                    elif [escalates_below] != record["thresholds"]:
                        verdict += (f"; FAIL: measured at {record['thresholds']}, fleet ships "
                                    f"{escalates_below}")
                        violations.append(
                            f"{arm}/{capability} on {dataset} was measured at escalation threshold "
                            f"{record['thresholds']} and fleet.java ships {escalates_below}")
                    else:
                        verdict += (f"; escalates {record.get('escalatedShare')}% below "
                                    f"{escalates_below}")

                row(arm, capability, dataset, kind, f"{record['value']:.1f}",
                    f"{against:.1f}", f"{delta:+.1f}", verdict,
                    interval=record.get("ci95"),
                    note=(f"n={record['n']} {record['metric']}, 95% CI "
                          f"[{record['ci95'][0]:+.1f}, {record['ci95'][1]:+.1f}], {identity}, "
                          f"{record['experiment']}/{record['artifact']}"
                          if record.get("ci95") else
                          f"n={record['n']} {record['metric']}, {identity}, "
                          f"{record['experiment']}/{record['artifact']}"))

    if "--json" in sys.argv:
        # The same rows, for a caller that needs to count them rather than print them.
        print(json.dumps({"rows": rows, "violations": violations}, indent=2))
        return len(violations)

    if markdown:
        print("| arm | capability | public dataset | local | gpt-5.1 | difference | basis |")
        print("| --- | --- | --- | --- | --- | --- | --- |")
        for entry in rows:
            interval = ""
            if entry["interval"]:
                low, high = entry["interval"]
                interval = f" [{low:+.1f}, {high:+.1f}]"
            print(f"| `{entry['arm']}` | {entry['capability']} | {entry['dataset']} | "
                  f"**{entry['value']}** | {entry['against']} | {entry['delta']}{interval} | "
                  f"{entry['verdict']} |")
        print()
        return len(violations)

    # A declared quality number is a claim with a scale, and the only honest value for it is the
    # worst measurement behind it: a mean lets a strong dataset hide a weak one, and the number the
    # router compares against a floor should be the one a deployment can rely on.
    for arm, tasks in sorted(declared_quality().items()):
        for task, value in sorted(tasks.items()):
            entry = basis.get(f"{arm}/{task}", {})
            measured_arm = entry.get("measuredBy", {}).get("arm")
            experiment = entry.get("measuredBy", {}).get("experiment")
            found = [r for r in records
                     if r["capabilityDataset"] in SPEAKS_FOR.get(task, ())
                     and r["arm"] == measured_arm
                     and (not experiment or r["experiment"] == experiment)]
            if not found:
                row(arm, task, "-", "declared", f"{value:.2f}", "-", "-",
                    "NO MEASUREMENT BEHIND THE DECLARED QUALITY")
                violations.append(
                    f"{arm} declares quality {value} for {task} and no measurement of "
                    f"{measured_arm!r} supports it")
                continue
            worst = min(r["value"] for r in found) / 100
            if abs(worst - value) > 0.005:
                row(arm, task, "-", "declared", f"{value:.2f}", f"{worst:.2f}", "-",
                    "DECLARED QUALITY IS NOT THE WORST MEASUREMENT")
                violations.append(
                    f"{arm} declares quality {value} for {task}; the worst of "
                    f"{len(found)} measurements is {worst:.2f} "
                    f"({', '.join(r['capabilityDataset'] + '=' + format(r['value'], '.1f') for r in found)})")
                continue
            row(arm, task, "-", "declared", f"{value:.2f}", f"{worst:.2f}", "±0.00",
                f"ok: the worst of {len(found)} measurements")

    print()
    if violations:
        print(f"{len(violations)} capability declaration(s) the measurements do not support:")
        for violation in violations:
            print(f"  - {violation}")
        print()
        print("Each one is a claim this fleet makes about a model. Close the gap, drop the")
        print("declaration, or record a basis in PARITY-BASIS.json that this gate can check.")
    else:
        print("every declared capability rests on a measurement this gate checked")
    return len(violations)


if __name__ == "__main__":
    raise SystemExit(main())
