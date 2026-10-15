# Rust cleanup review — evidence and implementation status

This review covers the native routes discussed in the article. It is not a completed dead-code
audit of all three repositories. The user has authorized validating the best route, making it
the default, removing unused alternatives, and publishing only after the release gates pass.

## Current integration status

- Corrected sequential DeltaNet is staged as the default for compatible FMA hosts and supported
  dimensions. The approximate chunked implementation is removed and the ABI revised. Exact
  Java alternatives were measured; kernel speed did not predict their whole-model behavior.
  Numerical equivalence to corrected Java passes the composed x86 and ARM cohorts. Small-Qwen
  task-quality differences against the published runtime and resource regressions remain release blockers.
- Grouped Q5_0's unused capability and dispatch support have been removed after actual-model
  slowdown and divergent x86 continuations were reproduced. Its bit is reserved; active
  single-projection Q5_0 remains.
- The historical Q5_1 embedding benchmark did not call Rust. Corrected experiments count native
  calls and clone output snapshots. The revised native row-reuse kernel reduces causal-model
  request time on both tested hosts, but the complete candidate fails allocation and peak-memory
  gates against published. A missing Qwen SwiGLU provider call is repaired in an external candidate
  under whole-model qualification. BERT retains Java: native reuse improves warm embedding latency
  but fails loading time. No JVM limitation has been established.
- Attention ownership is corrected, with a failing original Miri control and passing corrected
  checks. The native platform CI passes. Its performance justification is a separate task.
- The corrected activation implementation is numerically stable but causes allocations in actual
  models. JFR identifies vector/array materialization in the exponential call. External BF16 and
  SwiGLU candidates pass numerical checks and now exercise the actual Bonsai dispatch; their fixed
  whole-model resource comparisons remain in progress. Convolution arithmetic controls change
  small-Qwen answers without yet establishing a quality remedy.
- The shim registry tracks 15 operation groups. Structural validation passes; all unresolved
  causal-proof records remain unproven. The campaign-completion check must fail accordingly.

No release has been published from this cleanup. The [runtime record](../../projects/models-final-integration/docs/findings/runtime-cleanup-2026-10-12.md)
and [article explanation](why-rust.md) contain the current results. The review below preserves
how the investigation began; its proposed-work table is historical, superseded by this status.

Reachability and performance are separate questions. A route that production never takes is
inactive; a reported speedup makes it an urgent investigation target before deletion is finalized.
An active route with incomplete justification is not dead code.

## First priority: revisit DeltaNet before finalizing removal

**Finding:** my earlier claim that no Java-versus-native comparison existed was wrong. It relied
on an incomplete dispatcher comment. The retained [decision latency report](../../projects/models/benchmark-results/2026-09-24-decision-latency/CEILING.md)
contains that comparison, including reported per-decision times of 1.483 → 1.107 seconds without
a rubric and 2.201 → 1.604 seconds with one. These are historical report claims, not fresh results.

I independently reread its two retained TSV files and verified their hashes against the archived
`SHA256SUMS`:

| Arm | Cases | Recomputed median seconds | SHA-256 |
| --- | ---: | ---: | --- |
| Java recurrence, `S-gdn-false.tsv` | 120 | 2.1541784825 | `6514f4cdfb4ea0cb757f1f1426092d235adb3495059c5d5a9753b134d14cf7d1` |
| Native recurrence, `S-gdn-true.tsv` | 120 | 1.876404015 | `b55a507fb499381cca87dc841296a4cace92385911057caf593bedfe2e7a6c78` |

The case IDs match. The highest-probability label differs for `original-routing-06-0`.
This confirms that the retained results contain both a latency difference and changed behavior.
It does not independently reproduce the benchmark or establish a JVM limitation. These TSV
medians and the report's other timing tables are different measurements and must not be combined.

**Approved experimental work:**

1. Keep the pending deletion out of publication. Recover the historical experiment from git into
   an isolated benchmark worktree, without enabling it in production. Pin its graph, weights,
   native binary, JVM, prompts, thread counts, and reported route execution.
2. Reproduce Java recurrence versus native sequential, chunked, and grouped recurrence on the
   same host. Separate recurrence timings from full prefill and complete decisions. Include
   one-token decode, 18/128/512-token prefixes, and ragged groups.
3. Trace the changed label back through logits and recurrent state. Preserve the existing exact
   contracts; do not classify a systematic implementation difference as measurement noise.
4. Implement the corresponding Java chunking/state-reuse candidate in the experiment and
   compare it against current Java and Rust. A better algorithm is not inherently a Rust benefit.
5. Repeat on supported x86 and ARM hosts and a second public decision dataset, retaining the
   original cohort and every failed candidate. Use the proof plan's frozen protocol and budgets.
