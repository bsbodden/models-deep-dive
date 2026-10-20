#!/usr/bin/env python3
"""Score the committed result files against gold, and print the decision the protocol fixed.

The harness writes answers; this writes verdicts. Keeping them apart means the thing that produced
the answers never knew what would count as a win.

Scoring follows the published conventions rather than new ones: SQuAD normalisation (lowercase,
drop articles and punctuation, collapse whitespace) with exact match and token F1 for the question
answering, label accuracy for the decisions. The 95% intervals are bootstrap percentile intervals
over 10,000 resamples of the paired per-item scores, so the interval is on the difference the
protocol's thresholds are written against.
"""

from __future__ import annotations

import json
import random
import re
import string
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESAMPLES = 10_000
SEED = 20261019
ACCEPT_WITHIN = 2.0   # points; see README.md
REJECT_BEYOND = 5.0

ABSTENTIONS = ("i don't know", "i do not know", "dont know", "unknown", "not in the notes")


CITATION = re.compile(r"\[(?:doc-)?\d+(?:\s*,\s*(?:doc-)?\d+)*\]")


def normalise(text: str) -> str:
    # Citation markers are markup, not answer. The grounding-policy arm returns a cited answer --
    # "The Treaty of Amsterdam [doc-1]" -- which is right for a RAG pipeline and unscoreable under
    # span exact match. Stripping them is a scoring decision made after seeing that arm score 0.0
    # on answers that were otherwise correct, and it is declared here and in FINDINGS.md rather
    # than folded in quietly. It cannot flatter an arm that emits no citations.
    text = CITATION.sub(" ", text)
    text = text.lower()
    text = "".join(ch for ch in text if ch not in set(string.punctuation))
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return " ".join(text.split())


def abstained(answer: str) -> bool:
    low = answer.strip().lower()
    return not low or any(phrase in low for phrase in ABSTENTIONS)


def f1(prediction: str, gold: str) -> float:
    pred_tokens, gold_tokens = normalise(prediction).split(), normalise(gold).split()
    if not pred_tokens or not gold_tokens:
        return float(pred_tokens == gold_tokens)
    common = Counter(pred_tokens) & Counter(gold_tokens)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision, recall = overlap / len(pred_tokens), overlap / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def score_qa(rows: dict, gold: dict) -> dict:
    em, token_f1, per_item = [], [], {}
    for item_id, row in rows.items():
        answers = gold[item_id]["answers"]
        unanswerable = gold[item_id]["unanswerable"]
        answer = row["answer"]
        if unanswerable:
            # An unanswerable question's gold answer is to decline. Scoring a decline as a miss
            # would reward a model that always produces something.
            hit = 1.0 if abstained(answer) else 0.0
            em.append(hit)
            token_f1.append(hit)
        else:
            if abstained(answer):
                em.append(0.0)
                token_f1.append(0.0)
            else:
                em.append(max(float(normalise(answer) == normalise(a)) for a in answers))
                token_f1.append(max(f1(answer, a) for a in answers))
        per_item[item_id] = (em[-1], token_f1[-1])
    return {"n": len(em), "exactMatch": 100 * sum(em) / len(em),
            "tokenF1": 100 * sum(token_f1) / len(token_f1), "perItem": per_item}


def score_labels(rows: dict, gold: dict, labels: list[str]) -> dict:
    correct, unparseable, per_item = [], 0, {}
    for item_id, row in rows.items():
        want = gold[item_id]["label"]
        answer = row["answer"].strip()
        picked = answer if answer in labels else next(
            (label for label in labels if label.lower() == answer.lower()), None)
        if picked is None:
            # A provider that answers with a sentence rather than a label is wrong here, and the
            # count is reported separately so the reason is visible.
            picked = next((label for label in labels if label.lower() in answer.lower()), None)
            if picked is None:
                unparseable += 1
        hit = float(picked == want)
        correct.append(hit)
        per_item[item_id] = (hit, hit)
    return {"n": len(correct), "accuracy": 100 * sum(correct) / len(correct),
            "unparseable": unparseable, "perItem": per_item}


def paired_interval(left: dict, right: dict, key: int = 0) -> tuple[float, float]:
    shared = sorted(set(left["perItem"]) & set(right["perItem"]))
    if not shared:
        return (float("nan"), float("nan"))
    diffs = [left["perItem"][i][key] - right["perItem"][i][key] for i in shared]
    rng = random.Random(SEED)
    means = []
    for _ in range(RESAMPLES):
        means.append(100 * sum(rng.choice(diffs) for _ in diffs) / len(diffs))
    means.sort()
    return (means[int(0.025 * RESAMPLES)], means[int(0.975 * RESAMPLES)])


def verdict(delta: float, low: float, high: float) -> str:
    if delta >= -ACCEPT_WITHIN and low >= -REJECT_BEYOND:
        return "ACCEPT" if high >= -ACCEPT_WITHIN else "INCONCLUSIVE"
    if delta <= -REJECT_BEYOND and high <= -ACCEPT_WITHIN:
        return "REJECT"
    return "INCONCLUSIVE"


