#!/usr/bin/env python3
"""Fail when the fleet declares a capability its measurements do not support.

The rule, stated by the person who owns this code: for the tasks a small model is supposed to
succeed at, it must be close to or better than the frontier model. This turns that into a check
rather than a hope.

A capability declaration in fleet.java is an application saying "this model may serve this work".
Nothing verified that claim until the accuracy experiment ran, and what it found was a gap of 16 to
35 points against gpt-5.1 on four public datasets. So every declared (arm, task) pair must either
have a measurement within the margin, or be declared knowingly: the fleet records which, and this
gate refuses anything else -- including a pair nobody has measured at all, because an unmeasured
claim is the failure mode this whole round of work came from.

Exit code is the number of violations, so CI fails on it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments/routing-accuracy/RESULTS.json"
WAIVERS = ROOT / "experiments/routing-accuracy/PARITY-WAIVERS.json"
MARGIN = 2.0  # points behind the frontier reference, from the experiment's own decision rule

# Which measured dataset speaks for which declared capability. A dataset measures a task; it does
# not measure a capability name this application invented, so the mapping is written down rather
# than guessed from a string match.
SPEAKS_FOR = {
    "grounding": ("qa/squad2", "qa/hotpotqa"),
    "decision": ("decide/snips", "decide/trec"),
}


def declared_capabilities() -> dict[str, set[str]]:
    """Each local arm's declared capabilities, read from the demo rather than restated here."""
    source = (ROOT / "code/fleet.java").read_text()
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


def main() -> int:
    if not RESULTS.exists():
        print(f"no measurements: {RESULTS.relative_to(ROOT)} is missing", file=sys.stderr)
        return 1
    stages = json.loads(RESULTS.read_text())["stages"]
    waivers = json.loads(WAIVERS.read_text()) if WAIVERS.exists() else {}

    violations = []
    print(f"{'arm':12}{'capability':14}{'dataset':16}{'routed':>8}{'frontier':>10}{'delta':>8}  verdict")
    for arm, capabilities in sorted(declared_capabilities().items()):
        for capability in sorted(capabilities):
            datasets = SPEAKS_FOR.get(capability)
            if not datasets:
                waived = waivers.get(f"{arm}/{capability}")
                verdict = "waived: " + waived if waived else "UNMEASURED"
                print(f"{arm:12}{capability:14}{'-':16}{'-':>8}{'-':>10}{'-':>8}  {verdict}")
                if not waived:
                    violations.append(
                        f"{arm} declares {capability} and no dataset in this experiment measures it")
                continue
            for dataset in datasets:
                stage = stages.get(dataset)
                if stage is None:
                    violations.append(f"{arm}/{capability}: {dataset} was not run")
                    print(f"{arm:12}{capability:14}{dataset:16}{'-':>8}{'-':>10}{'-':>8}  NOT RUN")
                    continue
                delta = stage["delta"]
                within = delta >= -MARGIN
                waived = waivers.get(f"{arm}/{capability}")
                verdict = "ok" if within else ("waived: " + waived if waived else "FAIL")
                print(f"{arm:12}{capability:14}{dataset:16}{stage['routed']:>8.1f}"
                      f"{stage['allApi']:>10.1f}{delta:>+8.1f}  {verdict}")
                if not within and not waived:
                    violations.append(
                        f"{arm} declares {capability} but is {abs(delta):.1f} points behind the "
                        f"frontier model on {dataset} (margin {MARGIN})")

    print()
    if violations:
        print(f"{len(violations)} capability declaration(s) the measurements do not support:")
        for violation in violations:
            print(f"  - {violation}")
        print()
        print("Each one is a claim this fleet makes about a model. Close the gap, drop the")
        print("declaration, or record a waiver in PARITY-WAIVERS.json that says why it stands.")
    else:
        print("every declared capability is within the margin or waived with a reason")
    return len(violations)


if __name__ == "__main__":
    raise SystemExit(main())
