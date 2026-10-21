# What the arm selection said

The hypothesis was that a larger local model has the capability the 1B arm lacked: knowing when the
answer is not in the passage. **It does, and it does not generalise, and the second half cost this
fleet a claim.** Every number below is in [RESULTS.json](RESULTS.json), derived from the committed
rows by [score_arms.py](score_arms.py) with the scorer frozen in `../routing-accuracy`.

## The verdict, under the rule written before the first call

| arm | dataset | exact match | gpt-5.1 | difference | verdict |
| --- | --- | --- | --- | --- | --- |
| `llama3.1-8b` | SQuAD v2 (n=100) | **79.0** | 70.0 | +9.0 [+1.0, +17.0] | ACCEPT |
| `llama3.1-8b` | HotpotQA (n=100) | **31.0** | 60.0 | -29.0 [-40.0, -18.0] | REJECT |
| `llama1b` | SQuAD v2 (n=100) | 35.0 | 70.0 | -35.0 [-47.0, -23.0] | REJECT |
| `llama1b` | HotpotQA (n=100) | 37.0 | 60.0 | -23.0 [-35.0, -11.0] | REJECT |

ACCEPT on one dataset and REJECT on the other is **REJECT** for the candidate: the rule required
within two points on both. The 8B arm does not carry `grounding`.

**The control reproduced exactly.** The 1B arm scores 35.0 and 37.0 at n=100 -- the frozen
experiment's numbers to the decimal, on the same items, with prompt hashes checked equal -- so the
harness and both hosts are sound and the comparison is between arms rather than between runs. At
n=50 the same check was off by 7 points on HotpotQA, which is what a 50-item subset mean does
against a 100-item mean and why the protocol required the full sample before any declaration moved.

## Where the 8B wins, and what it is winning at

On SQuAD v2, split by whether the question has an answer at all:

| half | `llama1b` | `llama3.1-8b` | gpt-5.1 |
| --- | --- | --- | --- |
| answerable (n=50) | 70.0, declined 0 | 72.0, declined 3 | 70.0, declined 2 |
| unanswerable (n=50) | **0.0**, declined 0 | **86.0**, declined 43 | 70.0, declined 35 |

The reading is a tie three ways. The entire difference is the second row: the 1B arm never once said
"not in the notes" across fifty questions whose answer was not in the notes, with the prompt naming
the exact string to say it with. The 8B says it 43 times out of 50 and beats the frontier model at
it, which declined 35.

## Where it loses, and why that is the more interesting half

HotpotQA has ten paragraphs per question, a two-hop answer, and **no unanswerable questions at all**.

| arm | exact match | declined | median per answer | peak heap |
| --- | --- | --- | --- | --- |
| `llama1b` | 37.0 | 0 of 100 | 12,898 ms | — |
| `llama3.1-8b` | 31.0 | **33 of 100** | 73,180 ms | 1,915 MiB |
| gpt-5.1 | 60.0 | 10 of 100 | 638 ms | — |

The 8B arm declines a third of the questions on a dataset where every question has an answer, and
lands six points **behind** the model it was brought in to replace. The behaviour that won the first
dataset is the behaviour that loses the second.

So calibrated abstention is not a capability a model has or lacks. It is a trade between two kinds
of error -- answering when it should decline, declining when it should answer -- and which way the
trade pays is a property of what retrieval hands the model, not of the model. One short passage with
half the questions unanswerable: worth 44 points over the 1B. Ten paragraphs with none
unanswerable: costs 6.

## What the fleet does about it

`grounding`, as this project's gate defines it, is a claim no model in this catalog can carry: the
two datasets disagree about which local arm is better and neither arm is within 23 points of the
frontier model on multi-hop. The fleet stopped making that claim. It declares
`grounding-single-passage` on the 8B arm instead, because that is the shape its retrieval produces
-- three one-sentence notes indexed, the top two retrieved -- and `tools/parity_gate.py` maps the
narrow name to SQuAD v2 while still holding the broad name to both datasets. The narrowing is a
smaller claim, not a softer gate, and a deployment whose retrieval returns ten paragraphs cannot
reuse the declaration.

The cost of the arm it did adopt is in the same tables and is not small: 4.92 GB of weights against
0.81, 13.5 s per grounded answer against 1.9 s on eight dedicated cores, and 1,915 MiB of peak heap
against the 1B's few hundred.

## What this cannot settle

- **Two datasets, one shape each.** SQuAD v2 is single-passage with abstentions; HotpotQA is
  multi-hop without them. Nothing here separates "multi-hop is hard" from "ten distractor
  paragraphs are hard", and a dataset with both properties would be the way to.
- **No prompt engineering.** Both arms got one prompt, written once, asking for the shortest exact
  phrase and naming the abstention string. A prompt that discourages declining would move the
  HotpotQA number and might move SQuAD v2's the wrong way; that is the obvious next experiment.
- **`qwen3-8b` was not run.** The frozen arms table named it and the run log says why it was
  skipped: Qwen3 emits a reasoning block by default, which a 64-token answer cap turns into a
  truncated non-answer. An Apache-2.0 8B with the same measurement would be worth having, and this
  is not it.
- **One quantisation, one size, one family at 8B.** This says what `Meta-Llama-3.1-8B-Instruct` at
  Q4_K_M does on these two datasets. It does not say what 8B models do.