6. Return with a concrete recommendation: adopt the Java improvement; qualify a narrowly
   justified Rust route if Java cannot meet the requirement; or finalize removal after the
   reported benefit is disproved or cannot preserve the required behavior.

The original experiment did not authorize publication. The user has since explicitly authorized
completing the implementation decision, validation, removal of unused alternatives and publication
through the existing release checks; no additional consultation checkpoint is required.

The implementation target is one best production path. Different paths are justified only by
measured differences in input, hardware, or another concrete runtime requirement. Experimental
arms are controls for establishing that choice, not proposed user-facing switches.

## New correctness finding: active attention ownership

Rust attention workers create overlapping whole-buffer exclusive references before selecting
their assigned heads. A concrete patch narrows those references to each worker's own range;
it leaves arithmetic and scheduling unchanged. Local validation includes 540 configurations
repeated three times, all 32 Rust tests, and a minimal Miri reproduction demonstrating the
invalid overlap and the disjoint-range correction. The user has authorized the correction, which is applied locally with a pinned Miri CI guard.
All six native platform jobs and the Miri check have now passed in CI. Publication remains pending.
[CI](https://github.com/integrallis/models/actions/runs/38277441853),
[patch and evidence](../../projects/models-final-integration/benchmark-results/2026-10-11-gdn-proof/ATTENTION-OWNERSHIP.md).

The inactive native recurrence has the same ownership issue. Grouped tests also reproduced a
one-row call writing the wrong state slot and a separate exponential-rounding mismatch.
Experimental corrections pass 324 ragged group comparisons and 42 prefix cases; invalid and
duplicate slot mappings are rejected without changing output or state. Supported-host and
whole-model qualification remain separate gates.

## Initial findings and proposed work (historical)

| Priority | Finding | Proposed change or investigation | Validation before adoption |
| --- | --- | --- | --- |
| 2 | Q5_1 is active and `isEligible()` accepts supported shapes without performance filtering. The retained small-matrix case is slower in Rust; the short embedding experiment shows no end-to-end gain. | Reproduce the regression with current Java and Rust, short queries and long documents. Optimize Java and compare matched scheduling. Propose a measured routing restriction or replacement afterward; do not guess a cutoff from one old sample. | Exact projection parity, embedding quality, repeated same-host timings, and complete embedding throughput/latency on two public datasets. |
| 3 | Grouped Q5_0 is excluded by production eligibility, yet capability bit 13 and generic grouped entry points still expose it. The routing comment admits missing raw performance evidence. | Reproduce grouped versus independent execution first. If grouping has a benefit, test whether routing is missing a useful configuration. Otherwise remove the unreachable grouping advertisement and acceptance paths while preserving active Q5_0 projection arithmetic and shared dispatch. Check direct ABI callers before changing compatibility. | Route counters, tests that unsupported grouping is rejected before a native call, unchanged ordinary Q5_0 outputs, and model-level performance. |
| 4 | Attention is active and has a historical whole-model gain, but no isolated current JVM-cause proof. | Compare current Java and Rust attention under identical surrounding kernels and arithmetic contracts. Fix any Java implementation bottleneck found before attributing it to the JVM. | Tensor/token checks, context/head/cache-span matrix, then whole-model performance. No removal solely because the proof is incomplete. |
| 5 | Workers, batching, and conversion are shared support for active kernels. Existing measurements do not independently establish Rust superiority for each mechanism. | Instrument component costs and test matched Java/native scheduling, reuse and conversion. Remove support only when its last actual caller is gone. | Executed-dispatch tests, numerical parity, allocation, contention, CPU use, startup and complete model timing. |
| 6 | CUDA has measured accelerator gains. The retained same-model RTX 4090 TornadoVM attempt failed 36 device launches and did not reach the exact-token gate; its throughput is not valid evidence of working Java GPU performance. | Diagnose those recorded failures before evaluating a Java-authored replacement on the same GPU and workload. | Identical model/graph contract, successful launches, token parity, cold compilation, transfers, resident memory and whole-model speed. |
| Documentation | `architecture.adoc` still describes the old Q4_0 Java GPU path where the implemented CUDA module exports Q4_K/Q6_K and attention. Its retirement wording also implies a newer JDK is always required. | Update those current descriptions from implementation and evidence. Preserve explicitly historical experiment reports. | Cross-check exports and dispatch; validate documentation links/build. |

## Original production sequence (historical)

The DeltaNet kernel and shared-context model experiments are complete. The narrow attention
ownership correction is authorized and applied locally.
Review completed DeltaNet outcomes before changing production routing or finalizing its pending
deletion, then investigate the Q5_1 regression. The grouped Q5_0 decision follows
its reachability and performance checks, rather than automatic deletion based on inactivity.

The [proof plan](rust-shim-proof-plan.md) supplies the common correctness, measurement, and
release gates. The article now distinguishes existing implementations, historical measurements,
unverified causes, and the experiments needed to decide.
