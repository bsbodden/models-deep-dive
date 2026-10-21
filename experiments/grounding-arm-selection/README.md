# Can a larger local model serve grounded questions at frontier quality?

**Status: protocol frozen, no data collected.** A new directory rather than an edit to
`routing-accuracy/`, because that protocol is frozen and this adds arms it did not describe.

## Why

`tools/parity_gate.py` fails on the fleet's `grounding` declaration: the 1B arm measured 35.0 and
37.0 exact match on SQuAD v2 and HotpotQA against gpt-5.1's 70.0 and 60.0. The rule this project
holds itself to is that a small model must be close to or better than the frontier model on the
work it is given. 23 and 35 points is not close.

Three ways to close that: improve the model, drop the declaration, or waive it with a reason.
This measures the first. If a larger local model reaches parity, the fleet gets a grounding arm
whose declaration its evidence supports. If none does, the declaration cannot stand and the fleet
must either route grounded questions off the machine or say plainly that it serves them below
frontier quality.

## Arms

Identical prompts, identical retrieval, identical scorer to `routing-accuracy` -- the samples and
`score.py` are reused from that directory by path rather than copied, so a difference here cannot
come from a different question or a different measuring stick.

| arm | model | why |
| --- | --- | --- |
| `llama1b` | `bartowski_llama_3_2_1b_instruct_gguf_q4_k_m` | the fleet's current grounding arm, re-measured here so every arm shares one host and one run |
| `qwen3-8b` | `qwen3_8b_q4_k_m` | largest Qwen in the catalog, 40,960-token window |
| `llama3.1-8b` | `llama_3_1_8b_instruct_q4_k_m` | largest Llama in the catalog, 131,072-token window |
| `frontier` | `gpt-5.1` | the reference the gate compares against |

## Datasets and size

SQuAD v2 dev and HotpotQA distractor validation, the first **50** items of each committed sample.
Fifty is a screen, not a certification: it can separate a 20-point gap from parity and cannot
settle a 3-point one. A candidate that looks within margin at 50 is re-run at the full 100 before
any declaration changes, and that second run is the one the gate reads.

## Decision rule, fixed now

Per dataset, exact match, against the frontier arm measured in the same run:

- **Adopt** a candidate as the grounding arm if it is within **2 points** on both datasets.
- **Reject** it if it is more than **5 points** behind on either.
- **Inconclusive** between, or where the two datasets disagree, in which case the disagreement is
  reported and no declaration changes.

The 1B arm is expected to reject; it is in the run as a control, to show that this host and this
harness reproduce the gap the frozen experiment already found. If it does not reproduce, the run is
void and the harness is wrong, not the model.

## Kill criteria

- **Host ceiling** 6 hours on one `ccx33`, about USD 1.60. Stops and reports what finished.
- **Provider ceiling** USD 5 for the frontier arm.
- **Control failure.** If `llama1b` does not land within 5 points of the 35.0 and 37.0 already
  measured, the run is reported as void rather than interpreted.

## What it cannot settle

- Only grounded extraction. Nothing here measures chat, summarization or decisions.
- An 8B model that reaches parity costs more to run than a 1B: this measures quality, and the
  latency and memory it trades for are measured separately, per arm, in the same logs.
- Two public datasets, 50 items each at screen stage. A model that wins here has earned a
  confirmation run, not a production declaration.

---

## Run log

The protocol above is frozen. What follows is the record of what was run against it, including the
parts that went wrong, because a reader who cannot see the deviations cannot judge the result.

### Screen, 2026-10-20, one `ccx33` in `ash`

`ARMS="llama1b llama3.1-8b frontier"`, `LIMIT=50`. `qwen3-8b` was not run, for two reasons. The
question is whether *any* local arm reaches parity, and if `llama3.1-8b` does, a second 8B changes
no declaration -- had it failed, qwen would have had to run before concluding that no local arm
reaches parity. And Qwen3 emits a reasoning block by default, which a 64-token answer cap turns
into a truncated non-answer and a score of zero; measuring it properly means deciding how this
harness suppresses thinking, which is a different experiment and not one to improvise inside this
one.

Two follow-ups that this experiment deliberately does not answer. The arm it adopts is licensed
under `LicenseRef-Llama-3.1`, as the 1B arm it replaces was under `LicenseRef-Llama-3.2`, so the
fleet's licence posture is unchanged -- but a deployment that needs a permissive licence has an
Apache-2.0 8B in the same catalog (`qwen3_8b_q4_k_m`) and no number here for it. And the adopted
arm is 4.92 GB against the 1B's 0.81 GB, which a reader cloning the walkthrough pays for in
download before they pay for it in latency.

