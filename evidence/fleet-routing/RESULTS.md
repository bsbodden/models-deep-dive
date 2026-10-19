# fleet.java verified run

Host: Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz, 12 logical CPUs, macOS 26.6.2, x86_64
Java: openjdk version "25.0.3" 2026-04-21 LTS
JBang: 0.141.0
Date: 2026-10-16, both arms in one session after the host settled
Load average: 2.77 at the start of the routed arm, 5.42 after it (the fleet's own four resident
models), 3.71 after the all-remote arm
OPENAI_API_KEY and ANTHROPIC_API_KEY: present for the keyed runs below

Raw artifacts: `routed.log`, `all-remote.log`. Every derived figure below and in the article comes
from `tools/derive_fleet_figures.py`, which reads those two logs and `code/fleet.java`; its output
is `DERIVED.txt`. No figure in either document is hand-computed.

## jbang fleet.java, three remote providers, released 0.1.61 / 0.4.3 / 0.1.30

Two OpenAI models and one Anthropic model share the fleet with four local models. Each provider has
its own endpoint, credential, auth header and response shape; each client normalises its own
provider into one `RoutingUsage`.

```
classifier: 10 tasks from google_embeddinggemma_300m_gguf_q8_0, 768-dimensional, similarity floor 0.60

PROMPT                                               IN  COMPLETION
ping                                                  7          10
still there?                                          9          22
ok                                                    7          24
I was charged twice for my September order.          15         422
tell me more                                          9         100
I was charged twice for my September subscr…         19         813
When is a refund issued, and to which payme…         18         300
What happens to a duplicate charge?                  13         476
Our refund policy promises five business da…         61         437
Summarise this appendix for the support han…         89          72

== every prompt through gpt-5.1 ==
provider-reported: 247 input + 2676 completion tokens
at the declared $1.25/M in, $10.00/M out: $0.027069
Floor, not a ceiling: the grounded prompts are sent without their retrieved notes, which a
real all-remote implementation would have to include in the input.
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

PROMPT                                               IN  COMPLETION       MS
ping                                                  7          10     2639
still there?                                          9          22     1360
ok                                                    7          23     1129
I was charged twice for my September order.          15         411     6294
tell me more                                          9         134     1883
I was charged twice for my September subscr…         19         513     4688
When is a refund issued, and to which payme…         18         289     3437
What happens to a duplicate charge?                  13         356     3908
Our refund policy promises five business da…         61         406     5135
Summarise this appendix for the support han…         89          81     1497

== every prompt through gpt-5.1 ==
provider-reported: 247 input + 2245 completion tokens
at the declared $1.25/M in, $10.00/M out: $0.022759
conversation wall clock: 31983 ms, of which 31970 ms (100.0%) was model calls
No local weights are loaded, so there is no startup cost to amortise.
Floor, not a ceiling: the grounded prompts are sent without their retrieved notes, which a
real all-remote implementation would have to include in the input.
```

$0.022759 with no router against $0.005773 as routed: 74.6% less, a factor of 3.94. The eight
prompts that stayed local would have billed 1,758 completion tokens on gpt-5.1, or $0.017701 --
77.8% of the whole no-router bill. Wall clock went the other way: 31,983 ms with no router against
36,452 ms routed, 14% slower, before the 27,709 ms of one-off model loading. Per completion token the two providers that did run differ by twenty times,
$10.00 against $0.50 per million, and Haiku answered 5.2 times faster than gpt-5.1.

**These are one measured pair, and the pair moves.** gpt-5.1 bills its reasoning as completion
tokens and does not spend the same amount twice, which swings both arms. Four pairs measured on the
same ten prompts at the same declared prices:

| date | versions | all-remote | as routed | saving | factor |
| --- | --- | --- | --- | --- | --- |
| 2026-10-15 | 0.1.59 / 0.3.60 | $0.023859 | $0.006123 | 74.3% | 3.90 |
| 2026-10-16 | 0.1.60 / 0.4.0 | $0.022889 | $0.006993 | 69.4% | 3.27 |
| 2026-10-16 | 0.1.60 / 0.4.1 | $0.027069 | $0.005773 | 78.7% | 4.69 |
| 2026-10-16 | 0.1.60 / 0.4.1, baseline re-run with timings | $0.022759 | $0.005773 | 74.6% | 3.94 |

The article quotes the last row, because that is the pair measured together against the released
libraries. The honest reading of the three is that the saving on this workload is somewhere around
70-80% and a factor of three to five; a single figure quoted to four decimal places is precise about
one run and not about the effect. Nothing here is averaged, and no run was selected for being
favourable -- the middle row is the weakest of the three and is kept.

