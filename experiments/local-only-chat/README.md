# Which local model may serve the fleet's local-only chat turns?

**Status: protocol frozen, no data collected.** Written before `fetch_datasets.py` is run, and
committed before any arm is measured.

## Why

`tools/parity_gate.py` fails on two of the `small` arm's declarations:

```
small       chat          -        -         -       -  UNMEASURED
small       summarization -        -         -       -  UNMEASURED
```

`summarization` needs no experiment. The fleet's only summarization prompt is the long appendix,
which exceeds every local arm's context window, so the router has never once sent summarization to
a local model (`code/fleet.java`, the `longDocument` requirement). The declaration is surplus and
is being deleted rather than measured: an application should not claim what it never exercises.

`chat` is different. Two prompts in the demo session -- a billing complaint and the follow-up
"tell me more" -- carry `requireCapability("chat")` **and** `dataBoundary(LOCAL_ONLY)`, and
`qwen3-0.6b` serves both. That is a real claim about a 0.6B model, and nothing has measured it.

## The comparison basis, decided before the data

Every other declaration in this fleet is measured against gpt-5.1, because the fleet may send that
work to gpt-5.1. These two prompts it may not: the customer's billing complaint is marked
`LOCAL_ONLY`, and under that boundary the frontier model is not a candidate the router is allowed
to pick. The alternative to the 0.6B is not gpt-5.1; it is a different local model, or no service.

So this experiment reports **two** numbers and neither is optional:

1. **The ceiling gap.** gpt-5.1 is measured on the same items. Whatever the gap is, it is published
   as a number -- in `FINDINGS.md` and in the article -- as the price of the boundary. A fleet that
   drops the boundary should know what it is buying back.
2. **The declaration.** `chat` is declared for the local arm the measurement puts first. An arm
   more than **2 points** of token F1 behind the best local arm does not carry the declaration.

Both are reported for both datasets. If the two datasets disagree about the ordering, the
disagreement is reported and the declaration does not move.

## Arms

| arm | model | coordinate | why |
| --- | --- | --- | --- |
| `small` | Qwen3 0.6B q4_0 | `ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1` | the arm the fleet declares today |
| `llama1b` | Llama 3.2 1B q4_k_m | `bartowski.llama-3.2-1b-instruct-gguf.q4_k_m:3.2.0-q4_k_m.1` | the next size up, already in the fleet |
| `llama3.1-8b` | Llama 3.1 8B q4_k_m | `bartowski.meta-llama-3.1-8b-instruct-gguf.q4_k_m:3.1.0-q4_k_m.2` | the largest Llama in the catalog |
| `frontier` | gpt-5.1 | provider API | the ceiling, not a candidate under `LOCAL_ONLY` |

## Datasets and metric

Two, because one dataset has already produced a confident wrong answer in this project's history:

- **CoQA** dev v1.0 (`downloads.cs.stanford.edu/nlp/data/coqa/coqa-dev-v1.0.json`). Free-form
  conversational question answering over a passage, with the dialogue history each turn depends on.
- **QuAC** val v0.2 (`s3.amazonaws.com/my89public/quac/val_v0.2.json`). Information-seeking
  dialogue over Wikipedia, including turns whose gold answer is that the passage cannot answer them
  (`CANNOTANSWER`), which is the behaviour a support arm needs and the 1B arm has already been
  measured failing at.

100 items each, cut with this project's seed from the pinned downloads and committed. Each item
carries the passage, the preceding turns, the question and the gold answers, so every arm answers
the same conversation.

**Headline metric: token F1**, which is both datasets' own published metric; free-form dialogue
answers are not spans and exact match is the wrong stick for them. Exact match is reported beside
it. Scoring is `../routing-accuracy/score.py`, imported rather than copied, including its
abstention handling for unanswerable turns.

## Hosts, and which number came from which

**The three local arms run on one idle Hetzner `ccx33`** (8 dedicated vCPU), one after another, so
their per-item latencies can be read against each other and against the neighbouring experiment's.

**The `frontier` arm runs from this workstation**, because it is an HTTP call: the host a provider
request leaves from does not change the answer, and its latency is reported as what it is -- a
round trip from a laptop on a domestic connection, not a datacentre-to-datacentre number.

An earlier attempt ran the local arms here too and was abandoned rather than reported. This
workstation (`Intel Core i7-9750H`, 6 physical cores, 12 logical, 32 GB) answered the first five
CoQA items with the 0.6B model in 13.9, 15.1, 16.4, 18.9 and 31.0 seconds, and 22 to 25 seconds
each while it was also compiling; the `ccx33` answers the same hundred items at a median of **9.1
seconds**. So the honest size of the gap is roughly **two-fold**, not the ten-fold one an earlier
note here claimed by comparing this laptop's CoQA latencies against the *other* experiment's SQuAD
v2 latencies for a different model on different prompt lengths. Two-fold is still enough to make
every local arm look uniformly slow for reasons that have nothing to do with which arm should serve
chat, and the laptop's numbers moved by half again depending on what else it was doing, which is
the real reason they are not the ones reported.
The answers themselves were identical, which is the point of the next paragraph.

Local decoding here is deterministic across machines, and that is measured rather than assumed,
twice. The neighbouring experiment re-ran the 1B arm on a `ccx33` against the same 100 items this
workstation had already answered, prompt hashes checked equal, and got **byte-identical answers on
100 of 100**. And the five CoQA items this workstation answered with the 0.6B arm before the run
moved to the host came back identical there too, at three threads here against eight there. So
quality is a property of the weights and the prompt, both of which are pinned, and the host decides
only how long it takes.

## Kill criteria

- **Host ceiling** 6 hours on one host. Stops and reports what finished.
- **Provider ceiling** USD 5 for the frontier arm.
- **Harness check.** Every arm answers byte-identical prompts; the scorer refuses the run if any
  arm's prompt hashes differ.

## What it cannot settle

- Conversational question answering is not all of chat. Tone, refusal behaviour, instruction
  following and multi-turn task completion are not measured here, and the declaration this
  experiment supports is therefore narrower than the word "chat" suggests. Stated here because the
  gate reads a capability name and the name is broader than the evidence.
- Nothing here measures the escalation mechanism that closed the decision arm's gap: under
  `LOCAL_ONLY` there is nowhere to escalate to.
- 100 items per dataset separates a 10-point ordering from a tie. It does not settle 2 points, and
  a 2-point ordering is reported as a tie, which is what the decision rule above says.
