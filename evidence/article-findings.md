# Defects found by running the article

| Finding | Observed effect | Correction | Regression evidence |
| --- | --- | --- | --- |
| CLS pooling rejected at facade | Qualified LFM2.5 cannot open through `ModelJars.openEmbedding`. | Map CLS to the existing Models pooling enum. | Real pinned weights: failure before fix; finite, normalized, distinct, repeatable embeddings after. Dedicated task runs in PR and release validation. |
| Wrong composition demo | `modeljars demo granite-hybrid` imports Qwen classes absent from its declared dependency. | Select Granite's public composition API; reject unknown entrypoints explicitly. | Released generator's JBang compilation fails; corrected generated source compiles in the CLI test suite. Real Granite walkthrough produces ANSWERABLE and reports shared state. |
| Generated Jackson pin drifts | Tool demos declare 2.22.2 while the shared dependency policy uses 2.22.3. | Derive the declaration from the CLI's resolved Jackson version. | Generated declaration checked against the build's dependency policy. |
| Tool handler does not enforce argument range | Out-of-range brightness and integer overflow can reach the example's in-memory state. | Check integral representation, Java integer conversion and 0–100 bounds. | Compile and execute the generated validator: 0/100 accepted; -1/101/4294967296 rejected. |
| Stale composition integration assertion | The control run correctly reports zero physically shared tokens, but the test expects the shared run's count. | Assert positive shared tokens for SHARED and zero for RECOMPUTED; retain exact output equality. Run the real-weight composition gate in PR and release validation. | Before-fix run fails at 182 versus 0. Both real-weight tests pass after correcting the assertion; exact output equality is retained. |
| Obsolete GPU setup | README recommends the removed Tornado backend. | Document `backend-cuda`, FFM driver access and hardware requirements. | Checked against current source. |
| CUDA README presents old predictions as current status | Claims no kernel has run on a GPU despite retained October measurements. | Replace current status and preserve old reasoning in a labeled history file. | Cross-check against Rust exports, Java loading and G1/G4 evidence; full Models build/compliance passes. |
| Incorrect native recurrence description | Models README says recurrence routes to Rust; the dispatcher returns false. | Describe retained experimental kernels and active Java routing. | Checked both capability methods and ABI; Models build/compliance passes. |

