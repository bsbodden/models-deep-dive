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

Harriet's confidence separates its own hits from its misses: median **0.793** on the items it got
right, **0.379** on the ones it got wrong. [ESCALATION.txt](ESCALATION.txt) sweeps a gate that takes
the local answer above a threshold and the provider's below it, computed over the collected answers
rather than run:

| threshold from | applied to | local only | with the gate | all-API | escalated |
| --- | --- | --- | --- | --- | --- |
| SNIPS | TREC | 76.0 | **90.0** | 92.0 | 74% |
| TREC | SNIPS | 80.0 | **96.0** | 96.0 | 74% |

The gate recovers almost the whole gap, and the cross-dataset column is the one to read, because a
threshold chosen on the data that scores it is overfitting. But it escalates **74%** of the
decisions to do it, and 74% of that traffic going to a provider is most of the cost advantage for
that traffic. Calibration is real here and not sharp enough to be free.

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
- A **confidence gate on the decision arm is worth building and measuring properly**, not assuming:
  it worked here at a price worth stating.

## What this still cannot test

- One host, one afternoon, one set of pinned weights, n=100 per dataset. A screen, not a
  leaderboard: it can find a 16-point gap and cannot certify a 2-point one.
- Not the heartbeats, the chat turns or the appendix summary. Three of the article's six traffic
  kinds are untouched, and the two remote models were never compared against each other.
- Not the article's own ten prompts, deliberately: a corpus we wrote would score our own
  assumptions back to us.
- Not prompt engineering. Both arms got one prompt, written once, and a better prompt for the small
  model is a different experiment -- as is a larger local model, which is the obvious next question
  and is not answered here.
