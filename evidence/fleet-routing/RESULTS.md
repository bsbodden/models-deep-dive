# fleet.java verified run

Host: Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz, 12 logical CPUs, macOS 26.6.2, x86_64
Java: openjdk version "25.0.3" 2026-04-21 LTS
JBang: 0.141.0
Date: 2026-10-15T15:53:51Z
OPENAI_API_KEY: present for the keyed run below

## jbang fleet.java, three remote providers, released 0.1.59 / 0.3.60 / 0.1.30

Two OpenAI models and one Anthropic model share the fleet with four local models. Each provider has
its own endpoint, credential, auth header and response shape; each client normalises its own
provider into one `RoutingUsage`.

```
classifier: 10 tasks from google_embeddinggemma_300m_gguf_q8_0, 768-dimensional, similarity floor 0.60

WARMING                LOAD MS
smollm2-360m              2493
qwen3-0.6b                2439
llama-3.2-1b              3478
harriet-decisions        21685
total                    30095

PROMPT                                   CLASSIFIED           SELECTED            TOK      MS
ping                                     ~chat 0.48           smollm2-360m          1     169
    still here
still there?                             ~summarization 0.50  smollm2-360m          3     170
    still here
ok                                       ~reasoning 0.57      smollm2-360m          1     149
    still here
I was charged twice for my September …   ~tool-use 0.46       qwen3-0.6b            9    4288
    We'll check the details of your order to confirm if there was any issue with the payment. Let me know how we can assist you.
tell me more                             summarization        qwen3-0.6b            3    2267
    Of course, let me know how we can assist you with the next steps.
I was charged twice for my September …   ~tool-use 0.49       harriet-decisions    13   13910
    billing=true(p=0.91,c=0.58) queue=billing(p=0.99,c=0.95) urgency=this week(p=0.38,c=0.01)
When is a refund issued, and to which…   ~tool-use 0.51       llama-3.2-1b         12    2049
    A refund is issued to the original payment method within five business days.
What happens to a duplicate charge?      ~code 0.45           llama-3.2-1b          7    1716
    A duplicate charge is reversed automatically once billing reconciliation runs nightly.
Our refund policy promises five busin…   ~tool-use 0.52       gpt-5.1              55   10400
    There are two flows that can collide: 1. **Manual refund path** - You initiate a refund. - Policy promises: “Refund within five bus…
Summarise this appendix for the suppo…   ~summarization 0.54  claude-haiku-5-5     84    1131
    Refunds go to the original payment method within five business days, and duplicate charges are reversed automatically by the nightl…

== timing, warm ==
MODEL                CALLS  TOTAL MS   MEAN MS     SHARE
smollm2-360m             3       488       162      1.2%
qwen3-0.6b               2      6555      3277     15.9%
harriet-decisions        1     13910     13910     33.8%
llama-3.2-1b             2      3765      1882      9.1%
gpt-5.1                  1     10400     10400     25.3%
claude-haiku-5-5         1      1131      1131      2.7%
conversation wall clock: 41152 ms, of which 36249 ms (88.1%) was model calls
one-off load of the four local models: 30095 ms, paid once at startup, not per request

== ledger ==
10 prompts, 2 escalated to a remote provider, 8 answered on local weights
local ruler (qwen3-0.6b tokenizer): 139 of 188 input tokens were routed off this machine (73.9%)
provider ruler (gpt-5.1 reported): 204 input + 702 completion tokens billed
  the same prompt measured 139 tokens locally, so the two rulers differ by 65
completions generated on local weights: 123 tokens
REMOTE PROVIDER            IN   COMPLETION         COST
gpt-5.1                    61          598    $0.006056
claude-haiku-5-5          143          104    $0.000066
total                     204          702    $0.006123
had every prompt gone to gpt-5.1: $0.000235 of input alone, plus $0.001230 for the completions this machine produced for nothing
router-accounted spend: $0.006123 of the $0.05 shared budget
```

### What the second vendor's client needed that the first did not

Anthropic returns `content` as an array whose first block is `thinking`, with the answer in a later
`text` block, and reports `input_tokens`/`output_tokens` where OpenAI reports
`prompt_tokens`/`completion_tokens`. Reading `content[0].text` yields an empty string, which then
enters the ledger as a short answer rather than as an error. The client scans for the first `text`
block instead.

### The counterfactual, re-measured for ten prompts

```
classifier: 10 tasks from google_embeddinggemma_300m_gguf_q8_0, 768-dimensional, similarity floor 0.60

PROMPT                                               IN  COMPLETION
ping                                                  7          10
still there?                                          9          22
ok                                                    7          24
I was charged twice for my September order.          15         428
tell me more                                          9         109
I was charged twice for my September subscr…         19         625
When is a refund issued, and to which payme…         18         237
What happens to a duplicate charge?                  13         400
Our refund policy promises five business da…         61         430
Summarise this appendix for the support han…         89          70

== every prompt through gpt-5.1 ==
provider-reported: 247 input + 2355 completion tokens
at the declared $1.25/M in, $10.00/M out: $0.023859
Floor, not a ceiling: the grounded prompts are sent without their retrieved notes, which a
real all-remote implementation would have to include in the input.
```