Code and CLI fixes (merged after CI passed): [ModelJars PR 211](https://github.com/ModelJars/modeljars/pull/211).
Real composition gate: [ModelJars PR 213](https://github.com/ModelJars/modeljars/pull/213).
CUDA documentation (merged after CI passed): [Models PR 262](https://github.com/integrallis/models/pull/262).
Native documentation (merged after all CI passed): [Models PR 261](https://github.com/integrallis/models/pull/261).

The following are observed model/policy limitations, not established implementation defects:
Harriet's low-confidence binary billing decision disagrees with its queue choice, and the RAG
policy rejects the short generated answer in favor of a broader extractive fallback. The article
retains both outputs. Changing qualification or claiming better quality would require the
separate evaluation protocol, not editing the example until it looks successful.

## Release disposition

The runtime and CLI corrections are published in [ModelJars 0.1.56](https://github.com/ModelJars/modeljars/releases/tag/v0.1.56).
All six artifacts were downloaded from Central and compared with the signed bundle
(JAR, POM and Gradle module metadata). The [installation receipt](local-install/maven-local-receipt.json)
and [consumer graph](local-install/maven-dependency-tree.log) preserve that check.

The dependency chain remains Vectors 0.1.29 → Models 0.3.57 → ModelJars 0.1.56.
Models required documentation corrections; no additional Models or Vectors runtime patch
was needed for these findings. Website examples now advertise 0.1.56.

[All eleven released walkthroughs](walkthrough-results.md) passed with real cached weights.
Original failures are retained separately. These smoke checks establish that the article's
public API examples execute; they do not requalify the entire model catalog or establish
hardware-independent quality/performance claims.

The local Homebrew CLI is also 0.1.56. Its installed binary matches the release checksum,
and `brew test integrallis/tap/modeljars` passes; see the
[native installation receipt](local-install/native-cli-receipt.json).

## EmbeddingGemma 2 and Bonsai additions

| Finding | Observed effect | Correction | Evidence |
| --- | --- | --- | --- |
| Hidden width presented as embedding output | EmbeddingGemma 2 has hidden width 512 and output width 768; the prior CLI/site label conflated them. | Label descriptor width as hidden width; retain qualified vector width separately. | Site regression failed before the fix and passes afterward; CLI tests and the real 768-dimensional facade integration pass. ModelJars PR 216 carries the correction. |
| Bonsai example allocates the full advertised context | A 4 GB heap fails during cache allocation before generation. | Request a 64-token context for the eight-token demonstration through the public per-load configuration. | Failed cast/log retained under `bonsai-context-failure`; corrected released-runtime recording exits 0 and matches the reference continuation text. |
| Native and replacement figures appear disconnected | The supplied preview puts the two graphs on one canvas without any edge between them; some HTML breaks appear literally. | Combine them into one figure, link both Rust paths to replacement evaluation, and use plain-text labels. | `diagram-before-connection/reported-preview.png`, parsed Mermaid, a reachability check over all 17 nodes, and visually checked SVG/PNG exports. |

The context correction changes the article's load configuration; it does not change Models'
documented maximum-context default. The diagram correction changes presentation only.
EmbeddingGemma's numerical conformance and Bonsai's runtime compatibility are distinct from
retrieval or production RAG qualification.

The final generated-catalog check also found stale Granite and Harriet library coordinates
(0.1.55). ModelJars PR 216 aligns both with 0.1.57 and adds a CI guard covering the
coordinate, model version and download URL. This advances composition library dependencies;
it does not change their member weights or rewrite historical qualification reports.

## Article presentation without release numbers

At the author's request, release numbers were removed from the article prose and
Mermaid labels. Inline snippets omit JDK/dependency directives and replace marker
release suffixes with `<model-version>`; linked executable scripts and historical
receipts retain the tested pins. The synchronizer enforces this distinction. All
four Mermaid figures are regenerated as SVG and PNG. Model-family names remain
exact, because they identify the models under discussion.

## The quality claims, 2026-10-20

Everything above was found by *running* the article. This section is what was found by **scoring**
it: the fleet declared four capabilities and nothing had ever checked whether the models could
serve them. Three of the four declarations were wrong, and the fourth was a claim about work the
router never sent locally.

| Finding | Observed effect | Correction | Evidence |
| --- | --- | --- | --- |
| Four quality numbers typed in by hand | `chat 0.45`, `chat 0.60`, `grounding 0.70`, `decision 0.90` were this application's opinion. Measured against gpt-5.1 on four public datasets they were 16 to 35 points optimistic, and the 0.70 contradicted the catalog's own evidence for that artifact (GUARDED_RAG, model-only correctness 0.111). | Every declared quality number deleted. The fleet declares capabilities only; Models 0.5.x made that the honest option by scoring an unmeasured task as a neutral prior instead of a zero. | [routing-accuracy](../experiments/routing-accuracy/README.md), protocol frozen before the first call; [FINDINGS](../experiments/routing-accuracy/FINDINGS.md) |
| `grounding` declared on a 1B model | 35.0 exact match on SQuAD v2 against gpt-5.1's 70.0, and **0 abstentions out of 50** on the unanswerable half, with the prompt naming the abstention string. | The grounding arm is the largest Llama in the catalog, measured at 79.0 against gpt-5.1's 70.0 on the same 100 items. | [grounding-arm-selection](../experiments/grounding-arm-selection/README.md) |
| `decision` declared on the local arm alone | 80.0 and 76.0 against gpt-5.1's 96.0 and 92.0 — 16 points behind on both datasets. | The fleet escalates a decision whose calibrated confidence falls below 0.6, measured live at 98.0 and 90.0, and ships with that default on. The escalation share and its dollar cost are reported beside the gain. | [ESCALATION.txt](../experiments/routing-accuracy/ESCALATION.txt), `results-decide-gated0-6-*.jsonl` |
| `summarization` declared and never exercised | The only summarization prompt exceeds every local arm's context window, so eligibility ruled the arm out before the capability was consulted. Nothing measured it because nothing used it. | Declaration deleted. | `tools/parity_gate.py` reported it as unmeasured |
| Confidence medians labelled with the wrong scope | `fleet.java` and FINDINGS reported "median 0.793 when right, 0.379 when wrong ... over 200 items". Those were SNIPS's numbers; pooled over 200 items the medians are 0.637 and 0.368, and TREC's separation is much narrower (0.483 against 0.350). | Both are now derived from the arm's own rows by `confidence_medians` in `tools/article_figures.py`, per dataset, and the narrower TREC separation is reported as the reason that dataset has to escalate three quarters of its decisions. | `results-decide-routed-*.jsonl` |
| Nothing checked a declaration at all | Four wrong claims shipped because prose cannot check prose. | [`PARITY-BASIS.json`](../PARITY-BASIS.json) records the kind of evidence each declaration rests on, and `tools/parity_gate.py` fails the build with an exit code equal to the number it cannot verify. It matches each declaration to a measurement of the model the fleet actually ships, and refuses a declaration measured with an escalation gate the fleet does not ship. | `make check`, run in CI |

Two harness defects were corrected in the same round, because a measurement harness that leaks is a
measurement nobody can trust: `tools/isolated_host.sh` left a paid firewall behind when a run was
killed between creating the firewall and creating the server, and looped forever when the provider
refused the create instead of reporting the refusal. Both now fail loudly and tear down on every
exit path.
