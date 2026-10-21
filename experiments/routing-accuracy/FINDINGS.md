# What the measurement said

Written after scoring, against the decision rule frozen in [README.md](README.md) before
collection. Every number here is in [RESULTS.json](RESULTS.json), derived by `score.py` from the
committed per-item files.

Collected 2026-10-20 on a Hetzner `ccx33` provisioned for this and deleted after it, on ModelJars
0.1.62 / Models 0.4.3 / Vectors 0.1.30, against `gpt-5.1`. Every stage answered **100% of its items
locally**, so no stage is void: routing sent the work where the comparison assumed it would.

## The verdict, under the rule written in advance

| dataset | metric | routed | all-API | delta | 95% CI | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| SQuAD v2 dev (n=100) | exact match | 35.0 | 70.0 | **−35.0** | [−47, −23] | **REJECT** |
| HotpotQA distractor (n=100) | exact match | 37.0 | 60.0 | **−23.0** | [−35, −11] | **REJECT** |
| SNIPS 2017 (n=100) | label accuracy | 80.0 | 96.0 | **−16.0** | [−24, −9] | **REJECT** |
| TREC coarse (n=100) | label accuracy | 76.0 | 92.0 | **−16.0** | [−25, −8] | **REJECT** |

Four datasets, two task families, one direction. The hypothesis was that the local arms answer no
worse than the frontier model on the traffic the router gives them. **On public data they are 16 to
35 points worse, and the article's accuracy row cannot be filled with a tie.**

## Where the gap actually is, which the aggregate hides

SQuAD v2 was cut half answerable and half not, and the two halves do not behave alike:

| | n | exact match | token F1 | declined |
| --- | --- | --- | --- | --- |
| answerable, local 1B | 50 | **70.0** | 76.6 | 0 |
| answerable, gpt-5.1 | 50 | **70.0** | 86.6 | 2 |
| unanswerable, local 1B | 50 | 0.0 | 0.0 | **0 of 50** |
| unanswerable, gpt-5.1 | 50 | 70.0 | 70.0 | 35 of 50 |

**On a question a single short paragraph answers, the 1B model ties the frontier model exactly**:
70.0 against 70.0, trailing only on how tightly it cuts the span. The entire SQuAD gap is the other
half. Told in the prompt to reply exactly "I don't know" when the notes do not contain the answer,
the local arm did so **zero times in fifty**. It always produces something.

HotpotQA isolates the other axis, because none of its questions are unanswerable: ten paragraphs,
two of them relevant, an answer that needs both. There the local arm is **23 points behind with no
abstention involved**, on 2-word median answers with no truncation. That is reading, not format.

So three different things, not one:

1. **extraction from one short passage: no measured difference**
2. **multi-hop reading across ten passages: 23 points**
3. **knowing that the answer is absent: the local arm cannot do it at all**

And on closed decisions over many labels, **16 points on both datasets**, consistently.

## The first objection, measured rather than argued

"The fleet answered without the grounding policy the library ships." `apply_policy.java` re-decides
the same collected answers through `GroundedAnswerPolicy` -- no model runs, no prompt changes, so
it is comparable item by item. It makes things **worse**:

| | SQuAD v2 | HotpotQA |
| --- | --- | --- |
| local arm, raw | 35.0 | 37.0 |
| local arm through the policy | **27.0** | **10.0** |

The policy's decisions explain it. On SQuAD it returned `EXTRACTIVE_FALLBACK` for 27 items and
`MODEL_ANSWER_WITH_DERIVED_CITATIONS` for 71; on HotpotQA, 71 fallbacks. The fallback replaces the
model's answer with a span lifted from the retrieved text, which overwrites answers that were
already right. And it **never declined on an unanswerable item** -- its abstention comes from the
retrieval-score gate, which a topically relevant SQuAD paragraph passes, and from the model
explicitly abstaining, which this model never does.

Two honest limits on that arm: the policy was designed for prompts built by `GroundedRagPrompt`,
which instruct the model to cite, and it was applied here to answers shaped by this experiment's
prompt. And citation markup is stripped before scoring -- a decision made *after* seeing the policy
arm score 0.0 on answers that were otherwise correct, declared in `score.py`, and incapable of
flattering an arm that emits no citations.

## The one thing that worked: the decision arm knows when it is unsure

Harriet's confidence separates its own hits from its misses, by a lot on one dataset and a little on
the other: a median of **0.790** where it was right against **0.372** where it was wrong on SNIPS,
and **0.483** against **0.350** on TREC.

(An earlier revision of this file and of `fleet.java` reported that separation as "median 0.793 when
right, 0.379 when wrong ... over 200 items". Those were SNIPS's numbers wearing both datasets'
label. Pooled over all 200 items the medians are 0.637 and 0.368; per dataset they are the four
above. Both scripts now derive them from the arm's own rows -- `confidence_medians` in
`tools/article_figures.py` -- so the number in the prose is the number in the artifact.)

[ESCALATION.txt](ESCALATION.txt) sweeps a gate that takes the local answer above a threshold and the
provider's below it, computed over the already-collected answers rather than run:

| threshold from | applied to | local only | with the gate | all-API | escalated |
| --- | --- | --- | --- | --- | --- |
| SNIPS | TREC | 76.0 | **90.0** | 92.0 | 74% |
| TREC | SNIPS | 80.0 | **96.0** | 96.0 | 74% |