def load(stage: str, arm: str, dataset: str) -> dict | None:
    path = HERE / f"results-{stage}-{arm}-{dataset}.jsonl"
    if not path.exists():
        return None
    rows = {}
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def main() -> int:
    manifest = json.loads((HERE / "MANIFEST.json").read_text())
    report = {"resamples": RESAMPLES, "seed": SEED, "stages": {}}
    lines = []

    for stage, datasets in (("qa", ("squad2", "hotpotqa")), ("decide", ("snips", "trec"))):
        for dataset in datasets:
            routed, api = load(stage, "routed", dataset), load(stage, "api", dataset)
            if not routed or not api:
                lines.append(f"{stage}/{dataset}: not run")
                continue
            gold = {i["id"]: i for i in json.loads((HERE / f"sample-{dataset}.json").read_text())}
            shared = set(routed) & set(api)
            routed = {k: v for k, v in routed.items() if k in shared}
            api = {k: v for k, v in api.items() if k in shared}

            # Byte-identical prompts, per the protocol's second kill criterion.
            drift = [k for k in shared if routed[k]["promptSha256"] != api[k]["promptSha256"]]
            if drift:
                raise SystemExit(f"{stage}/{dataset}: {len(drift)} prompts differ between arms")

            if stage == "qa":
                left, right = score_qa(routed, gold), score_qa(api, gold)
                headline, metric = "exactMatch", "exact match"
                extra = f"token F1 {left['tokenF1']:.1f} against {right['tokenF1']:.1f}"
                # Reported because the aggregate hid the cause on the first dataset: a model that
                # never declines loses every unanswerable item while tying on the answerable ones,
                # and "worse at reading" and "never abstains" are different problems with
                # different fixes. This is extra detail, not a change to the decision rule.
                split = {}
                for kind, name in ((False, "answerable"), (True, "unanswerable")):
                    subset_ids = [k for k in shared if gold[k]["unanswerable"] == kind]
                    if not subset_ids:
                        continue
                    for side, rows_side in (("routed", routed), ("allApi", api)):
                        subset = {k: rows_side[k] for k in subset_ids}
                        scored = score_qa(subset, gold)
                        split[f"{name}/{side}"] = {
                            "n": scored["n"],
                            "exactMatch": round(scored["exactMatch"], 2),
                            "tokenF1": round(scored["tokenF1"], 2),
                            "abstained": sum(1 for r in subset.values() if abstained(r["answer"])),
                        }
            else:
                split = {}
                labels = manifest["labelSets"][dataset]
                left, right = (score_labels(routed, gold, labels),
                               score_labels(api, gold, labels))
                headline, metric = "accuracy", "label accuracy"
                extra = (f"unparseable provider answers: {right['unparseable']}"
                         f" of {right['n']}")

            delta = left[headline] - right[headline]
            low, high = paired_interval(left, right)
            local_share = 100 * sum(1 for r in routed.values() if r.get("local")) / len(routed)
            call = verdict(delta, low, high)
            # The stage measures the local model only if routing actually sent the work there.
            if local_share < 80:
                call = f"VOID (routing sent only {local_share:.0f}% of items to a local model)"

            report["stages"][f"{stage}/{dataset}"] = {
                "n": left["n"], "metric": metric,
                "routed": round(left[headline], 2), "allApi": round(right[headline], 2),
                "delta": round(delta, 2), "ci95": [round(low, 2), round(high, 2)],
                "localShare": round(local_share, 1), "verdict": call,
                "routedExtra": left, "apiExtra": right,
            }
            if split:
                report["stages"][f"{stage}/{dataset}"]["split"] = split

            # The grounding-policy arm is reported, not judged: it re-decides the same collected
            # answers through GroundedAnswerPolicy, which fleet.java does not use and rag.java
            # does. It exists because "you did not use the policy" is the first objection to the
            # routed arm's score, and an objection that can be measured should not be argued.
            policy = load(stage, "policy", dataset)
            if policy and stage == "qa":
                policy = {k: v for k, v in policy.items() if k in shared}
                scored = score_qa(policy, gold)
                decisions = Counter(v.get("groundingDecision", "?") for v in policy.values())
                report["stages"][f"{stage}/{dataset}"]["groundingPolicyArm"] = {
                    "n": scored["n"], "exactMatch": round(scored["exactMatch"], 2),
                    "tokenF1": round(scored["tokenF1"], 2), "decisions": dict(decisions)}
                lines.append(
                    f"    grounding-policy arm: EM {scored['exactMatch']:.1f} "
                    f"F1 {scored['tokenF1']:.1f}, decisions {dict(decisions)}")
            for side in ("routedExtra", "apiExtra"):
                report["stages"][f"{stage}/{dataset}"][side].pop("perItem", None)
            lines.append(
                f"{stage}/{dataset}: n={left['n']} {metric} routed {left[headline]:.1f} against "
                f"all-API {right[headline]:.1f}, delta {delta:+.1f} "
                f"[{low:+.1f}, {high:+.1f}] -- {call}; {extra}; "
                f"{local_share:.0f}% answered locally")
            for name, values in split.items():
                lines.append(f"    {name}: n={values['n']} EM {values['exactMatch']:.1f} "
                             f"F1 {values['tokenF1']:.1f} abstained {values['abstained']}")

    (HERE / "RESULTS.json").write_text(json.dumps(report, indent=2) + "\n")
    print("\n".join(lines))
    print("\nRESULTS.json written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
