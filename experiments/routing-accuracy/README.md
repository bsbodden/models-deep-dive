# Does routing to a local model cost accuracy?

**Status: protocol frozen, no data collected.** Written before the first measurement, per the
house rule that the hypothesis, the decision rule and the kill criterion are committed before the
run. Nothing in this directory may be edited after data collection begins except the results
files; a protocol change means a new directory.

## The gap this closes

`articles/models-deep-dive` compares a routed fleet against sending every prompt to `gpt-5.1`, and
publishes cost and latency for both. Its accuracy row says **not measured** on both sides, because
that harness records what each arm charged and how long it took and never scores an answer. The
whole argument for routing rests on the part that is unmeasured: that a 1B model quoting retrieved
text, and a 4B model choosing between labels, are good enough that moving that traffic off a
frontier model is free in quality terms.

## Hypothesis

On the traffic the router actually assigns them, the local arms answer **no worse than** the
frontier model, where "no worse" is defined per task below. The null being tested is that they do.

This is a screen, not a leaderboard. It can find a large difference; it cannot certify a small one.

## What is measured, on data nobody here authored

Two task families, two public datasets each, because one dataset measured carefully has already
produced a confident wrong answer on this project once.

| stage | task | datasets | gold | scored by |
| --- | --- | --- | --- | --- |
| 1 | grounded question answering | HotpotQA distractor validation; SQuAD v2 dev | short answer strings, plus unanswerable items in SQuAD v2 | exact match and token F1 under the SQuAD normalisation (lowercase, strip articles and punctuation) |
| 2 | closed decision over a fixed label set | SNIPS 2017 seven-intent validation; TREC coarse question classification | gold label | label accuracy |
| 3 | long-document summarisation | deferred; see below | none | an LLM judge, prompts committed before the run |

Stage 3 compares two hosted models rather than local against frontier, needs a judge rather than
gold, and answers a different question. It runs only if stages 1 and 2 complete, and its judge
prompt is committed before its first call.

## Arms

Both arms see **byte-identical prompts**, built once per item and passed to each. The only
difference is which model answers.

- **routed** — the article's own fleet, through `ModelRouter`, with the same policy, requirements
  and candidates as `code/fleet.java`. The router decides which model answers each item, and the
  model it chose is recorded per item. If it escalates an item to a provider, that is part of the
  result and is reported as such, not quietly dropped.
- **all-API** — every item to `gpt-5.1`, the same model the article's no-router arm uses.

Retrieval is **budget-matched**: for grounded QA, each item's full paragraph set from the dataset
is placed in both arms' prompts, so the local arm never answers from less evidence than the
frontier model gets. A prompt that does not fit a candidate's context window makes that candidate
ineligible, which is routing working, and is recorded.

## Decision rule, fixed now

Per dataset, with n recorded and a 95% bootstrap interval on the difference:

- **Accept** the article's routing claim for that task if the routed arm's score is within
  **2 points** of the all-API arm, or better.
- **Reject** it if the routed arm is worse by **more than 5 points**, and say so in the article in
  the same table that currently says "not measured".
- **Inconclusive** between 2 and 5 points, or if the interval spans the threshold: reported as
  inconclusive with its n, not rounded into either verdict.

A disagreement between the two datasets in a family is reported as a disagreement. It is not
averaged away, and the more favourable dataset is not promoted.

## Kill criteria

- **Routing does not do what the comparison assumes.** If fewer than 80% of a stage's items are
  answered by the local arm the stage was built to test, the stage measures the router's
  eligibility rules rather than the local model's accuracy. Stop, report that, and fix the fleet
  or the stage rather than publishing the score.
- **Budget drift.** If the two arms' prompts are not byte-identical for every item, stop.
- **Cost ceiling.** USD 15 of provider spend across all stages. The run stops at the ceiling and
  reports partial results with their n.
- **Host ceiling.** 6 hours of one `ccx33`, about USD 1.60. Stops and reports what finished.

## What this cannot test

- **Not the heartbeats.** Three tokens saying "still here" have no accuracy to measure; that row
  of the article's table is latency and nothing else.
- **Not the article's own ten prompts.** Those are ours, and a corpus we wrote would score our own
  assumptions back to us. The datasets here were written by other people for other purposes, which
  is the point and also a limit: they are not a support queue.
- **Not quality under load, or over time.** One host, one afternoon, one pinned set of weights.
- **Not whether the frontier model is right.** `gpt-5.1` is scored against the same gold as the
  local arms, so the comparison holds even where both are wrong, but the datasets' own label noise
  bounds what any of these numbers mean.

## Pins

Recorded in `REPRODUCE.md` with the dataset SHA-256s and the exact artifact coordinates before the
first measured call.