Then it was run, live, at the threshold the sweep chose on SNIPS -- `accuracy.java decide gated0-6`,
which asks Harriet first and the provider only below the threshold, so the arm is the mechanism and
not an arithmetic recombination of two other arms' files:

| public dataset | local only | live gated arm | all-API | escalated | verdict |
| --- | --- | --- | --- | --- | --- |
| SNIPS | 80.0 | **98.0** | 96.0 | 33% | +2.0 [+0.0, +5.0] ACCEPT |
| TREC | 76.0 | **90.0** | 92.0 | 74% | -2.0 [-6.0, +2.0] INCONCLUSIVE |

Three things in that table are worth more than the headline. The live arm **beat** the all-API arm
on SNIPS, which the simulation did not predict: the local model is right on items gpt-5.1 gets
wrong, so the combination is better than either side alone. The escalation rate is **33%** on SNIPS
and not the 74% the sweep estimated, because the sweep's rate came from TREC's much narrower
confidence separation. And TREC's -2.0 is exactly at the margin this project requires, with an
interval that still spans -6.0 to +2.0 -- a hundred items saying it cannot resolve two points, which
is reported rather than rounded into the claim.

The cost is the other half of the mechanism and it is in `MEASUREMENTS.json` per arm: parity on
these datasets is bought with provider calls, a third of them on one dataset and three quarters on
the other. The fleet ships with the gate on by default, because a declaration measured with it on is
a claim about a fleet that runs with it on, and `tools/parity_gate.py` fails the build if the
default and the measured threshold ever diverge.

## How the decision arm is wrong, which is the only part a fix can act on

`error_analysis.py` groups the wrong items by the confusion they are, from the arm's own rows, and
writes [ERROR-ANALYSIS.json](ERROR-ANALYSIS.json). Two confusions carry most of the loss:

| dataset | confusion | items | share of errors | median confidence |
| --- | --- | --- | --- | --- |
| TREC | `DESC` read as `ENTY` | 13 of 24 | 54% | 0.373 |
| SNIPS | `SearchScreeningEvent` read as `SearchCreativeWork` | 5 of 20 | 25% | 0.517 |
| SNIPS | `RateBook` read as `PlayMusic` | 5 of 20 | 25% | 0.360 |

TREC's block is one ambiguity repeated: "What is phosphorus?", "What are coral reefs?", "What is
pectin?" are definitions, which TREC labels `DESC`, and the arm reads them as entities. SNIPS's two
blocks are a schedule-versus-work confusion ("show me the schedule for Rat Rod Rockers!") and a
rating-versus-playing one ("mark this album a score of 5"), where the medium in the sentence pulls
harder than the verb.

Two things follow, and both matter to the fleet rather than only to the leaderboard.

**The errors are concentrated and they are describable in a sentence each**, which is what a rubric
is. This arm's accuracy is a function of the criteria the caller writes -- the first of the six
findings in the article is that the same question without a rubric comes back `p=0.503
confidence=0.00` -- so these three blocks are a tuning experiment with a clear hypothesis and a
clear risk of overfitting to the items that suggested it. **Not attempted here**, and the protocol
it would need is written down rather than improvised: rubrics rewritten from one dataset's first
half, scored on the other half and on the other dataset, with the rubric text committed before the
second run.

**The errors are mostly low-confidence**, which is why the escalation gate recovers as much as it
does: the median confidence on an error is below the 0.6 threshold in every block but one. The
exception is the one to watch -- "What is a shaman?" came back `HUM` at confidence **0.848**, above
any sane threshold, and a gate cannot catch a mistake the model is sure about. Calibration buys
back the uncertain errors and nothing else.

## What this changes in the article

The article's summary table said "not measured" on both sides of the accuracy row. It now says what
these four datasets say, which is not what the routing argument assumed. Specifically:

- The **cost and latency findings are untouched.** Nothing here measures either.
- The claim that most of that traffic "never needed a frontier model" is **not supported as a
  quality claim**. On the demo's own mix, the only axis these datasets can speak to is
  single-paragraph extraction, where the local arm ties. On harder public corpora it does not.
- The fleet has **no abstention path** on its grounding arm, and the policy that exists does not
  provide one. A deployment that cares about unanswerable questions needs something the demo does
  not have.
- A **confidence gate on the decision arm was built, run live and shipped on by default**: 98.0
  against gpt-5.1's 96.0 on SNIPS at 33% escalated, 90.0 against 92.0 on TREC at 74%. The price is
  stated in the same table as the gain.

## What this still cannot test

- One host, one afternoon, one set of pinned weights, n=100 per dataset. A screen, not a
  leaderboard: it can find a 16-point gap and cannot certify a 2-point one.
- Not the heartbeats, the chat turns or the appendix summary. Three of the article's six traffic
  kinds are untouched, and the two remote models were never compared against each other.
- Not the article's own ten prompts, deliberately: a corpus we wrote would score our own
  assumptions back to us.
- Not prompt engineering. Both arms got one prompt, written once, and a better prompt for the small
  model is a different experiment.
- Not a larger local model, which was the obvious next question and is answered in
  [grounding-arm-selection](../grounding-arm-selection/README.md) instead, on these same items with
  this same scorer.
