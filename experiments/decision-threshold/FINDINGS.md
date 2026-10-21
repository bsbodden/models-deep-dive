# Findings: the shipped threshold stands, the confidence behind it does not mean what it says

Four stages, run on rows already committed by `experiments/routing-accuracy`. Reproduce with
`python3 tune.py all && python3 score.py`. Every number below is in `stage*.json` or
`RESULTS.json`; nothing here was typed from memory.

## 1. The composition reproduces the shipped gate, and bounds how finely it can be read

Composing the local arm's rows with `gpt-5.1`'s rows at the shipped 0.6 reproduces the measured
`gated0-6` arm exactly on TREC — **90.0** at **74%** escalated — and two points low on SNIPS:
**96.0** at **36%** against the measured **98.0** at **33%**.

The reason is in the same artifact. The same item's confidence is **not reproducible between
runs**: median drift **0.0104** on SNIPS and **0.0220** on TREC, max **0.1036** and **0.0983**, and
**3** SNIPS items and **4** TREC items changed side of 0.6 between the two runs. On SNIPS those
three items are worth two points of accuracy and three points of escalated share.

That has a consequence for a claim this project makes elsewhere. The declared SNIPS result, **98.0
against gpt-5.1's 96.0**, is a +2.0 margin, and the identical configuration re-measures at **96.0**
— parity. The declaration still passes the gate's frontier basis either way, because that basis
asks for within-2.0 rather than for a win, but the arm is not evidenced to *beat* the frontier
model on SNIPS. It is evidenced to match it at a third of the calls.

## 2. The post's own minimum requirement is infeasible here, at every threshold

Read as a binary decision — escalate, with the positive class *the local arm was wrong* — the gate
at 0.6 has precision **0.500** and recall **0.900** on SNIPS, and precision **0.297** and recall
**0.917** on TREC. It catches nearly every mistake and pays for it by escalating questions the
local arm had right: on TREC, **seven of every ten escalated questions** were ones it would have
answered correctly.

No threshold satisfies precision >= 0.80 **and** recall >= 0.80, on either dataset, on any of the
five training splits. The best F1 available is **0.732** at threshold 0.47 on SNIPS and **0.478** at
0.55 on TREC. By the post's selection criterion — set a requirement, rule out models that cannot
meet it — this decision model would be **ruled out** as a judge. It is still the right choice for
this fleet, for a reason the post does not have to consider: the gate is not the product. Accuracy
of the combined arm is, and that is bought by over-escalating.

## 3. Cross-validated tuning loses accuracy to save calls — a null under the frozen rule

Stratified 5-fold, seed 20261021, threshold chosen on four folds and scored on the fifth:

| dataset | folds chose | held-out accuracy, tuned | at 0.6 | escalated share, tuned | at 0.6 |
| --- | --- | --- | --- | --- | --- |
| SNIPS | 0.47, 0.55, 0.47, 0.47, 0.47 | 93.0 | 96.0 | 24% | 36% |
| TREC | 0.55, 0.52, 0.55, 0.55, 0.33 | 89.0 | 90.0 | 59% | 74% |

Both datasets agree on the direction — a lower threshold, fewer provider calls, less accuracy — and
neither satisfies either clause of the decision rule: SNIPS loses 3.0 points where the run-to-run
noise is 2.0, and TREC loses 1.0 point where this comparison's noise floor measured 0.0. **The
shipped 0.6 is kept, and it is kept because a cheaper gate measured worse, not because nobody
checked.**

Two honest caveats. The TREC noise floor of 0.0 is one comparison in which four items changed side
of the threshold and none of them changed the outcome; the true resolution is coarser than zero, and
a 1.0-point loss at n=100 is not a result either way. And F1 is the wrong objective for this gate
even though it is the post's default: it weights a wasted provider call the same as a wrong answer
served to a customer, which is not this fleet's exchange rate. A rule written for that exchange rate
would have to price the calls, which is what `RESULTS.json` reports beside every threshold.

## 4. The confidence is badly calibrated, in the under-confident direction

| dataset | mean confidence | observed accuracy | ECE | Brier, reported | Brier, Platt-scaled | 95% CI of the change |
| --- | --- | --- | --- | --- | --- | --- |
| SNIPS | 0.663 | 0.800 | 0.153 | 0.1198 | 0.1044 | [-0.0351, +0.0046] |
| TREC | 0.455 | 0.760 | 0.322 | 0.2695 | 0.1743 | [-0.1486, -0.0414] |

The arm is right **80%** of the time on SNIPS while reporting **0.663**, and right **76%** of the
time on TREC while reporting **0.455**. The reliability bins are negative almost everywhere: it
understates itself across the whole range, not only at the ends.

Platt scaling fitted on the training folds improves the held-out Brier score on both datasets by
point estimate, conclusively on TREC (interval excludes zero, 5 of 5 folds) and inconclusively on
SNIPS (interval includes zero, 4 of 5 folds). It is adopted as a **reporting** change only: the
scaling is monotone, so it cannot change which questions this gate escalates, only the number
printed beside an answer.

The useful consequence is the translation. Once calibrated, the shipped threshold of 0.6 means
**"escalate unless the answer is about 82% likely to be right"** on SNIPS and **84%** on TREC —
nearly the same requirement on both, even though one escalates 36% of questions and the other 74%.
The gate's meaning is stable across the two datasets; what differs is how hard the questions are.
A threshold that reads as "escalate when less than 60% sure" is doing something considerably
stricter than it sounds, and that is worth knowing before anyone tunes it by feel.

## What this cannot say

Two datasets, 100 items each, one model, one rubric set, and no new collection. It cannot speak for
any other decision task, it cannot resolve a one-point difference, and it says nothing about whether
a better-calibrated model would need a gate at all. The one thing it settles is local: the number
the fleet ships is the better of the two measured here, and the confidence it compares against is
pessimistic by 14 points on one dataset and 30 on the other.