$0.023859 all-remote against $0.006123 as routed: 74.3% less, a factor of 3.90. The eight prompts
that stayed local would have billed 1,855 completion tokens on gpt-5.1, or $0.018671 -- 78.3% of the
whole all-remote bill. Per completion token the two providers that did run differ by twenty times,
$10.00 against $0.50 per million, and Haiku answered 9.2 times faster than gpt-5.1.

## Walkthrough re-verified on the released libraries

Every script in `code/` was repinned to ModelJars 0.1.58, Models 0.3.59 and Vectors 0.1.30 and run
on the host above on 2026-10-15. All fourteen completed.

| script | outcome |
| --- | --- |
| chat.java | "Paris"; 26 prompt + 1 completion tokens |
| safetensors.java | "Paris" from the BF16 safetensors bundle |
| embed.java | 1,024-dimensional vector |
| rerank.java | correct ordering; Berlin population document first at 8.708755 |
| tools.java | tool calls applied: bedroom light 20, front door locked |
| composite.java | ANSWERABLE; physical prefix sharing true, 182 shared prefix tokens |
| decisions.java | billing? true p=0.920 c=0.60; queue billing p=0.991 c=0.95; urgency today |
| speech.java | 1,728 ms of audio at 32 kHz, RTF 1.433 |
| spring.java | "Paris" through the Spring AI adapter |
| route.java | discovery found 2 cached chat models and selected qwen3_0_6b_q4_0 |
| rag.java | retrieved doc-0 at 0.8581; policy returned EXTRACTIVE_FALLBACK |
| gemma.java | 768-dimensional vector under the publisher's prefix recipe |
| bonsai.java | verified 5.95 GB PTQ1_0 artifact; completion produced |
| fleet.java | routing ledger above |

### Three defects found by running them

`decisions.java` asked its yes-or-no question without a rubric and reported
`billing? false p=0.503 confidence=0.00` on evidence that is plainly about billing. Harriet's
javadoc records the difference a rubric makes: accuracy 0.8917 with one against 0.7500 without,
measured 2026-09-24 over 120 JevBench items on the same model and kernel. With rules attached to
each outcome the same question returns `true p=0.920 confidence=0.60`. The script was corrected.

In `fleet.java`, giving every prompt the same session id let a liveness check anchor the whole
conversation: the router adds a `switch-margin` of 0.05 to the incumbent so a conversation does not
hop between models, and the incumbent was the 360M model. Liveness checks now carry no session.

`gpt-5.1` is a reasoning model and bills its reasoning as completion tokens. The first keyed run
stopped on `RoutingBudgetExceededException: provider usage exceeded declared token bounds` against
a declared 512-token output ceiling. The ceiling is now 2,048 with a matching
`max_completion_tokens` on the request. Completion counts are not deterministic: the same prompt
billed 517, 563 and 611 completion tokens across three runs, while the input side held at 61.

The provider counted 61 input tokens for a prompt the local qwen3-0.6b tokenizer measured at 55, an
11% gap on one prompt. The ledger therefore reports the routed share on the local ruler and the
bill on the provider's, and never mixes them.

## Library findings, and what was done about each

Three gaps surfaced from writing an application against `models-router` rather than reading it.

**1. Usage cost was not reachable (fixed, additive).** The budget charges
`(input * inPrice + output * outPrice) / 1e6`, but `RoutingBudget.cost` is package-private, so
`fleet.java` reimplemented it to print its own ledger — two copies of one rule, free to drift.
`ModelCandidate.costOf(long, long)` now exposes it and the budget delegates to it.

**2. Classification confidence was invisible (fixed, additive).** `classify` returns a task or
null. At a 0.60 similarity floor, seven of the nine prompts in this run classified as null; at
0.35, "What happens to a duplicate charge?" came back as `code`. Either way the caller receives the
same null for "unlike every exemplar" and "weak but real match", with no way to tell them apart.
`PretrainedTaskClassifier.match(query)` now returns the nearest task and its similarity, and
`admits(match)` reports whether `classify` would have returned it.

**3. A completion that exceeds declared token bounds is billed and then discarded (not fixed —
contract decision).** `RoutingExecution.Attempt.settle` computes the cost, records it against the
budget, *then* throws `RoutingBudgetExceededException` if usage exceeded
`RoutingExecutionOptions.tokenBounds`. Because `ModelFleet.executeControlled` calls `settle` before
its `return new RoutedResult<>(value, ...)`, the completion already paid for never reaches the
caller. Observed on the first keyed run of `fleet.java`: a 512-token output bound against a
reasoning model that billed 517.

This is a fail-closed guard working as written, so changing it is a contract decision rather than a
bug fix. Three options:

- *Attach the artifact to the exception.* Keep failing, but let the caller recover what it was
  charged for. Non-breaking; preserves fail-closed semantics; slightly awkward to type on an
  exception.
- *Return the result with the violation recorded* in `RoutingAttempt` or on `RoutedResult`. Wastes
  nothing, but weakens the guard: a caller ignoring the field exceeds its bound silently.
- *Make bounds per-candidate.* The deeper issue is that one `(input, output)` pair is applied to
  every candidate, and a 24-token local acknowledgement and a reasoning model's 2,048-token
  completion cannot share a ceiling. This is the real fix and the largest change.

Recommended: the first as an immediate non-breaking step, and the third as the actual design, since
a single global output bound cannot describe a mixed fleet. Deferred to the library owner.
