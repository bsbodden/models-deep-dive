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

## jbang fleet.java, three remote providers, released 0.1.60 / 0.4.1 / 0.1.30

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

Every script in `code/` was repinned to ModelJars 0.1.60, Models 0.4.1 and Vectors 0.1.30 and re-run
on the host above on 2026-10-16, after `~/.m2/repository/com/integrallis/*/0.4.1` was deleted so
nothing could resolve to the copy published locally during development. All fourteen completed; the
thirteen non-keyed ones were run by `tools/run_examples.py`, whose per-script logs, source hashes,
resolved dependency coordinates and exit codes are in `evidence/walkthrough-0.4.1/`
(`runs.json`, `environment.json`). `runs.json` records the resolved coordinates, which read
`com.integrallis:models:0.4.1` and the rest.

| script | outcome |
| --- | --- |
| chat.java | "Paris"; 26 prompt + 1 completion tokens |
| safetensors.java | "Paris" from the BF16 safetensors bundle; 22 prompt + 1 completion |
| embed.java | 1,024-dimensional vector |
| rerank.java | correct ordering; Berlin population document first at 8.708755 |
| tools.java | two tool calls applied: bedroom light 20, front door locked |
| composite.java | ANSWERABLE; physical prefix sharing true, 182 shared prefix tokens |
| decisions.java | billing? true p=0.920 c=0.60; queue billing p=0.991 c=0.95; urgency today p=0.389 c=0.02 |
| speech.java | 1,856 ms of audio at 32 kHz, RTF 1.378 |
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

**7. "Discovery only finds cached models" was never true (three documents corrected).** The
article, `code/README.md` and `route.java` all stated that discovery reports only models whose
weights are already downloaded. That claim was never tested; it was assumed, repeated, and
published.

Measured two ways on this host. Hiding a cached GGUF
(`~/.modeljars/cache/sha256/48ab.../model.gguf`) changed nothing: both models were still reported,
with the same ids, locality and context windows. Removing the local registry
(`~/.modeljars/catalog/registry.properties`, 6,585 lines) changed nothing either. Discovery is
driven entirely by the classpath -- a marker jar carries its model's descriptor -- and weights are
fetched when a runtime is opened, not when a model is discovered. That is why `route.java` can
select between models that have never been downloaded, which is a better story than the one the
article was telling.

The claim surfaced because it predicted a bug: if discovery needed cached weights, `fleet.java`
building its fleet before warming its models would fail on any machine that had not run it before.
The prediction was wrong because the premise was, and a reordering made on that premise was
reverted. Worth recording as the general case: an unverified claim is not merely unsupported, it
produces confident reasoning that is wrong in a direction nothing in the output reveals.

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
