#!/usr/bin/env python3
"""Tests for the gate, because a gate nobody tests is a gate that passes for the wrong reason.

This already happened twice today. `check_grounding_guard.sh` grepped for a model id and reported a
working fleet as broken the day the model changed. An earlier `parity_gate.py` sliced `fleet.java`
to the wrong `// endregion`, found no declarations at all, and printed a clean table while
measuring nothing -- which is why the parser now refuses an empty parse.

Each case builds a throwaway repository: a `fleet.java` with the declarations under test, a basis
file, and one experiment's `MEASUREMENTS.json`. The gate runs against it as a subprocess, exactly
as CI runs it, and the assertions are on its exit code -- which is the violation count -- and on
the text it prints, because the text is what a person reads at 2am.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLEET = """
class fleet {{
  static final String TINY_ID = "tiny_model_q8_0";
  static final String GROUNDER_ID = "big_model_q4_k_m";

  static List<Prompt> prompts() {{
    // region: requirements
    var grounded =
        RoutingRequirements.builder()
            .requireCapability("grounding")
            {boundary}
            .build();
    var decision = RoutingRequirements.builder().requireCapability("decision").build();
    // endregion
    return List.of();
  }}

  static ModelFleet<Responder> buildFleet() {{
    // region: locals
    var grounder =
        discovered(catalog, GROUNDER_ID)
            {quality}
            .tags(Set.of())
            .capabilities(Set.of("grounding"))
            .build();
    // endregion
    return null;
  }}

