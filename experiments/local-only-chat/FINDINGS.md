# Which local arm may serve a turn the boundary forbids sending anywhere

The fleet's chat prompts carry `dataBoundary(LOCAL_ONLY)`, so this was never "is a small model as
good as gpt-5.1" — it was "which local arm serves these turns best". The answer changed the fleet:
the arm it shipped declines most of what it is asked, and the arm that replaced it is within two
points of the frontier model on both datasets. Every number is in [RESULTS.json](RESULTS.json),
derived from the committed rows by [score_chat.py](score_chat.py) with the scorer frozen in
`../routing-accuracy`.

## The headline

Token F1, 100 items per dataset, identical prompts across arms with the hashes checked equal:

| arm | CoQA | QuAC | declined (CoQA / QuAC) | median per answer |
| --- | --- | --- | --- | --- |
| `small` — Qwen3 0.6B, the arm the fleet shipped | **14.7** | **27.1** | **62 / 72** of 100 | 9.1 s / 13.8 s |
| `llama1b` — Llama 3.2 1B | 57.8 | 28.0 | 3 / 19 | 3.6 s / 6.2 s |
| `llama3.1-8b` — Llama 3.1 8B | **82.2** | **48.1** | 1 / 16 | 33.0 s / 48.6 s |
| `frontier` — gpt-5.1 | 83.9 | 49.0 | 2 / 34 | 1.1 s / 1.1 s |

The 8B arm is **1.6 points** off the frontier model on CoQA and **0.9** on QuAC. Both are inside the
two points this project requires of a declared capability, so the declaration rests on the frontier
basis rather than on the weaker "best among local arms" one the boundary would have allowed.

## What the 0.6B was actually doing

It was refusing. On CoQA it answered "I don't know." to 62 of 100 items whose answer is in the
passage in front of it; on QuAC, 72 of 100. Its answerable-half F1 is 13.8 on CoQA against the 8B's
82.1. That is not a cheap arm trading quality for latency, it is an arm that mostly does not answer,
and the limp replies in this article's own run record -- "We'll check the details of your order to
confirm if there was any issue with the payment" -- were it standing one notch away from refusing
outright.

Four earlier revisions of the article shipped that arm with a hand-typed quality of 0.45 and then
with no number at all. Neither state was a measurement. This is the measurement.

## What it costs to fix

| | 0.6B | 8B |
| --- | --- | --- |
| weights | 0.43 GB | 4.92 GB |
| median CoQA answer | 9.1 s | 33.0 s |
| median QuAC answer | 13.8 s | 48.6 s |
| peak heap | 1,258 MiB | 1,144 MiB |

Three to four times the latency per turn on eight dedicated cores, and eleven times the download.
The fleet pays it because the alternative is an arm that declines two thirds of its traffic, and
because the same arm already serves grounded extraction -- so the fleet holds one 8B rather than one
8B and one 0.6B. The 0.6B stays loaded for its tokenizer, which is the ruler every token count in
the article is measured with, and declares no capability so the router can never select it.

## QuAC is hard for everyone, and that is in the table on purpose

gpt-5.1 scores 49.0 on QuAC and declines 34 of 100. The dataset has 18 genuinely unanswerable turns
in this sample and an information-seeking setup where the asker cannot see the passage, so low
scores there are a property of the task rather than of the arm. The comparison still works -- every
arm met the same items -- but QuAC's absolute numbers should not be read as "half the answers were
wrong".

## What this cannot settle

- **Conversational question answering is not all of chat.** Tone, instruction following, refusal
  behaviour and multi-turn task completion are not measured here, and the declaration this evidence
  supports is narrower than the word on the capability. It is recorded that way in
  `PARITY-BASIS.json` rather than left for a reader to infer.
- **Two datasets, one shape.** Both give the model a passage and a dialogue history. Nothing here
  measures a chat turn with no passage at all, which is what the demo's two prompts actually are.
- **The 0.6B's refusals were not prompt-engineered away.** One prompt, written once, naming the
  abstention string -- the same prompt every arm got. A prompt that discourages declining would
  probably raise its score and is a different experiment.
- **Latency is `ccx33` latency.** Eight dedicated vCPU, every local arm on one shape. The frontier
  arm's milliseconds are a round trip from a laptop and are not comparable with the rest.
