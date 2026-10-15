# Engineering plan: prove or remove each Rust shim

Status: implementation and qualification are in progress; no complete shim-necessity certification has been issued. This document defines
acceptance gates and does not certify any shim. It follows the [verification findings](rust-java-verification.md), the workspace
[working agreement](../../CLAUDE.md), and the Models [campaign runbook](../../projects/models/docs/CAMPAIGN-RUNBOOK.md).

## Current progress and remaining gates

Corrected sequential native DeltaNet is staged as the default on compatible FMA hosts and supported
shapes. The approximate chunked implementation was removed after investigation; sequential
DeltaNet was retained because the measured whole-model results justified investigating and
correcting it. The earlier proposal to remove all native recurrence is superseded. See the
[DeltaNet findings](../../projects/models-final-integration/benchmark-results/2026-10-11-gdn-proof/FINAL-GDN-FINDINGS.md)
and [cleanup review](rust-cleanup-review.md).

The composed candidate preserves Java/native full-logit snapshots across all 148 selected public
cases, including fresh sessions, reset, and chunked input, on x86 and ARM. That does not establish
quality parity with the published runtime: the small dense Qwen cohort scores 90/148 versus 91/148
on x86 and 85/148 versus 90/148 on ARM. Both larger-model strata pass their per-dataset quality
checks. Convolution activation rounding changes some small-model answers; the investigation has
not yet established a replacement that clears quality and resource gates. Repeated-case controls
also reproduce output drift in the published baseline. That finding does not waive the failed gate.

The native attention ownership correction and the recurrence addressing corrections are staged.
The evidence inventory and enforcement are implemented in the integration branch. All unresolved
shim-necessity claims remain explicitly unproven. Failed experiments and raw measurements are
archived outside release code; retained findings link to their receipts.

The current work is to:

1. Finish the fixed Bonsai comparisons using the actual BF16 and SwiGLU production dispatch,
   including observed capability ablations, startup, latency, allocation, and peak memory.
2. Finish the Q5_1 whole-model comparison after repairing the missing Qwen SwiGLU provider call.
   The previous composed runtime fails allocation and memory gates despite its faster kernel.
3. Resolve the small-Qwen quality differences using frozen inputs and generic arithmetic controls;
   do not tune coefficients or prompts to particular answers.
4. Integrate only accepted source, repeat affected real-model and public-quality checks on those
   exact artifacts, and run the dependency-ordered release checks before publication.

The [workspace audit](../../library-audit-2026-10-12.md) records current run IDs, artifact identities,
completed failures, and remaining gates. No cleanup release has been published. The user has
already authorized completing this work and publishing through the release checks; another
consultation checkpoint is not required. The acceptance contract below remains unchanged.

## Objective and acceptance contract

For every production Rust operation, either produce reproducible evidence that a specific
limitation of a supported JVM prevents the tested Java implementations from meeting the required
workload performance, or implement and qualify its Java replacement. Narrow native selection to
the configurations where its necessity is demonstrated. Remove unused native implementations
after checking ABI compatibility and callers.

“Rust was faster” is insufficient. “We have not optimized Java yet” is unfinished engineering.
Proof must identify a concrete API, compiler, or device-runtime limitation and connect that
limitation to a user-facing requirement. It is bounded to named runtimes and supported hardware;
we cannot prove that no conceivable Java algorithm could ever work.

A retained route must satisfy all five gates:

1. **Correctness:** preserve its declared numerical contract and real-model behavior.
2. **Java investigation:** implement and measure the relevant Java alternatives below.
3. **JVM cause:** retain a minimal reproducer, generated-code or runtime evidence, and a controlled
   experiment connecting the limitation to the measured cost.
4. **Necessity:** the best tested Java route misses a workload requirement fixed before measurement;
   the Rust route meets it, without moving another required metric outside its limit.
5. **Scope and retirement:** record exactly where the result applies and a runnable test that will
   establish when Java can replace the shim.

Supporting routines such as native workers inherit justification from the proven compute
operations that require them. They must not be advertised as separate JVM limitations without
independent evidence. A GPU-to-CPU comparison proves accelerator benefit, not the necessity of
writing the device kernel in Rust.

