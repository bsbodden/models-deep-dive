# Can rubric text fix the decision arm's errors, without touching the model?

**Status: protocol frozen, baseline not yet collected, no rubric written.** Nothing in this
directory has been tuned. The held-out samples are cut and the decision rules below are fixed; the
intervention comes after.

## Why

[The error analysis](../routing-accuracy/ERROR-ANALYSIS.json) says the decision arm's mistakes are
not spread thin. Three confusions carry most of them:

| dataset | confusion | items | share of that dataset's errors | median confidence |
| --- | --- | --- | --- | --- |
| TREC | `DESC` read as `ENTY` | 13 of 24 | 54% | 0.373 |
| SNIPS | `SearchScreeningEvent` read as `SearchCreativeWork` | 5 of 20 | 25% | 0.517 |
| SNIPS | `RateBook` read as `PlayMusic` | 5 of 20 | 25% | 0.360 |

Each one is describable in a sentence — "a question asking what something *is* wants a description,
not an entity"; "a request for showtimes or a schedule is a screening event, not a search for a
work"; "a numeric rating is a rating whatever medium it names" — and a sentence per outcome is
exactly what Harriet takes. The article's first finding is that the same question without a rubric
is a coin flip, so rubric text is the arm's dominant input. The question here is whether it is still
the dominant input *after* a reasonable rubric already exists, and whether a rubric written against
observed errors generalises or merely fits them.

## The samples, and why they are new

`sample-snips-heldout.json` and `sample-trec-heldout.json`, 100 items each, cut by
[`cut_heldout.py`](cut_heldout.py) from the same pinned downloads the measured experiment used —
SNIPS re-fetched and verified against the SHA-256 that experiment recorded, TREC read from its
committed raw and hashed the same way. Every item in the measured sample is excluded by id, so the
two sets share nothing.

**The first hundred cannot be the test set.** Their errors have been read item by item, by
`error_analysis.py` and by me, and the three confusions above were named from them. A rubric written
from that reading and scored on those same items would report how well it fits errors it was shown.
So: **the measured hundred are the development set, and these hundred decide.**

One honest limit of that arrangement: nobody has looked at the held-out errors, and nobody will
before the intervention is written. The baseline below is collected as an aggregate, and its
per-item mistakes stay unread until the test run is scored.

## Arms and what varies

Only the rubric text varies. Same model, same composite, same prompt template, same answer spaces,
same scorer — `accuracy.java` takes `-Daccuracy.rubrics=<path>` for exactly this, so one sample is
measured against two rubric files rather than one sample being copied to carry a second rubric.

| arm | rubrics | what it answers |
| --- | --- | --- |
| `routed` baseline | `../routing-accuracy/rubrics-<dataset>.json` | what the shipped rubric scores on items nobody tuned against |
| `routed` tuned | `rubrics-<dataset>-tuned.json` | what a rubric written from development errors scores on the same items |

The local-only arm is the one that varies, because that is where rubric text acts. The escalation
gate's accuracy follows from it and is reported, not optimised.

## Decision rule, fixed now

On the held-out hundred, per dataset, label accuracy:

- **Adopt** the tuned rubric if it is **not worse on either dataset** and better by at least **3
  points on at least one**. Three points is one standard error's worth at n=100 near 80% accuracy,
  which is the smallest difference this sample can see.
- **Reject** it if it is worse by more than 3 points on either dataset. A rubric that trades one
  confusion for another is not an improvement, and the confusion table is reported either way.
- **Inconclusive** otherwise, and the rubric does not ship.

Two numbers are reported beside the headline, and neither can change the verdict:

- **The development-to-held-out gap.** Accuracy on the hundred the rubric was written from, minus
  accuracy on the hundred it was not. That difference is the overfitting estimate, and a large one
  is the finding even when the held-out number improves.
- **The confidence separation**, median confidence where the arm was right against where it was
  wrong, per dataset. A rubric that raises accuracy while flattening that separation makes the
  escalation gate worse at the job it exists for, which the fleet pays for in escalations.

## Kill criteria

- No host. This is local inference on this workstation and a provider call only if a gated arm is
  measured; the laptop's latencies are not a measurement and are not reported, exactly as in
  `../local-only-chat`.
- If the baseline on the held-out hundred differs from the measured hundred by more than **8
  points** on either dataset, the two samples are not interchangeable and the experiment stops
  rather than interpreting a difference between populations as a difference between rubrics.

---

## Baseline, collected 2026-10-20, before any rubric was written

| dataset | held-out accuracy | development accuracy | held-out − development | confidence right / wrong | below the 0.6 gate |
| --- | --- | --- | --- | --- | --- |
| SNIPS | **78.0** | 80.0 | -2.0 | 0.797 / 0.486 | 45% |
| TREC | **78.0** | 76.0 | +2.0 | 0.490 / 0.350 | 80% |

Both gaps are two points, well inside the eight the kill criterion allows, so **the two samples are
interchangeable** and a difference measured here can be attributed to the rubric rather than to the
draw. That was the one thing that had to be true before the experiment could mean anything, and it
is the reason the baseline was collected before the intervention rather than alongside it.

The confidence separation reproduces the shape the development set showed: wide on SNIPS (0.797
against 0.486) and narrow on TREC (0.490 against 0.350), which is why TREC's gate escalates 80% of
its items against SNIPS's 45%. Any rubric that improves accuracy by flattening that separation is
making the escalation gate worse, which is why it is in the table.

`score_rubrics.py` prints these three numbers and refuses to print the held-out set's per-item
mistakes unless asked with `--confusions`. Nobody has asked yet, and nobody should until the
intervention is written and scored.

## What this cannot settle

- One model. Nothing here says whether another decision model needs the same rubric.
- One rubric revision. A second attempt informed by the held-out errors would be fitting the test
  set, so if this one is inconclusive the answer is a third sample, not a second guess.
- Not the fleet's own rubrics. The billing, queue and urgency rules in `fleet.java` are a different
  set of sentences on a different task, and no public dataset scores them. What transfers is the
  method, not the text.
