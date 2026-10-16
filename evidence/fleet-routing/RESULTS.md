# fleet.java verified run

Host: Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz, 12 logical CPUs, macOS 26.6.2, x86_64
Java: openjdk version "25.0.3" 2026-04-21 LTS
JBang: 0.141.0
Date: 2026-10-16T18:04Z (routed arm), 2026-10-16T18:13Z (all-remote arm)
Load average at the start of each arm: 3.10 and 2.66
OPENAI_API_KEY and ANTHROPIC_API_KEY: present for the keyed runs below

Raw artifacts: `routed.log`, `all-remote.log`. Every derived figure below and in the article comes
from `tools/derive_fleet_figures.py`, which reads those two logs and `code/fleet.java`; its output
is `DERIVED.txt`. No figure in either document is hand-computed.

## jbang fleet.java, three remote providers, released 0.1.60 / 0.4.0 / 0.1.30

Two OpenAI models and one Anthropic model share the fleet with four local models. Each provider has
its own endpoint, credential, auth header and response shape; each client normalises its own
provider into one `RoutingUsage`.

```
classifier: 10 tasks from google_embeddinggemma_300m_gguf_q8_0, 768-dimensional, similarity floor 0.60

PROMPT                                               IN  COMPLETION
ping                                                  7          10
still there?                                          9          22
ok                                                    7          19
I was charged twice for my September order.          15         431
tell me more                                          9          99
I was charged twice for my September subscr…         19         404
When is a refund issued, and to which payme…         18         346
What happens to a duplicate charge?                  13         346
Our refund policy promises five business da…         61         501
Summarise this appendix for the support han…         89          80

== every prompt through gpt-5.1 ==
provider-reported: 247 input + 2258 completion tokens
at the declared $1.25/M in, $10.00/M out: $0.022889
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

$0.022889 all-remote against $0.006993 as routed: 69.4% less, a factor of 3.27. The eight prompts
that stayed local would have billed 1,677 completion tokens on gpt-5.1, or $0.016891 -- 73.8% of the
whole all-remote bill. Per completion token the two providers that did run differ by twenty times,
$10.00 against $0.50 per million, and Haiku answered 8.4 times faster than gpt-5.1.

Completion counts are not deterministic, so these are the figures of the pair of runs measured
together on the released libraries, not a best case. The 0.1.59 / 0.3.60 pair measured on 2026-10-15
gave $0.023859 against $0.006123 -- 74.3% and a factor of 3.90 -- on the same prompts and the same
prices. The spread between those two pairs is the provider's variance in how much reasoning it
bills, and it is the reason the article states one measured pair rather than an average.

## Walkthrough re-verified on the released libraries

Every script in `code/` was repinned to ModelJars 0.1.60, Models 0.4.0 and Vectors 0.1.30 and re-run
on the host above on 2026-10-16. All fourteen completed; the thirteen non-keyed ones were run by
`tools/run_examples.py`, whose per-script logs, source hashes, resolved dependency coordinates and
exit codes are in `evidence/walkthrough-0.4.0/` (`runs.json`, `environment.json`).

| script | outcome |
| --- | --- |
| chat.java | "Paris"; 26 prompt + 1 completion tokens |
| safetensors.java | "Paris" from the BF16 safetensors bundle; 22 prompt + 1 completion |
| embed.java | 1,024-dimensional vector |
| rerank.java | correct ordering; Berlin population document first at 8.708755 |
| tools.java | two tool calls applied: bedroom light 20, front door locked |
| composite.java | ANSWERABLE; physical prefix sharing true, 182 shared prefix tokens |
| decisions.java | billing? true p=0.920 c=0.60; queue billing p=0.991 c=0.95; urgency today p=0.389 c=0.02 |
| speech.java | 1,920 ms of audio at 32 kHz, RTF 1.361 |
| spring.java | "Paris" through the Spring AI adapter |
| route.java | discovery found 2 cached chat models and selected qwen3_0_6b_q4_0 at score 0.684 |
| rag.java | retrieved doc-0 at 0.8581 and doc-1 at 0.6651; policy returned EXTRACTIVE_FALLBACK |
| gemma.java | 768-dimensional vector under the publisher's prefix recipe |
| bonsai.java | verified 5.95 GB PTQ1_0 artifact; completion produced |
| fleet.java | routing ledger above, both arms |

Two figures moved from the 0.1.58 / 0.3.59 run of 2026-10-15 and are restated above: the speech
sample is 1,920 ms at RTF 1.361 rather than 1,728 ms at RTF 1.433, and `decisions.java` reports its
urgency confidence, which the earlier table omitted. Nothing else changed.

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