**The first 0.4.1 attempt was discarded for load contamination, not for its numbers.**
`bonsai.java` maps a 5.95 GB model and ran immediately before the fleet, leaving the host at load
average 39.67 with 3,562,206 pageouts. In that run qwen3-0.6b reported 25,163 ms and 21,174 ms
against 4,057 ms and 2,307 ms here, the warm-up took 35,397 ms against 27,709 ms, and the wall clock
was 150,222 ms of which only 50.3% was inside model calls -- the process was starved. The cost
figures from that run were unaffected, since token counts come from the provider, but a published
pair should be measured under one condition, so both arms were re-run after the machine settled
below load 3.5. The discarded run's own tell is the model-call share: a starved run still prints a
complete and plausible table.

## Walkthrough re-verified on the released libraries

Every script in `code/` was repinned to ModelJars 0.1.61, Models 0.4.3 and Vectors 0.1.30 and re-run
on the host above on 2026-10-16, after `~/.m2/repository/com/integrallis/*/0.4.3` was deleted so
nothing could resolve to the copy published locally during development. All fourteen completed; the
thirteen non-keyed ones were run by `tools/run_examples.py`, whose per-script logs, source hashes,
resolved dependency coordinates and exit codes are in `evidence/walkthrough-0.4.3/`
(`runs.json`, `environment.json`). `runs.json` records the resolved coordinates, which read
`com.integrallis:models:0.4.3` and the rest.

| script | outcome |
| --- | --- |
| chat.java | "Paris"; 26 prompt + 1 completion tokens |
| safetensors.java | "Paris" from the BF16 safetensors bundle; 22 prompt + 1 completion |
| embed.java | 1,024-dimensional vector |
| rerank.java | correct ordering; Berlin population document first at 8.708755 |
| tools.java | two tool calls applied: bedroom light 20, front door locked |
| composite.java | ANSWERABLE; physical prefix sharing true, 182 shared prefix tokens |
| decisions.java | billing? true p=0.920 c=0.60; queue billing p=0.991 c=0.95; urgency today p=0.389 c=0.02 |
| speech.java | 1,728 ms of audio at 32 kHz, RTF 1.350 |
| spring.java | "Paris" through the Spring AI adapter |
| route.java | discovery found 2 cached chat models and selected qwen3_0_6b_q4_0 at score 0.684 |
| rag.java | retrieved doc-0 at 0.8581 and doc-1 at 0.6651; policy returned EXTRACTIVE_FALLBACK |
| gemma.java | 768-dimensional vector under the publisher's prefix recipe |
| bonsai.java | verified 5.95 GB PTQ1_0 artifact; completion produced |
| fleet.java | routing ledger above, both arms |

The speech sample is the one entry that moves between runs: 1,728 ms at RTF 1.433 on 2026-10-15,
1,920 ms at RTF 1.361 on 0.4.0, and 1,856 ms at RTF 1.378 here. It is a synthesis length, not a
fixed property, so the article quotes the run rather than the model. Every other outcome -- the
rerank ordering and its 8.708755, the 182 shared prefix tokens, the two retrieved documents and
their scores, the three calibrated verdicts, the 1,024- and 768-dimensional vectors, the 5.95 GB
artifact -- is identical across all three runs.

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

**3. A completion that exceeds declared token bounds was billed and then discarded (fixed in
0.3.60, both ways).** `RoutingExecution.Attempt.settle` computed the cost, recorded it against the
budget, *then* threw `RoutingBudgetExceededException` if usage exceeded
`RoutingExecutionOptions.tokenBounds`. Because `ModelFleet.executeControlled` calls `settle` before
its `return new RoutedResult<>(value, ...)`, the completion already paid for never reached the
caller. Observed on the first keyed run of `fleet.java`: a 512-token output bound against a
reasoning model that billed 517.

Two changes, both non-breaking. `RoutingBudgetExceededException` now carries `billedResult()`,
`billedUsage()` and `billedCost()`, so a caller can recover what it was charged for without the
guard ceasing to fail closed. And the deeper issue -- one `(input, output)` pair applied to every
candidate, when a 24-token local acknowledgement and a reasoning model's 2,048-token completion
cannot share a ceiling -- is addressed by an optional `ModelCandidate.maxOutputTokens` and
`effectiveMaxOutputTokens(fallback)`, which prefers the candidate's own bound over the
execution-wide one. The previous constructor arity remains as an overload. `fleet.java` declares
2,048 on the remote candidates and leaves the fleet-wide bound small for the local arms.

**4. A candidate could not describe a provider that charges in steps (fixed in 0.4.0).** Anthropic
publishes Haiku 5.5 at $0.10/$0.50 per million below a 100,000-token prompt and $0.50/$2.50 at or
above it. `ModelCandidate` accepted one pair of rates, so the only way to declare that provider was
to pick a step and be wrong on the other side of it -- and because `RoutingBudget` charges what
`ModelCandidate.costOf` reports, declaring the low pair makes a budget stop spending later than it
was told to, by a factor of five on a long request.