## Work sequence and deliverables

Keep one integration branch per affected repository for this campaign. Use short-lived experiment
branches only when needed; retain rejected experiments as benchmark sources and evidence, not
unused production alternatives. Do not amend commits referenced by deployed benchmark payloads.
Keep experimental changes off release branches until their gates pass.

### 1. Establish a trustworthy baseline and complete inventory

- Finish the outstanding BF16 determinism repair and its regression checks before using Bonsai
  as a performance acceptance workload. Diagnose other baseline failures explicitly; do not
  score failed runs or silently exclude failing models.
- Freeze source commits, artifact hashes, dependency locks, build tools, JVM distributions and
  flags for Vectors, Models, and ModelJars. Record source builds separately from released artifacts.
- Enumerate every CPU capability and exported ABI function, all three CUDA exports, Java
  dispatch conditions, actual callers, and qualified model profiles that exercise them. Inventory
  activation conversion and worker support as dependencies of their compute operations.
- Give each operation/configuration an ID and status: `UNPROVEN`, `PROVEN_REQUIRED`,
  `JAVA_REPLACEMENT_READY`, `RETIRED`, or `INACTIVE_EXPERIMENT`. Historical evidence starts as a
  reference, not automatic proof for the current implementation.
- Add observable invocation and fallback counters to the benchmark harness. An ablation must
  assert that its intended route executed and that the disabled route did not. Use benchmark-only
  injection or adapters where possible, avoiding new unsupported production tuning switches.

**Deliverable:** `docs/native-shims/registry.json` in Models, a schema, and a generated inventory
covering the CPU capability enum, native exports, CUDA exports, and production dispatch sites.
Implemented in the Models integration branch: [registry](../../projects/models-final-integration/docs/native-shims/registry.json),
[schema and contract](../../projects/models-final-integration/docs/native-shims/README.md), and
[validator](../../projects/models-final-integration/scripts/verify-native-shim-evidence.py).
The inventory covers 15 operation groups, 24 active CPU capability bits and one reserved retired bit, 20 CPU exports, and three CUDA exports.
All groups remain explicitly unproven or inactive until their evidence satisfies the complete contract.
`verifyNativeShimEvidence` runs in `complianceCheck`; 14 mutation tests exercise rejection of stale,
unexecuted, incomplete, or unowned evidence. `verifyNativeShimCampaignComplete` deliberately fails
while unresolved groups remain. Structural validation cannot establish scientific causality; reviewed
compiler/runtime evidence and workload measurements are still required.

### 2. Build the common comparison harness

Extend the retained JMH, real-weight, and qualification harnesses. The same payload must run:

| Arm | Purpose |
| --- | --- |
| Released Java implementation | Establish the existing Java behavior and cost. |
| Java candidate | Test each proposed improvement independently. |
| Java plus the one Rust operation under investigation | Isolate that operation's contribution. |
| Released Java plus Rust configuration | Detect regressions against the behavior users receive. |
| Independent model oracle / authoritative performance comparator | Verify the graph and the existing application qualification requirements. |

Keep every other operation and setting constant for a component ablation. Also measure complete
Java execution: interactions between worker pools, batching, and neighboring kernels can reverse
an isolated result. Do not change arithmetic, activation precision, prompts, context, output
length, or thread counts between arms and call the difference a language speedup.

For CPU kernels, test one worker and the actual deployment worker count. Separate preparation,
conversion, dispatch, compute, and result handling before measuring the combined path. This
prevents crediting Rust arithmetic for a gain actually caused by different scheduling or memory
layout. For GPUs, separate compilation, upload, launch, compute, download, and synchronization.

**Deliverable:** one reproducible command per operation/profile that produces all arms, route
counters, raw samples, correctness results, environment receipts, and a machine-readable verdict.
Missing weights, tools, or a comparator are setup work to complete, not reasons to skip the gate.

### 3. Investigate the operations, in this order

