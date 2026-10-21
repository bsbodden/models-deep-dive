#!/usr/bin/env python3
"""One record shape for every experiment's headline numbers, and the only thing the gate reads.

Three experiments score three different kinds of question with three different scripts, and
`parity_gate.py` has to decide whether a capability a fleet declares is supported by any of them.
Teaching the gate three file formats is how a gate ends up agreeing with whichever format it
understood. So each scorer writes `MEASUREMENTS.json` beside its `RESULTS.json`: a flat list of
records in this shape, each one naming the arm, the model coordinate behind that arm, the metric,
the value, the item count and the raw artifact it came from.

A record is a measurement, not a verdict. The thresholds stay in the experiments' own protocols and
in the gate; nothing here decides anything.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ARM_IN_HARNESS = re.compile(r'new Arm\(\s*"([^"]+)"\s*,\s*"([^"]+)"', re.S)


def record(*, experiment: str, capability_dataset: str, arm: str, coordinate: str | None,
           metric: str, value: float, n: int, artifact: str,
           reference: dict | None = None, delta: float | None = None,
           ci95: list[float] | None = None, extra: dict | None = None) -> dict:
    """One arm's headline number on one dataset.

    `capability_dataset` is the key a capability declaration maps to -- "chat/coqa",
    "qa/squad2", "decide/trec" -- and `coordinate` is the Maven coordinate of the weights that
    produced it, so the gate can check that the thing measured is the thing the fleet ships.
    """
    out = {
        "experiment": experiment,
        "capabilityDataset": capability_dataset,
        "arm": arm,
        "coordinate": coordinate,
        "metric": metric,
        "value": round(float(value), 2),
        "n": int(n),
        "artifact": artifact,
    }
    if reference is not None:
        out["reference"] = reference
    if delta is not None:
        out["delta"] = round(float(delta), 2)
    if ci95 is not None:
        out["ci95"] = [round(float(ci95[0]), 2), round(float(ci95[1]), 2)]
    if extra:
        out.update(extra)
    return out


def write(directory: Path, records: list[dict]) -> Path:
    path = Path(directory) / "MEASUREMENTS.json"
    path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    return path


def read_all(experiments_root: Path) -> list[dict]:
    """Every experiment's records, with the directory they came from attached."""
    records = []
    for path in sorted(Path(experiments_root).glob("*/MEASUREMENTS.json")):
        for row in json.loads(path.read_text()):
            row.setdefault("experiment", path.parent.name)
            row["source"] = f"experiments/{path.parent.name}/MEASUREMENTS.json"
            records.append(row)
    return records


def coordinates_from_harness(harness: Path) -> dict[str, str]:
    """The arm name -> coordinate map a harness declares in its own source.

    Parsed rather than restated, for the same reason the gate parses fleet.java: a second copy of
    the mapping is a second thing to forget to update.
    """
    text = Path(harness).read_text()
    found = {name: coordinate for name, coordinate in ARM_IN_HARNESS.findall(text)}
    if not found:
        raise SystemExit(f"no arms found in {harness}; the parser is broken, not the harness")
    return found


def normalise_model_id(coordinate: str) -> str:
    """A coordinate's artifact id in the form a ModelJars catalog id uses.

    `org.modeljars.huggingface:bartowski.llama-3.2-1b-instruct-gguf.q4_k_m:3.2.0-q4_k_m.1`
    becomes `bartowski_llama_3_2_1b_instruct_gguf_q4_k_m`, which is the id `CatalogDiscovery`
    reports for the same weights. Everything that is not a letter or a digit becomes an
    underscore, and the version is dropped.
    """
    artifact = coordinate.split(":")[1] if ":" in coordinate else coordinate
    return re.sub(r"[^a-z0-9]+", "_", artifact.lower()).strip("_")


def same_weights(catalog_id: str, coordinate: str) -> bool:
    """Whether a catalog id and a Maven coordinate name the same weights.

    Not equality after normalisation, because the two namespaces disagree in ways that have
    nothing to do with identity: `CatalogDiscovery` reports `qwen3_0_6b_q4_0` for the artifact
    published at `ggml-org.qwen3-0.6b-gguf.q4_0`, dropping the publisher and the format. Every
    token of the catalog id must appear in the coordinate's artifact id, which accepts those
    omissions and still refuses two different models -- a 1B and an 8B share no size token, and a
    q4_0 and a q8_0 share no quantisation token.

    It cannot see through a composite: `org.modeljars.composite:harriet` carries no token of the
    base weights' id, so a declaration measured through a composite has to say so in the basis
    file and the gate prints that note rather than claiming a match it did not make.
    """
    artifact = set(normalise_model_id(coordinate).split("_"))
    return all(token in artifact for token in normalise_model_id(catalog_id).split("_"))