  static double escalate() {{
    return Double.parseDouble(
        System.getProperty("fleet.decisions.escalateBelowConfidence", "{threshold}"));
  }}
}}
"""


def write_repo(root: Path, *, boundary: str = "", quality: str = "", threshold: str = "0",
               basis: dict | None = None, records: list[dict] | None = None) -> None:
    (root / "tools").mkdir(parents=True)
    (root / "code").mkdir(parents=True)
    (root / "experiments/fixture").mkdir(parents=True)
    (root / "evidence/runs").mkdir(parents=True)
    for name in ("parity_gate.py", "measurements.py"):
        shutil.copy(HERE / name, root / "tools" / name)
    (root / "code/fleet.java").write_text(
        FLEET.format(boundary=boundary, quality=quality, threshold=threshold))
    (root / "PARITY-BASIS.json").write_text(json.dumps({"declarations": basis or {}}, indent=2))
    (root / "experiments/fixture/MEASUREMENTS.json").write_text(
        json.dumps(records or [], indent=2))


def run(root: Path) -> tuple[int, str]:
    finished = subprocess.run([sys.executable, str(root / "tools/parity_gate.py")],
                              capture_output=True, text=True, cwd=root)
    return finished.returncode, finished.stdout + finished.stderr


def record(dataset: str, arm: str, value: float, *, delta: float | None = None,
           reference: float = 90.0, thresholds: list[float] | None = None,
           catalog_ids: list[str] | None = None, extra: dict | None = None) -> dict:
    out = {
        "experiment": "fixture", "capabilityDataset": dataset, "arm": arm,
        "coordinate": None, "metric": "exactMatch", "value": value, "n": 100,
        "artifact": f"results-{arm}-{dataset}.jsonl",
        "reference": {"arm": "api", "catalogIds": ["gpt-5.1"], "value": reference},
        "delta": value - reference if delta is None else delta,
        "ci95": [-1.0, 1.0],
        "catalogIds": catalog_ids if catalog_ids is not None else ["big_model_q4_k_m"],
    }
    if thresholds:
        out["thresholds"] = thresholds
        out["escalatedShare"] = 50.0
    if extra:
        out.update(extra)
    return out


CASES: list[tuple[str, dict, int, list[str], list[str]]] = []


def case(name: str, repo: dict, expected_violations: int,
         must_say: list[str], must_not_say: list[str] | None = None) -> None:
    CASES.append((name, repo, expected_violations, must_say, must_not_say or []))


FRONTIER_BASIS = {"grounder/grounding": {
    "basis": "frontier",
    "measuredBy": {"experiment": "fixture", "arm": "big"},
    "reason": "fixture"}}
LOCAL_BASIS = {"grounder/grounding": {
    "basis": "best-local",
    "measuredBy": {"experiment": "fixture", "arm": "big"},
    "reason": "fixture"}}

case("a declaration with no basis is a violation",
     dict(basis={}, records=[record("qa/squad2", "big", 95.0)]),
     1, ["NO BASIS RECORDED", "records no basis"])

case("a declaration within the margin passes",
     dict(basis=FRONTIER_BASIS,
          records=[record("qa/squad2", "big", 95.0), record("qa/hotpotqa", "big", 89.0)]),
     0, ["ok", "every declared capability rests on a measurement"])

case("a declaration behind the margin fails with the gap",
     dict(basis=FRONTIER_BASIS,
          records=[record("qa/squad2", "big", 95.0), record("qa/hotpotqa", "big", 50.0)]),
     1, ["FAIL", "40.0 points behind"])

case("a dataset that was never run is a violation, not an omission",
     dict(basis=FRONTIER_BASIS, records=[record("qa/squad2", "big", 95.0)]),
     1, ["NOT RUN", "has no measurement"])

case("a measurement of a different model is refused",
     dict(basis=FRONTIER_BASIS,
          records=[record("qa/squad2", "big", 95.0, catalog_ids=["some_other_model"]),
                   record("qa/hotpotqa", "big", 95.0, catalog_ids=["some_other_model"])]),
     2, ["WRONG MODEL", "is not among the models"])

case("best-local is refused when the requirement is not local-only",
     dict(basis=LOCAL_BASIS,
          records=[record("qa/squad2", "big", 10.0), record("qa/hotpotqa", "big", 10.0)]),
     1, ["REFUSED", "does not set RoutingDataBoundary.LOCAL_ONLY"])

case("best-local is allowed when the requirement is local-only",
     dict(boundary=".dataBoundary(RoutingDataBoundary.LOCAL_ONLY)",
          basis=LOCAL_BASIS,
          records=[record("qa/squad2", "big", 10.0,
                          extra={"carriesDeclaration": True,
                                 "bestLocal": {"arm": "big", "value": 10.0, "behind": 0.0}}),
                   record("qa/hotpotqa", "big", 10.0,
                          extra={"carriesDeclaration": True,
                                 "bestLocal": {"arm": "big", "value": 10.0, "behind": 0.0}})]),
     0, ["first among local arms", "80.0 behind gpt-5.1"])

case("a best-local arm ahead of the frontier model is not described as behind it",
     dict(boundary=".dataBoundary(RoutingDataBoundary.LOCAL_ONLY)",
          basis=LOCAL_BASIS,
          records=[record("qa/squad2", "big", 95.0,
                          extra={"carriesDeclaration": True,
                                 "bestLocal": {"arm": "big", "value": 95.0, "behind": 0.0}}),
                   record("qa/hotpotqa", "big", 95.0,
                          extra={"carriesDeclaration": True,
                                 "bestLocal": {"arm": "big", "value": 95.0, "behind": 0.0}})]),
     0, ["5.0 ahead of gpt-5.1"], ["5.0 behind gpt-5.1"])

case("a measurement taken with escalation fails a fleet that ships without it",
     dict(basis=FRONTIER_BASIS,
          records=[record("qa/squad2", "big", 95.0, thresholds=[0.6]),
                   record("qa/hotpotqa", "big", 95.0, thresholds=[0.6])]),
     2, ["measured with escalation, fleet ships without it"])

case("a measurement taken at another threshold than the fleet ships fails",
     dict(threshold="0.4", basis=FRONTIER_BASIS,
          records=[record("qa/squad2", "big", 95.0, thresholds=[0.6]),
                   record("qa/hotpotqa", "big", 95.0, thresholds=[0.6])]),
     2, ["measured at [0.6], fleet ships 0.4"])

case("an inflated quality number is refused, with both numbers",
     dict(quality='.quality(java.util.Map.of("grounding", 0.95))',
          basis=FRONTIER_BASIS,
          records=[record("qa/squad2", "big", 95.0), record("qa/hotpotqa", "big", 89.0)]),
     1, ["DECLARED QUALITY IS NOT THE WORST MEASUREMENT", "the worst of 2 measurements is 0.89"])

case("a quality number equal to the worst measurement passes",
     dict(quality='.quality(java.util.Map.of("grounding", 0.89))',
          basis=FRONTIER_BASIS,
          records=[record("qa/squad2", "big", 95.0), record("qa/hotpotqa", "big", 89.0)]),
     0, ["ok: the worst of 2 measurements"])


def main() -> int:
    failures = 0
    for name, repo, expected, must_say, must_not_say in CASES:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_repo(root, **repo)
            code, output = run(root)
        problems = []
        if code != expected:
            problems.append(f"exit {code}, expected {expected}")
        for phrase in must_say:
            if phrase not in output:
                problems.append(f"missing {phrase!r}")
        for phrase in must_not_say:
            if phrase in output:
                problems.append(f"should not say {phrase!r}")
        if problems:
            failures += 1
            print(f"FAIL  {name}")
            for problem in problems:
                print(f"        {problem}")
            print("      ---- gate output ----")
            for line in output.splitlines():
                print(f"      {line}")
        else:
            print(f"ok    {name}")
    print()
    print(f"{len(CASES) - failures} of {len(CASES)} gate cases pass")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