`PricingTier` and `ModelCandidate.pricingTiers` let a candidate declare a rate that applies from a
prompt size upwards; `tierFor(inputTokens)` returns the tier in force and `costOf` applies it.
Crossing a threshold reprices the whole request, output included, which is what the providers
actually do. Thresholds are inclusive and token counts are integers, so "above 100,000 tokens" is
declared as `100_001` and no separate inclusive/exclusive flag is needed. Tiers are stored in
threshold order whatever order they were declared in, and two may not start at the same size.

`blendedCostPerMillionTokens` deliberately still reports list price, and routing still scores on it.
Scoring normalises cost across the eligible candidates, so a rate that moved with prompt size would
make a candidate's score jump at its threshold and its rank non-monotonic in the size of the
request. Accounting is where the tier has to be right.

**5. Discovery had no derivation, so the demo stopped discovering (fixed in 0.4.1).**
`CatalogDiscovery`'s own javadoc states its purpose: it exists "so that using the router does not
begin with writing out every model's price, latency and per-task quality by hand -- figures a caller
has no way to know and would have to invent." Probed against the released 0.1.60 catalog with the
fleet's four model jars on the classpath, it returns for SmolLM2:

```
smollm2_360m_instruct_q8_0
  local=true capabilities=[chat] contextWindow=8192
  ttft=72ms tok/s=20.70 quality={}
```

