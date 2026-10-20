#!/usr/bin/env python3
"""What a confidence gate would have bought, computed over the answers already collected.

This is a counterfactual, not a measured pipeline: for each threshold it takes the local answer
when Harriet's confidence is at or above the threshold and the provider's answer otherwise, from
the committed result files. Nothing runs and nothing is charged.

It is reported because the per-item data says the local arm knows when it is unsure -- its
confidence is far lower on the items it gets wrong -- and a fleet can act on that. Two honest
limits come with it. Choosing the threshold on the same dataset that scores it is overfitting, so
the cross-dataset column is the one to read: the threshold picked on one dataset, applied to the
other. And escalating costs provider calls, so the escalation rate is the price.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASETS = ("snips", "trec")
THRESHOLDS = [round(0.05 * i, 2) for i in range(0, 21)]


def load(dataset: str) -> list[dict]:
    gold = {i["id"]: i["label"] for i in json.loads((HERE / f"sample-{dataset}.json").read_text())}
    def rows(arm):
        path = HERE / f"results-decide-{arm}-{dataset}.jsonl"
        if not path.exists():
            return {}
        return {json.loads(l)["id"]: json.loads(l)
                for l in path.read_text().splitlines() if l.strip()}
    routed, api = rows("routed"), rows("api")
    shared = sorted(set(routed) & set(api) & set(gold))
    return [{"gold": gold[k], "local": routed[k]["answer"],
             "confidence": routed[k].get("confidence", 0.0), "api": api[k]["answer"]}
            for k in shared]


def sweep(items: list[dict]) -> list[tuple[float, float, float]]:
    out = []
    for threshold in THRESHOLDS:
        escalated = [i for i in items if i["confidence"] < threshold]
        correct = sum(1 for i in items
                      if (i["api"] if i["confidence"] < threshold else i["local"]) == i["gold"])
        out.append((threshold, 100 * correct / len(items), 100 * len(escalated) / len(items)))
    return out


def main() -> int:
    loaded = {d: load(d) for d in DATASETS}
    loaded = {d: items for d, items in loaded.items() if items}
    if not loaded:
        print("no decision results yet")
        return 1

    best = {}
    for dataset, items in loaded.items():
        rows = sweep(items)
        local_only = rows[0][1]
        api_only = [r for r in rows if r[0] >= 1.0][-1][1]
        print(f"== {dataset}: n={len(items)}, local only {local_only:.1f}, all-API {api_only:.1f}")
        print(f"{'threshold':>10}{'accuracy':>10}{'escalated':>11}")
        for threshold, accuracy, escalated in rows:
            if threshold in (0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0):
                print(f"{threshold:>10.2f}{accuracy:>10.1f}{escalated:>10.0f}%")
        # The threshold that maximises accuracy here, kept only to apply to the other dataset.
        best[dataset] = max(rows, key=lambda r: (r[1], -r[2]))
        print(f"   best on this dataset: threshold {best[dataset][0]:.2f} -> "
              f"{best[dataset][1]:.1f} at {best[dataset][2]:.0f}% escalated")
        print()

    if len(loaded) == 2:
        print("cross-dataset, which is the honest number: a threshold chosen on one dataset,")
        print("applied to the other, so the data that picked it is not the data that scores it.")
        for source, target in (("snips", "trec"), ("trec", "snips")):
            threshold = best[source][0]
            items = loaded[target]
            escalated = [i for i in items if i["confidence"] < threshold]
            correct = sum(1 for i in items
                          if (i["api"] if i["confidence"] < threshold else i["local"]) == i["gold"])
            rows = sweep(items)
            print(f"  threshold {threshold:.2f} from {source} on {target}: "
                  f"{100 * correct / len(items):.1f} against {rows[0][1]:.1f} local-only and "
                  f"{[r for r in rows if r[0] >= 1.0][-1][1]:.1f} all-API, "
                  f"{100 * len(escalated) / len(items):.0f}% escalated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