First complete the DeltaNet investigation in the cleanup review: reproduce the historical
Java/native result, investigate numerical divergence, and test Java chunking/state reuse.
Then follow the ordering below. The inactive-code row does not authorize deleting a path with
reported performance gains before investigating them.

Complete one group before moving to the next. Within each group, exercise small workloads first
and retain boundary shapes and larger workloads; do not hide dispatch overhead behind large matrices.

| Order | Operation and starting workloads | Java work and causal experiment | Required decision |
| --- | --- | --- | --- |
| 1 | Q5_1; real MiniLM Q5_K artifacts, short queries and documents near the model's supported context limit; 384×384 and 1536×384 projections with small and large batches | Compare existing dequantization with direct packed-block processing; match the Rust accumulation tree and unfused arithmetic. Compare sequential, existing parallel, and workload-sized dispatch. Inspect conversion, bounds checks, spills, inlining, and allocations. Measure complete embedding latency and throughput on at least two public text datasets. | Resolve the existing small-batch regression and end-to-end null result. Keep only profiles with all five proof gates; otherwise replace the route with qualified Java. |
| 2 | CPU grouped-query attention; Granite with short/long contexts, different query/KV head groups, ordinary caches and shared-prefix spans | Benchmark the current fused Java kernel against Rust with identical reduction and exponential contracts. Isolate cache reuse, vectorized softmax, head partitioning, dispatch, and allocation. Inspect compiled code and run complete generation. | Demonstrate a current JVM cause and workload need, or implement the Java replacement. An older Granite result is not sufficient. |
| 3 | Persistent workers, grouped/independent projections, batch weight reuse, activation preparation and half conversion | Match work partitioning and reuse between Java and Rust; measure barriers, polling, context switches, activation bytes, conversion instructions, and allocation. Test tiny jobs followed by large jobs, changing active worker counts, repeated close/open, and concurrent sessions. | Fix implementation gaps in Java. Retain native support only for independently justified native compute callers; remove orphan support. |
| 4 | Q4_0, Q5_0, Q8_0; small published generation models and Soprano Q8, spanning decode and prefill | Compare widening, packed pairwise expressions, unpacking, row tiling, and staged scheduling. Reproduce compiler instruction selection on supported HotSpot and Graal distributions. Test the complete quantized block and model, not merely a dot-product instruction. | Prove the packed-dot/compiler gap on each retained profile, or select the Java implementation that passes. Preserve speech waveform and streaming gates. |
| 5 | Q4_K, Q5_K, Q6_K and mixed groups; qualified models carrying those actual tensor types, including vocabulary and FFN shapes | Isolate scale/minimum unpacking, integer dot products, activation sharing, row/batch reuse, mapped-memory addressing and spills. Test register tiles and grouped Java scheduling independently. | Retain format- and host-specific native routes only where the complete evidence proves need. Do not extrapolate one format's result to the others. |
| 6 | PTQ1_0; real Bonsai weights on x86 and ARM, sequential decode and chunked prefill | Start from the existing Java SIMD implementation. Isolate trit unpacking, Q8 preparation, integer accumulation, scale conversion and dispatch. Match Rust's arithmetic exactly and inspect vector widening versus packed-dot instructions. | Preserve full-vocabulary parity and publisher oracles; repeat application qualification on the final runtime. Earlier source experiments remain historical. |
| 7 | Inactive Gated DeltaNet and excluded grouped Q5_0 implementations | Confirm all dispatch sites and callers. Check whether removal affects exported capability masks or ABI consumers. Keep useful reproducers in benchmark/test code. | Remove unused production code through a compatible ABI change or the next declared ABI revision; reserve retired bits. No new native recommendation from an unmeasured experiment. |
| 8 | CUDA Q4_K, Q6_K and grouped-query decode attention | Implement equivalent Java-authored device candidates using the viable tooling identified at execution time, including the retained Java accelerator experiments. Test ordinary launch, device discovery, compilation/cache behavior, memory ownership, transfers, and fallback on the same supported GPU. CPU Vector API alone is not the comparison. | Establish whether the blocker is device compilation, packaging, runtime integration, or performance. A tooling inconvenience that we can fix is engineering work. Retain Rust only for a reproduced supported-runtime limitation and a measured workload requirement. |