Of the seven builder calls the first version of `fleet.java` wrote for that model, four were already
there (`local`, `contextWindow`, and throughput as an estimate), one was half there (`chat` yes,
the application's own `liveness` no), and one -- per-task `quality` -- genuinely was not.

It wrote all seven anyway, and the reason is a missing API rather than carelessness about typing.
`ModelCandidate` is a record of thirteen components with no derivation, so adding one capability to
a discovered candidate meant restating the other twelve by hand and keeping that copy in step. That
costs more than declaring the model from scratch, so the rational response was not to discover --
and the invented figures then drifted from the artifacts: qwen3-0.6b was declared with a
32,768-token context window where its GGUF says 40,960.

`ModelCandidate.toBuilder()` returns a builder initialised from every component, and
`Builder.addCapabilities(String...)` adds names to the ones already set rather than replacing them.
Capabilities carry over as an explicit choice, so a later `tags(...)` on a derived builder cannot
silently discard what the application just added -- on a fresh builder `tags` seeds `capabilities`,
and on a derived one that would be a loss. Seven tests, each checked against a deliberately broken
implementation; one fixture had to be changed because it held `contextWindow` at the builder's own
default, where dropping the copy could not fail it.

**6. The demo was passing a filter it had silently disabled (no library change).** Rewriting
`fleet.java` to discover made its fifth prompt unroutable:

```
NoEligibleModelException: no model declares the summarization tag;
no model declares required capabilities [chat]; policy is local-only
```

`ModelRouter.eligible` filters on
`taskType != null && !candidate.tags().isEmpty() && !candidate.tags().contains(taskType)`. A
hand-written candidate never called `tags(...)`, so its tag set was empty and that clause never
fired. Discovered candidates carry the catalog's `tags=[chat]`, which switches it on, and
`tell me more` -- the only prompt in this conversation that clears the 0.60 similarity floor, as
`summarization` -- then matches no local model.

This is the library behaving as written: a non-empty tag set is a hard task filter, and an empty one
opts out. The defect is the demo's, and it is worth recording because of how it hid. The program was
not exercising the filter and said nothing about it; a reader would have concluded the fleet was
tag-filtered correctly. It is now cleared deliberately, with the reason in the code, which is the
same behaviour arrived at as a decision instead of an accident. Nothing found it except fixing an
unrelated defect.

**7. A botched experiment made me "correct" a claim that was right.** The article, `code/README.md`
and `route.java` all said discovery reports only models whose weights are already cached. I set out
to verify it, hid `~/.modeljars/cache/sha256/48ab.../model.gguf`, saw discovery still report the
model, and concluded the claim was false. I rewrote all three documents, recorded the correction
here, and reverted a `fleet.java` reordering that the original claim justified.

The experiment was wrong. `ModelJarsCatalog.cached()` checks two locations:

```java
if (descriptor.localPath().filter(Files::isRegularFile).isPresent()) {
  return true;
}
Path artifact = ModelJarCache.artifactPath(descriptor);
return ModelJarCache.isComplete(descriptor, artifact);
```

SmolLM2's descriptor carries
`localPath = ~/.jvllm/models/smollm2-360m-instruct-q8_0.gguf` — a second copy of the same 386 MB
file, which short-circuits the check before the cache path is consulted. I had hidden one of two
copies and read the result as proof.

Re-run with **both** copies hidden, discovery reports nothing. The original claim was correct, and
all three documents are restored.

The reverted reordering was also correct, and is restored. `fleet.java` builds its fleet from
discovery, so on a machine that has never run it there is nothing to discover until the weights are
fetched, and opening each runtime is what fetches them. Verified by deleting both copies and running
the demo: SmolLM2 re-downloaded (31,521 ms of warm-up against its usual ~2,200 ms), discovery then
found all four models, and routing proceeded normally.

What this costs to get wrong is worth stating plainly: a single bad experiment produced a confident
correction, three rewritten documents, a reverted bug fix and a written-up finding, all of them
wrong, and none of it looked uncertain at the time.

**8. A policy comment claimed an outcome nobody had routed (corrected).** `fleet.java` explained
its choice of `BALANCED` by saying `LOCAL_FIRST` "would weight locality at 0.35 and latency enough
that the 360M model wins ordinary chat on speed". `LOCAL_FIRST` weights latency at **0.10**, lower
than `BALANCED`'s 0.15, so the stated mechanism could not produce the stated outcome.

Routed for real, selection only, on the customer's question:

```
BALANCED     -> qwen3_0_6b_q4_0             {quality=0.271, latency=0.150, locality=0.056, cost=0.333}
LOCAL_FIRST  -> qwen3_0_6b_q4_0             {quality=0.193, latency=0.094, locality=0.368, cost=0.211}
FASTEST      -> smollm2_360m_instruct_q8_0  {quality=0.071, latency=0.737, locality=0.053, cost=0.053}
```

`LOCAL_FIRST` picks the same model `BALANCED` does: every local arm scores identical locality, so a
0.35 thumb on it separates nothing between them. `FASTEST` is the policy that hands ordinary chat
to the 360M model. The comment now says that, and says it because it was measured.

**9. The catalog and popularity sections had no provenance at all (now generated).** The project
rule is that analysis tables are produced by scripts from committed artifacts and never typed by
hand. That section of the article was typed by hand: no artifact in `evidence/`, no generator.
Re-derived from `modeljars.org/catalog.json`, committed as `evidence/modeljars-catalog.json` and
reduced by `tools/catalog_stats.py` (output in `evidence/CATALOG-STATS.txt`).

Most figures survived verification exactly: 103 entries, 67 upstream repositories, 167.2 GB, 13.7 MB
smallest, 16.8 GB largest, 0.91 GB median, the format split, the architecture families, the
quantization and domain counts, and the qualification counts (65 RAG, 31 embedding, 29 performance
profiles). The size figures are decimal GB; computed as GiB they read 155.7 / 13.1 / 15.6 / 0.85,
and the script now states which it uses.

One figure was wrong. The licence row said "3 single-model terms including one non-commercial".
There are **6**: Mistral-Research, DeepSeek, Qwen-Research, Llama-3.1, Llama-3 and one
`fair-noncommercial-research-license`. Corrected. Two entries also declare `requiredWeightBytes`
rather than `sizeBytes` -- the composites, whose weights are another catalogued model's -- so the
total covers 101 entries and the article now says so instead of implying 103.

**10. The popularity table quoted download counts with no snapshot (now committed).** A 30-day
download count is a moving number, and the article quoted seven of them plus a 15,143,513 total
against "64 repositories that report counts", with nothing recorded about when they were read.

Re-read from the HuggingFace API on 2026-10-16 and committed as
`evidence/huggingface-downloads.json` by `tools/fetch_downloads.py`. The totals had moved:
**65** repositories report, totalling **17,441,805**. Only two of the 67 do not report, and neither
is a HuggingFace repository -- the first-party compositions carry `modeljars://` source ids. The
article's claim that "one upstream GGUF conversion" also failed to report is no longer true.

The ordering moved too: `deepreinforce-ai/Ornith-1.0-9B-GGUF` is now second at 2,324,254, and
`ggml-org/embeddinggemma-300M-GGUF` has dropped to ninth, which broke a sentence that pointed at
"the seventh row". The table is now rendered by `tools/downloads_table.py` from the snapshot, and
the article states the read date beside the figures.

**11. Three counting and scope errors in the prose (corrected).** Found by counting the thing
rather than re-reading the sentence.

- "The five requirement objects are the whole routing policy" -- there are **six**
  (`liveness`, `chatHere`, `grounded`, `decision`, `synthesis`, `longContext`).
- "One fleet, seven models, three vendors" -- seven models is right, but there are **two** vendors,
  OpenAI and Anthropic. The body of the article said "at two vendors" twice; only the heading
  disagreed.
- "There is no classifier branch, no keyword matching, no prompt inspection" -- the classifier does
  inspect the prompt; that is its job. What is true is that nothing *branches* on what it reports:
  the task type feeds the quality term in scoring, and eligibility is settled by the requirement
  objects alone. Restated to say that.

**12. The walkthrough was not doing RAG in the arm it compared against.** The routed arm called
`ground()`, which embedded the question, searched the collection and sent `Notes: ... Question: ...`.
The no-router arm sent the bare question. The two arms were answering different questions, and the
baseline's input was shorter for a reason that has nothing to do with routing. The article covered
it with a "floor, not a ceiling" caveat instead of fixing it.

Retrieval is now a shared `resolve(retrieval, prompt)` that both arms call, per request. Measured
effect on the baseline's input: the two grounded prompts went from 18 and 13 tokens to **73 and 68**.

**13. The long-context escalation was manufactured (fixed), and fixing it exposed three more.**
`long-context` was a capability name invented in the demo and declared only on the remote
candidates. The catalog has no such capability; it declares `long-context` as a *feature* on seven
entries, and 41 of its models have context windows of 128k or more, one at 1,024,000. The prompt
being escalated was 89 tokens, which every local arm could hold. The demo "worked" because the
routing obeyed the invention.

The appendix is now a real generated document: 1,500 clauses, 708,130 characters, **147,011 tokens**
measured by the local tokenizer. Escalation comes from `ModelRouter.eligible` rejecting
`contextWindow < estimatedTokens`, which excludes the local arms at 8,192 / 40,960 / 131,072 and
admits the remotes at 200k / 400k / 1M. Sized deliberately: 3,000 clauses gave 295,107 tokens, which
also excluded Haiku and left only two remotes competing.

Three defects followed, none of which a 89-token prompt could reach:

- **The classifier throws on a long prompt.** `PretrainedTaskClassifier.match` embeds its input, and
  EmbeddingGemma's context is 2,048 tokens: `sequence of 147019 tokens exceeds the model's context
  length of 2048`. The demo now routes on the instruction and sizes on the payload, which is also
  the right design -- "summarise this appendix" carries the task signal and the appendix does not.
  The library behaviour is still worth changing: a classifier that works by embedding will meet
  prompts longer than its embedding window, and truncating is a better answer than throwing.
- **The appendix was inlined into the prompt text**, so routing on `prompt.text()` would still have
  handed the classifier 147k tokens. It is now an attachment, structurally the same as retrieval.
- **The input bound was fleet-wide only** -- see finding 14.

**14. The post-call token guard was per-candidate for completions and fleet-wide for prompts
(fixed in 0.4.3).** `RoutingExecution` read `candidate.effectiveMaxOutputTokens(...)` for the output
side -- per-candidate since 0.3.60 -- but `options.tokenBounds().inputTokens()` for the input side.
So the appendix routed correctly, the call succeeded, and the guard then refused it:
`provider usage exceeded declared token bounds`.

Raising the fleet-wide bound is not a workaround. `RoutingExecution.account` takes
`inputTokens + outputTokens` as the context every request must fit, so a bound of 200,000 made a
one-token liveness check demand a 200,512-token window:

```
NoEligibleModelException: no model has a context window of 200512 tokens;
no model declares required capabilities [liveness]; policy is local-only
```

And `RoutingExecutionOptions` rejects a budget without complete bounds, so omitting them was not
available either. There was no configuration that both admitted a 147,011-token prompt and left
small requests routable. `ModelCandidate.maxInputTokens` and `effectiveMaxInputTokens` mirror the
output side; the fleet-wide pair goes back to 4096/512 and each remote declares what it can hold.

**15. A locally published jar shadowed Central for three runs.** Publishing Models to the local
Maven repository so ModelJars could compile before 0.4.2 existed produced a `backend-native` jar of
**64,095 bytes with zero native platforms**, because native kernels are built per platform in CI.
It then shadowed Central's 1,178,791-byte jar with all six, and every run failed with
`no Models native-kernel artifact for macos-x86_64`. Clearing `~/.m2` was not enough: jbang caches
its own resolution and kept pointing at the deleted path, so the entry had to be dropped from
`~/.jbang/cache/dependency_cache.json` and the script rebuilt with `--fresh`. Verify what is on the
classpath, not what you believe you published.

**16. Three declared numbers were wrong, and each one failed at a different place.** The demo
declared a context window and a price for every remote. Running a genuinely large document against
them found three errors, none of which a small prompt could reach.

- **Haiku's window admitted a prompt it could not hold.** Eligibility is decided on a local
  estimate; billing is decided on the provider's count. The same document measured **147,011**
  tokens by the local qwen3-0.6b tokenizer, **141,534** at OpenAI and **219,559** at Anthropic --
  49% longer on Anthropic's ruler. A 147k estimate fits Haiku's 200,000-token window; the 219,559
  Anthropic actually counted does not. The router admitted it, the call was made and paid for, and
  the post-call guard refused the result: `provider usage exceeded declared token bounds`, with
  `billedUsage()` reporting 219,559 input and `billedCost()` $0.1109. That is 0.3.60's
  billed-overrun API doing exactly the job it was added for, and the only reason the spend was
  recoverable.
- **gpt-5.1's declared window was 400,000; the real limit is 272,000.** The provider said so
  itself: `Input tokens exceed the configured limit of 272000 tokens. Your messages resulted in
  284034 tokens.` A window declared too generously does not fail at routing time. It fails at the
  provider, after the request has been built and sent.
- **The document had to be sized against the worst ruler, not the best.** Sizing it to just clear
  the local arms left a margin that one provider's tokenizer ate. It is now 2,500 clauses,
  245,741 local tokens: past every local window, past Haiku's 200,000 on any tokenizer, and inside
  gpt-5.1's real 272,000.

The general shape is the one this whole file keeps finding: a declared figure is a claim, and the
only authority on a provider's limits is the provider.

**17. The measured result stopped flattering the router, and the article now says so.**
*The latency half of this finding is superseded by finding 20: the ratio quoted here is one
pair, and the pair moves. The cost half stands.* With a real
document in play the numbers are $0.310373 with no router against $0.099222 routed -- 68.0% less, a
factor of 3.13 -- but wall clock went from 24,491 ms to 52,588 ms, **115% slower**.

Both halves have the same cause. The appendix is 236,535 of the 236,596 billed input tokens, and
routing sent it to gpt-4.1-mini at $0.40/M instead of gpt-5.1 at $1.25/M: $0.094736 against $0.296.
gpt-4.1-mini is also slower, 23,390 ms against 8,485 ms. The cost saving and the latency cost are
one decision seen from two sides.

The corollary matters more than the headline. The eight prompts answered locally would have cost
$0.009959 on gpt-5.1 -- **3.2%** of the bill. On this workload keeping them local is nearly free
either way, and the saving is one provider choice on one document. On a workload of ten thousand
heartbeats it inverts. The article states both and does not pretend the mix is universal.

**18. An unsourced number did not survive being measured (null published).** The article claimed
four resident runtimes "made qwen3-0.6b twenty times slower than it is alone" -- 1,169 ms against
23,946 ms -- and that capping each runtime at three threads fixed it. Neither figure had a committed
artifact; both came from an earlier session and were never re-derived.

Measured by `code/oversubscription.java`, which times the same prompt with qwen3-0.6b alone and then
with three other runtimes resident, run with and without the cap
(`evidence/fleet-routing/oversubscription.log`):

```
default: every runtime sizes for all 12 cores
  qwen3-0.6b alone                   3152 ms
  qwen3-0.6b beside three others     3749 ms   (1.2x)

-Dmodels.native.kernels.threads=3
  qwen3-0.6b alone                   3584 ms
  qwen3-0.6b beside three others     3827 ms   (1.1x)
```

The effect is **1.2x, not 20x**, and the cap does not improve it -- it is slightly slower on its own.
The 23,946 ms almost certainly came from a load-contaminated run of the kind finding 11 describes,
measured before the harness rejected those. The claim is withdrawn and the measurement published as
it came out. The script still sets the cap, because the published run was measured with it, and the
article says that rather than implying the cap earned its place.

**19. "115% slower" was true and badly framed.**
*Superseded by finding 20: re-measuring the pair three times showed the ratio itself is not a
property of the fleet. The attribution below -- two chosen destinations, not a routing tax --
held up and is still what the article says.* The routed arm takes 52,588 ms against the
baseline's 24,491 ms, warm against warm. But routing imposes no such tax: two prompts account for
+23,424 ms of the +23,435 ms, and both are destinations the `BALANCED` policy chose -- the appendix
to gpt-4.1-mini, cheaper per token and slower, and the closed decision to a 4B model on CPU.
Everything else nets to +11 ms, and the three heartbeats are 5-9x faster locally. The article now
attributes the latency to the two choices rather than to routing as such.

**20. The headline latency ratio was a property of the provider, not of the fleet.** Findings 17
and 19 both quoted one pair of wall clocks, 52,588 ms routed against 24,491 ms with no router, and
argued about the 115% between them. Re-running the identical pair showed the ratio is not a number
the fleet owns. Every accepted pair is now archived under `runs/` with its load readings, and
`tools/run_variance.py` reduces them:

<!-- figures:variance -->
| run (UTC) | routed | no router | latency ratio | cost factor |
| --- | --- | --- | --- | --- |
| `20261019T042738Z` | 63,520 ms | 58,623 ms | 1.08× | 3.15× cheaper |
| `20261019T043801Z` | 43,690 ms | 31,155 ms | 1.40× | 3.19× cheaper |
| `20261019T044507Z` | 45,530 ms | 25,857 ms | 1.76× | 3.13× cheaper |

Across **3 measured pairs** — same code, same prompts, same machine, all archived under [`evidence/fleet-routing/runs/`](evidence/fleet-routing/runs) — the latency ratio moved from **1.08× to 1.76×** (median 1.40×) while the cost factor moved from **3.13× to 3.19×**. One of those is a property of the fleet; the other is a property of the provider's queue on the day. Which is which:

- the no-router arm's wall clock ranged over **2.27×** (25,857 ms to 58,623 ms)
- the routed arm's remote portion ranged over **2.62×** (15,226 ms to 39,935 ms)
- the routed arm's local portion ranged over **1.22×** (23,585 ms to 28,667 ms)
- the appendix prompt alone, byte for byte identical every run, came back in 3,309 ms at best and 17,863 ms at worst — **5.40×** on one call to one provider
<!-- end:figures:variance -->

The cost factor barely moves, because token counts are a function of the prompts and the prompts do
not change. The latency ratio moves by a third, because most of the no-router arm is one call to one
provider and that call is not the same call twice. The article no longer leads with a ratio. It
leads with which of the two arms you can predict, states the range with its n, and the harness
refuses to publish a figure from a single pair.

This is the same class of error as finding 18 -- a number quoted without asking whether it is
repeatable -- and it survived longer because this one had an artifact. A committed log proves what a
run printed. It does not prove the run is representative.

**21. The article's prose drifted from its own tables twice, so the prose is generated now.**
`tools/refresh_article_blocks.py` has lifted the quoted output blocks straight out of the logs since
finding 9. The sentences around them were still typed by hand, and after a re-measurement the
article stated 52,588 ms in a paragraph directly beneath a table reading 63,520 ms, quoted
$0.310373 above a ledger reading $0.313503, and said the appendix went to Anthropic's Haiku in a
section whose own table showed it going to gpt-4.1-mini.

`tools/article_figures.py` now generates the comparison tables *and* the sentences that carry their
numbers, into `<!-- figures:NAME -->` regions in both this record and the article. What cannot be
generated in place is checked instead: `verify_prose` fails the run if the article states a
six-figure number that appears in no file under `evidence/` or `code/`. Both generators read the
newest *archived* pair rather than the harness's working logs, which the harness truncates at the
start of every attempt -- so the quoted blocks and the derived tables are always the same run.

**22. Harriet's batched decisions are not a bug, and the condition they turn on is not documented.**
Asking three questions about one ticket costs more than the javadoc's "a second question about the
same state costs a fraction of the first" implies, and the reason is in the source rather than in
any fault. The resumption point is captured after the *shared prefix*, and
`ModelJarDecisionRuntime.sharedPrefix` is `criteria.isEmpty() ? state : state + "\n" + criteria` --
the evidence **and the rubric**. It is reused only when the next question's shared prefix is
byte-identical (`ModelJarDecisionRuntime` line 243: "Every space in the group must share one prefix,
so a group of mixed rubrics cannot be grouped. Falling back is correct and the caller sees the same
answers either way"). Three questions with three rubrics -- a boolean, a choice over queues, an
ordered severity, which is exactly the shape of a real batch -- share no prefix, so each one
re-reads the evidence.

The layout itself is a measured choice, not an oversight: the same javadoc records rubric-before
with letters-after at Intelligence **88.9** over 120 JevBench items against **86.1** for both after
the criterion and **79.6** for both before, dated 2026-09-24. That is read from the library's own
record, not measured here. So the rubric is in the prefix because it scores better there, and the
cost of that is that mixed-rubric batches do not amortise.

`code/grouping.java` measures both shapes -- same-rubric and mixed-rubric, at one, two and three
questions -- on the shipped 0.1.61 artifact over a 250-token ticket, after a discarded warm-up
batch, printing every verdict's probability to six places as well as its latency so the same probe
is the before/after check on any change (`evidence/fleet-routing/grouping.log`):

<!-- figures:grouping -->
| questions about one ticket | one shared rubric | three different rubrics |
| --- | --- | --- |
| 1 | 14,723 ms | 14,792 ms |
| 2 | 15,919 ms | 32,387 ms |
| 3 | 16,635 ms | 44,005 ms |

The first question costs what reading the ticket costs — 14,723 ms and 14,792 ms, the same work either way. What the two after it cost is the finding: **956 ms** each when the rubric is shared against **14,606 ms** each when it is not, a factor of **15.3**.

Strip the rubrics out entirely and the same three questions take **14,464 ms** against **44,005 ms** — the prefix is then the ticket alone, so all three share it. That **3.0×** is what the rubric buys its accuracy with, and the library's own record prices the other side of that trade at 0.8917 accuracy with rubrics against 0.7500 without. Measured here, read there.
<!-- end:figures:grouping -->

Harriet stays in the walkthrough: nothing here returns a wrong answer, and the three archived pairs
above include this cost in the routed arm without it changing which arm is cheaper.

**The headroom is real and is not a prompt change.** Where the rubric sits in the prompt is settled
by the Intelligence measurement. Where the *capture* sits is not: capturing after the state alone
and re-reading the criteria per question would send byte-identical prompts, return the same
answers, and amortise the evidence across unlike questions. On this probe the mixed batch pays
44,005 ms for a ticket that costs 14,464 ms to read once. That is a change to
`ModelJarDecisionRuntime` -- a second resumption slot keyed on the state prefix, with the existing
tokenisation guard deciding whether the split is safe -- and it is the next thing on this path. It
is not in 0.1.61 and the article says so rather than implying the current cost is necessary.

### Where the other implementations on this machine put this line

Read from the clones on this machine, with paths, not from their documentation. Two of the three
things I had written down about this survey turned out to be wrong when I opened the code again, so
every row below cites where it was read.

| implementation | where its prices come from | prompt-size tiers | tier applied when selecting |
| --- | --- | --- | --- |
| LiteLLM | fetched over HTTP at import | yes | not a selector |
| weave-os/router | catalog in Go source, client artifacts generated | yes | yes |
| vLLM semantic router | operator YAML, per model | no | flat cost is a selection weight |
| RouteLLM | no prices at all | no | no cost term |
| TensorZero | operator config | no | no |
| Models 0.4.0 | operator-declared on the candidate | yes | no, by choice |

**LiteLLM does not ship a static table.** `litellm/__init__.py:546` calls
`get_model_cost_map(url=model_cost_map_url)` at import, and the default URL
(`litellm/__init__.py:417`) is the project's own `model_prices_and_context_window.json` on GitHub
raw. `litellm_core_utils/get_model_cost_map.py` retries 429 and 5xx with Retry-After-aware backoff,
validates what came back (a non-empty dict whose model count is above a floor and has not shrunk
past a ratio against the packaged copy, so a corrupted upstream cannot silently empty the map), and
falls back to `model_prices_and_context_window_backup.json` on any failure.
`LITELLM_LOCAL_MODEL_COST_MAP=True` forces the local copy, and
`get_model_cost_map_source_info()` reports which one is live. Its tiered rates are the
`input_cost_per_token_above_{N}k_tokens` keys in that map. This is the opposite of what I had
recorded, and it is the strongest argument for the network option we declined: they clearly thought
the freshness was worth a startup fetch, and then spent real effort making the fetch safe to depend
on.

**weave-os/router tiers in selection as well as in billing.** `internal/router/catalog/catalog.go:62`
carries `LongContext *LongContextPricing` with `{ThresholdTokens, InputUSDPer1M, OutputUSDPer1M}`,
and `Pricing.ForInputTokens(inputTokens)` at line 103 swaps rates above the threshold --
structurally the same thing as `PricingTier` and `tierFor`, declared exclusive at `100_000` where
ours is inclusive at `100_001`. Its catalog lives in Go source and `cmd/genprices` regenerates every
client-side artifact from it. But `ForInputTokens` is called from
`internal/router/policy/resolver.go:479` inside `estimatedCostUSD`, from `resolver.go:537` when
candidates are expanded, and from `internal/router/planner/policy.go:159-160` in the pin-versus-fresh
switch economics -- all selection -- as well as from `internal/router/catalog/cost.go:21,64` and
`internal/proxy/turnloop.go:2567` when billing. I had recorded it as billing-only. It is not.

That is the one data point against the choice this release made, and it deserves stating as such
rather than being argued away. The difference is what the number feeds: weave-os scores on an
absolute estimated cost in dollars, where a tier change moves the score monotonically with true
cost. Models normalises cost across the eligible candidates into a 0-1 score, so a candidate
crossing its own threshold moves relative to every other candidate and its rank stops being
monotonic in request size. Normalised scoring is the reason we kept list price, not a claim that
tiering selection is wrong -- a router that scores on absolute cost should tier its selection, and
weave-os does.

**The selection-oriented routers skip tiers entirely.** vLLM's semantic router has flat per-million
`Rates` in `src/semantic-router/pkg/modelpricing/modelpricing.go:7`, declared as `pricing:` on a
model in operator YAML (`pkg/config/canonical_providers.go:24`), and uses cost in selection as a
weight and a ceiling (`config/fragments/algorithm/selection/multi-factor.yaml`: `cost: 0.2`,
`max_cost_per_1m: 5.0`). There is no size threshold anywhere in it. RouteLLM has no price or cost
term in `routellm/` at all -- it routes on a quality model and a threshold. TensorZero takes
operator-declared `cost_per_million` or `cost_per_unit`
(`crates/tensorzero-types/src/cost.rs:21-25`) with no tier.

**On where the numbers come from, the implementations divide three ways.** LiteLLM fetches a
community-maintained map at startup with a validated local fallback. weave-os keeps the catalog in
its own source and generates its artifacts from it. The selection-oriented routers and TensorZero
take operator-declared values and nothing else. Models stays in the third group on purpose:
fetching a price map at startup trades a network dependency and a third-party trust boundary for
freshness, and that belongs to a deployment rather than to a library. The honest cost of that choice
is that an operator's declared price goes stale silently, which LiteLLM's design avoids and ours does
not. Prices in `fleet.java` are declared constants, and the article says so where it reports cost.
