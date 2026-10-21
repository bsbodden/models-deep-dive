# Does the shipped escalation threshold survive the method a practitioner would use on it?

The fleet's decision arm escalates a question to `gpt-5.1` when its own confidence falls below
**0.6**. That number was picked by looking at one dataset (SNIPS) and then scored on another
(TREC). Nobody tuned it, nobody checked whether the confidence behind it is calibrated, and nobody
asked what it buys per dollar at any other setting.

This experiment applies the procedure in Hamel Husain's *How To Use Decision Models For Evals*
(hamel.dev, read 2026-10-21) to our own gate: set a requirement first, tune the threshold by
cross-validation rather than by eye, and check the calibration of the score the threshold is
applied to. The post's framing is binary pass/fail judging; ours is multiclass intent
classification, so the binary decision under test is **the gate itself** — escalate or not — with
the positive class defined as *the local arm was wrong*. Under that mapping the post's metrics
transfer exactly: precision of escalation is the share of escalated questions the local arm would
have got wrong, recall is the share of its mistakes the gate catches.

## What this is and is not

It is a **reanalysis of rows already committed** by `experiments/routing-accuracy`: 100 SNIPS and
100 TREC items, each with the local arm's answer and confidence (`results-decide-routed-*.jsonl`)
and `gpt-5.1`'s answer for the same item (`results-decide-api-*.jsonl`). No model is run and no
provider is called. Every threshold is evaluated by composing those two files, which is the same
definition the measured gated arm uses: below the threshold, take the provider's answer.

It therefore **cannot** produce evidence about items nobody collected, cannot speak for any dataset
but these two, and cannot settle a threshold to more precision than the confidences are
reproducible to — which stage 1 measures rather than assumes.

Its records are written under `capabilityDataset` keys of `tuning/snips` and `tuning/trec`, which
are deliberately not keys `tools/parity_gate.py` maps any capability to. A sweep contains
measurements at thresholds the fleet does not ship, and those must not be able to support a
declaration.

## Stages

Each stage refuses to run unless the previous stage's artifact exists.

1. **Validate the simulator.** Compose the two files at the shipped 0.6 and compare with the
   measured `gated0-6` arm. Also measure how far the same item's confidence moved between the two
   runs, which bounds how finely any threshold can be chosen. Artifact: `stage1-simulator.json`.
2. **Sweep.** Every threshold from 0.00 to 1.00 in steps of 0.01: combined accuracy, escalated
   share, and the gate's own precision, recall, F1 and F2. Artifact: `stage2-sweep.json`.
3. **Tune by cross-validation.** Stratified 5-fold on the "local arm was wrong" label, seed
   20261021. Select the threshold maximising F1 on the four training folds subject to precision
   >= 0.80 **and** recall >= 0.80; if no threshold satisfies both on a fold, record that the
   constraint is infeasible and select on F1 alone. Score the selected threshold on the held-out
   fold. Artifact: `stage3-cv.json`.
4. **Calibration.** Reliability over 10 equal-width bins, expected calibration error, and the
   Brier score of the confidence as a prediction of the local arm's own correctness. Then Platt
   scaling fitted on the training folds only (IRLS on the log-odds, probabilities clipped to
   [1e-6, 1-1e-6]) and the held-out Brier before and after. Artifact: `stage4-calibration.json`.

## Decision rule, fixed before the analysis ran

The shipped 0.6 is **replaced** only if a cross-validated alternative beats it on held-out folds by
more than the run-to-run noise stage 1 measures, on **both** datasets, on combined accuracy at no
greater escalated share — or at a materially smaller escalated share (>= 10 points) for no loss of
accuracy beyond that noise. A win on one dataset and a loss on the other is a null, and is published
as one: that is exactly the shape of result that deleted a capability in the grounding experiment.

Platt scaling is **adopted** only if it improves the held-out Brier score on both datasets. It
changes nothing about routing if it does not, because the gate compares a confidence to a threshold
and a monotone recalibration of that confidence is the same gate at a moved threshold. Its value, if
any, is that the number the article prints beside an answer would then mean what it says.

## Kill criterion

If stage 1 shows the simulator disagrees with the measured gated arm by more than the confidence
drift can account for, the composition is not a model of the shipped gate and the rest of the
experiment is void. Nothing here is reported in that case except that failure.
