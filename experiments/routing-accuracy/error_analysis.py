#!/usr/bin/env python3
"""Group the decision arm's mistakes by the confusion they are, from its own committed rows.

An accuracy of 80.0 says how often the arm was wrong. It does not say *how*, and "how" is the only
thing a fix can act on. This reads the routed arm's rows, scores them with the frozen scorer, and
prints every wrong item grouped by (gold -> predicted) with the confidence the arm reported, so a
rubric change can be aimed at a confusion rather than at an average.

Nothing here is tuning. It is the diagnostic a tuning experiment would have to start from, and it
is a script rather than a paragraph so the groups cannot drift from the rows.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import score as stick  # noqa: E402  the frozen scorer


def main() -> int:
    manifest = json.loads((HERE / "MANIFEST.json").read_text())
    report = {}
    for dataset in ("snips", "trec"):
        rows = {}
        for line in (HERE / f"results-decide-routed-{dataset}.jsonl").read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["id"]] = row
        gold = {i["id"]: i for i in json.loads((HERE / f"sample-{dataset}.json").read_text())}
        scored = stick.score_labels(rows, gold, manifest["labelSets"][dataset])
        wrong = [(k, rows[k]) for k, (hit, _) in scored["perItem"].items() if hit == 0.0]

        confusions = Counter()
        examples = defaultdict(list)
        for item_id, row in wrong:
            pair = (gold[item_id]["label"], row["answer"].strip())
            confusions[pair] += 1
            examples[pair].append({
                "id": item_id,
                "confidence": round(row["confidence"], 3),
                "probability": round(row["probability"], 3),
                "text": gold[item_id].get("text", ""),
            })

        print(f"\n== {dataset}: {len(wrong)} wrong of {len(rows)}, "
              f"accuracy {scored['accuracy']:.1f}")
        for (want, got), count in confusions.most_common():
            share = 100 * count / len(wrong)
            median = sorted(e["confidence"] for e in examples[(want, got)])[count // 2]
            print(f"  {want} read as {got}: {count} items ({share:.0f}% of the errors), "
                  f"median confidence {median:.3f}")
            for example in examples[(want, got)][:2]:
                print(f"      c={example['confidence']:.3f}  {example['text'][:68]}")
        report[dataset] = {
            "n": len(rows),
            "accuracy": round(scored["accuracy"], 2),
            "wrong": len(wrong),
            "confusions": [
                {"gold": want, "predicted": got, "count": count,
                 "shareOfErrors": round(100 * count / len(wrong), 1),
                 "items": examples[(want, got)]}
                for (want, got), count in confusions.most_common()
            ],
        }

    (HERE / "ERROR-ANALYSIS.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nwrote {HERE / 'ERROR-ANALYSIS.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