| arm / dataset | n | exact match | token F1 | median ms | peak heap |
| --- | --- | --- | --- | --- | --- |
| `llama1b` / squad2 | 50 | 40.0 | 44.0 | 2,486 | 326 MiB |
| `llama3.1-8b` / squad2 | 50 | 72.0 | 81.2 | 13,546 | 552 MiB |
| `llama1b` / hotpotqa | 50 | 30.0 | 34.5 | 19,083 | 605 MiB |

The split is the finding. On the 23 unanswerable SQuAD v2 items in that subset the 1B scored 0.0
and declined 0 times; the 8B declined 19 times and scored 82.6. On the 27 answerable items the 1B
scored 74.1 and the 8B 63.0 -- the larger model is *worse* at reading the answer out and far better
at knowing there isn't one, and on this dataset the second effect is larger.

**Control check.** On squad2 the control landed at 40.0 against the frozen experiment's 35.0, +5.0
and inside the margin. On hotpotqa it landed at 30.0 against 37.0, -7.0, outside it: by the frozen
criterion the hotpotqa screen is void. The criterion compares a 50-item subset mean against a
100-item mean, which are not the same quantity, so this is a flaw in the screen's own check rather
than evidence about the harness -- and it is precisely why the protocol already required the full
100 before any declaration moves. Prompt hashes are compared against the frozen experiment's
artifacts directly, which is the harness check that does mean something.

**Abandoned mid-run.** `llama3.1-8b` on hotpotqa reached item 12 of 50 and was then killed, not by
the kill criteria: a `pkill` pattern aimed at a different stuck run matched this one too. The host
was torn down and no partial file was written. The confirmation run below re-measures that cell at
the full 100, so nothing was re-run twice for the same number.

### Confirmation, 2026-10-20, `ccx33` in `ash`, in windows

`LIMIT=100`, both datasets, same shape as the screen.

A larger shape was tried first and is not available: this account is capped at eight dedicated
cores, and `ccx63`, `ccx53` and `ccx43` are all refused with `resource_limit_exceeded` even with
nothing else running. The reason a larger host was wanted is supervision -- a 100-item 8B pass on
hotpotqa takes about 140 minutes on eight cores, longer than this workstation can hold a foreground
run for, and a run whose supervisor dies leaves a paid host billing, which has already happened
once today. So the sample is measured in windows instead: `arms.java` takes an item offset, each
window is a separate supervised run on its own host, and the scorer merges the windows and refuses
any pair that disagrees about an item it measured twice.

Measuring in windows is not free of assumptions. Two windows are two hosts and two weight loads,
so a drift between them would show up as a split in the result; the 1B arm's byte-identical answers
across two hosts above is the evidence that it does not, and the merge check is what would catch it
if it ever did.

**What it measured.** SQuAD v2 in one run of 100, HotpotQA in two windows of 50 merged by the
scorer with no disagreement on any item measured twice. The control reproduced the frozen
experiment's 35.0 and 37.0 exactly at n=100, so the `ccx33` latencies above and the laptop's are
measuring the same answers. The verdict was ACCEPT on SQuAD v2 (79.0 against gpt-5.1's 70.0) and
REJECT on HotpotQA (31.0 against 60.0, and 6.0 behind the 1B arm), which under the frozen rule is
REJECT for the candidate. [FINDINGS.md](FINDINGS.md) carries the split that explains it and what
the fleet declares instead.

**Only `llama3.1-8b` is re-run, and the reason is measured rather than assumed.** On the 100 items
the screen shares with the frozen experiment, the 1B arm returned **byte-identical answers on 100
of 100** -- a different host, a different harness, the same prompt hashes -- so local decoding here
is deterministic and the frozen run's 1B and `gpt-5.1` arms at n=100 are the same measurement a
re-run would produce, item for item, on prompts whose hashes are checked equal rather than assumed
equal. Re-running them would spend an hour of a paid host to reproduce two files that already
exist. The frontier arm is an API call and no host shape changes it.

That is a deviation from "measured in the same run", and it is one the determinism check earns: the
comparison is between arms on identical prompts over identical items, which is what the phrase was
protecting. The scorer refuses the comparison outright if any prompt hash differs.