This table is the starting experiment set. Generated-code findings must drive additional focused
candidates when a fixable issue appears; completing a checklist does not excuse leaving a known
Java fix untested.

### 4. Produce causal proof for each proposed retention

For every suspected limitation:

1. Reduce the real hot path to a standalone Java reproducer that preserves the relevant input
   layout, arithmetic, memory access, and compiler behavior.
2. Capture compilation level, inlining decisions, generated instructions, allocation, and relevant
   CPU counters. Separate diagnostic profiling from the timing runs.
3. Implement the corresponding Java alternatives. Inspect their generated code; failed scalar
   replacement, unnecessary copying, or missing batching may be our implementation defect.
4. Run a controlled change that tests the proposed cause: for example, the same Java code on a
   compiler that emits the missing instruction, or a corrected Java expression that removes the
   allocation. Where only a native primitive can provide the control, hold surrounding work and
   call overhead constant and document the remaining attribution limits.
5. Reinsert the result into the real model. The cause is relevant only if eliminating its cost
   addresses the frozen workload requirement.

If the causal evidence remains ambiguous, mark the route `UNPROVEN`; do not promote a hypothesis
to “JVM limitation.” Submit a minimal upstream issue for confirmed JVM defects, or link an
existing matching issue. An upstream issue by itself is not proof of model-level necessity.

## Measurement and correctness protocol

Freeze `protocol.json` before candidate results. It must specify artifacts and sources, at least
two public datasets per affected task, representative shapes, deployment CPUs/GPUs, current
supported JVM distributions, thread/affinity settings, cold/warm definitions, repetitions,
numeric contracts, metric limits, and the decision procedure. Include native-width x86 and ARM;
where supported, distinguish ARM NEON and SVE. Forcing a vector width on another CPU is a
correctness exercise, not a substitute for that hardware's performance measurement.

Start kernel timing with at least three fresh JMH forks, five warmup iterations and ten measured
iterations per arm, recording iteration durations. Whole-model comparisons use counterbalanced
same-host process pairs, at least ten fresh-process observations for startup and at least thirty
measured requests per arm for warm behavior. Retain run order and process-level samples; report
confidence intervals with the process/pair as the independent unit. Increase repetitions under
a predeclared sampling schedule if tail estimates or paired differences remain uncertain.
Never rerun until a favorable result appears or discard a slow valid trial.

| Gate | Required evidence |
| --- | --- |
| Kernel correctness | Independent format oracle plus Java/Rust comparison; exact bits wherever the existing contract is exact. Cover tails, signs, scale extremes, batch boundaries and cold-to-compiled transitions. Do not loosen tolerances to admit a faster candidate. |
| Model correctness | Real weights, full logits where available, greedy token IDs, session continuation/isolation, cache sharing, and task-specific outputs. Preserve existing embedding/reranking and audio quality floors. Token parity alone is insufficient. |
| Application qualification | Run the existing policy unchanged. For authoritative RAG comparisons, retain the 0.80 minimum decode ratio, 1.5 maximum end-to-end latency ratio, contribution and quality gates, and recorded absolute latency tier. These admission limits do not permit regressions against the shipped implementation. |
| Performance preservation | Compare Java replacements with the shipped route for TTFT, TPOT, decode/prefill throughput, end-to-end latency, startup, peak memory, and allocation. Freeze numerical budgets for each profile before measurement. Every detected regression is investigated and fixed; an inconclusive result does not pass. |
| Evidence precision | Target paired confidence intervals narrow enough to distinguish a 1% change in each primary timing metric. This is a measurement target, not permission for a 1% slowdown. If hardware noise or sample cost prevents a decision, report `INCONCLUSIVE` and resolve the experimental limitation. |
| Rust necessity | The best tested Java candidate reproducibly misses a frozen requirement while Rust passes, with uncertainty accounted for. A kernel-only win or a gain that affects no required workload metric does not establish necessity. |

Freeze startup and memory budgets from the actual deployment envelope and existing behavior;
do not invent them after seeing the winner. A retention target must cite a user-facing requirement
or the established shipped performance being preserved, not a new target chosen to favor Rust.
Do not require a deliberately weak Java implementation to fail merely to produce a justification.

Use dedicated, otherwise idle benchmark hosts. Before remote runs, follow the campaign runbook:
verify live pricing and quota, declare per-phase cost/time limits, pin immutable payloads, upload
early diagnostics and partial results, and confirm termination of every owned instance. Reaching
a budget limit makes the experiment incomplete; it does not turn missing evidence into a pass.

## Evidence artifacts and build enforcement

Store each proof bundle under `benchmark-results/native-shim-proof/<operation>/<profile>/` in
Models, with Vectors kernel reproductions stored and linked from Vectors where appropriate:

- `protocol.json`: requirements and experiment matrix frozen before measurements.
- `provenance.json`: source/artifact hashes, dependency graph, tools, runtime, hardware and commands.
- `correctness/`, `raw/`, `codegen/`: oracle results, all timing samples, counters and compiler evidence.
- `decision.json`: verdict, scope, limitations, rejected candidates, remaining work and retirement test.
- `README.md`: concise explanation of the demonstrated cause and its workload consequence.

Add a proposed `verifyNativeShimEvidence` build task and meaningful validator tests. It must:

1. Fail when a production native route/export lacks a registry entry or has a mismatched capability.
2. Verify evidence hashes, mandatory fields, profile coverage and nonempty executed-arm counters.
3. Invalidate affected proofs when kernel, dispatch, numerical contract, relevant dependency,
   compiler/toolchain, or qualification policy changes. Use explicit dependency fingerprints;
   unrelated documentation changes must not invalidate a proof.
4. Prevent new native routes from entering releases as `UNPROVEN`. Keep existing gaps visible in
   a finite migration checklist; this campaign is not complete while any active route remains
   unproven. Do not manufacture grandfathered proof records.
5. Test rejection of missing comparators, stale fingerprints, wrong artifacts, absent route
   execution, and unsupported hosts. A structural validator cannot establish causal proof; the
   linked experiment and its technical review remain required.

Run fast deterministic checks on normal CI. Run real-weight and dedicated-host performance gates
for affected changes and before release. Periodically recheck confirmed blockers against supported
JVM updates so a solved limitation triggers retirement work instead of persisting indefinitely.

## Integration, releases, and completion

First qualify Java replacements and route narrowing on source builds. If replacement currently
regresses, keep the existing release intact while fixing it; do not falsely mark the shim proven,
delete a qualified model, relax a test, or ship a slower replacement to close the checklist.
No unresolved item may be called completed.

Release in dependency order:

1. **Vectors:** land qualified Java kernels and regression tests; pass its full required checks,
   release procedure and dry run; publish if changed; fetch and verify the actual Central artifacts.
2. **Models:** consume the verified Vectors release, align dependency locks, implement only the
   proven native selection and qualified Java replacements, and check ABI compatibility. Run
   required builds, real-weight suites, and affected application comparisons before publishing.
3. **ModelJars:** consume the verified Models release and the matching Vectors dependency. Check
   shared dependency policies across all three projects. Repeat the complete current catalog's
   default correctness smokes for kernel/decoder changes, plus affected task qualifications, using
   the released libraries. Preserve historical reports and add new evidence instead of relabeling it.
4. Publish changed catalog/marker/CLI/site artifacts through their documented procedures, verify
   Central consumer resolution, and update local codebases and installed tools. Publish only
   projects whose contents changed; do not create unnecessary releases.

Update the article, architecture documentation, and JVM research brief from the final proof
registry. In particular, remove stale claims that inactive recurrence is a necessary native route.

The campaign is complete when every active route has all five proof gates, every replaced route
uses qualified Java in the released runtime, unused native code is removed compatibly, the
dependency chain and catalog pass on released artifacts, and the article's explanations link to
the actual evidence. The final report must list each retained/removed/narrowed operation and its
measured justification; it must also state any unfinished work plainly.
