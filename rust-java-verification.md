# Verification of the Java replacement claims

This is a source and retained-evidence review supporting [Why do we need Rust?](why-rust.md).
No new performance measurements were made for this review. Historical measurements below apply
to their recorded sources, hardware, runtime, and workloads.

The follow-up [engineering plan](rust-shim-proof-plan.md) defines the experiments, proof gates,
build enforcement, and release work required to resolve these findings.

**Correction after expanding the evidence search:** the earlier DeltaNet assessment was
incomplete. The retained decision campaign includes Java-versus-native timings and changed
predicted labels. The [cleanup review](rust-cleanup-review.md) records the source reports and
checksum-verified TSV reanalysis. DeltaNet's local removal is on hold for reconsideration;
performance investigation now takes priority over finalizing deletion.

The sentence “others are implementation work we can do in Java already” was too broad. It did
not identify an omitted implementation or demonstrate that implementing one would replace a
shim without a regression. Several examples described as potential Java work are already present.
Conversely, not every retained shim has evidence isolating a JVM limitation. Those are separate
findings; neither justifies claiming that all Java optimization possibilities have been exhausted.

## What is already implemented

| Area | Verified Java implementation | What the evidence establishes |
| --- | --- | --- |
| Persistent workers and dispatch | [GgufPersistentRowExecutor](../../projects/vectors/vectors-core/src/main/java/com/integrallis/vectors/core/GgufPersistentRowExecutor.java) keeps platform threads alive, polls before parking, and executes stage plans. | These are existing Java mechanisms. A [scheduling experiment](../../projects/models/benchmark-results/audio/soprano-q8-scheduling-20260904/README.md) made isolated projections about three times faster but made complete language generation roughly 40% slower; that change was rejected. |
| Batched weight reuse | [PanamaVectorUtilSupport](../../projects/vectors/vectors-core/src/main/java/com/integrallis/vectors/core/PanamaVectorUtilSupport.java) implements row-local reuse across several quantized formats. | A further [Q8 tiling candidate](../../projects/vectors/vectors-bench/jmh-results/soprano-q8-experiments-20260905.md) was exact but took 688 ms against the existing 322 ms control. Reuse is implemented; additional tiling is not automatically an improvement. |
| Grouped-query attention | [GroupedQueryAttentionKernel](../../projects/models/backend-java/src/main/java/com/integrallis/models/backend/purejava/ops/GroupedQueryAttentionKernel.java) contains vectorized scores, softmax, and accumulation with shared key/value reads and fixed reductions. | The [Granite investigation](../../projects/models/benchmark-results/2026-09-15-granite-4.1-3b-alora-hybrid/preflight.md) records a whole-model gain after native attention was introduced. It does not identify an unavoidable JVM limitation or establish parity with the current Java implementation. |
| Ternary projections | [TernaryDequantizer](../../projects/models/backend-java/src/main/java/com/integrallis/models/backend/purejava/quant/TernaryDequantizer.java) implements packed ternary/Q8 dot products with Java vectors. | The [Bonsai evidence](../../projects/models/benchmark-results/2026-10-11-bonsai-production/README.md) retains the Java SIMD improvement and its rejected native ARM predecessor. The corrected NEON route subsequently exceeded Java SIMD by 2.538 times in decode and 2.610 times in prefill on the measured host. These are source experiments; final qualification remains pending. |
| Activation preparation and half conversion | [GgufQuantizationSupport](../../projects/vectors/vectors-core/src/main/java/com/integrallis/vectors/core/GgufQuantizationSupport.java), the Java projection kernels, and TernaryDequantizer already prepare activations and use Java half conversion. | Neither operation is missing from Java. The reviewed evidence does not independently establish these helpers as unavoidable reasons for retaining Rust. |
| Gated DeltaNet recurrence | Java remains the execution path. The unused Rust kernels, FFM bindings, and native recurrence injection hooks have been removed from the working source. | This is dead-code removal, not a performance optimization. The CPU native ABI was advanced because the recurrence exports were deleted. Publication is separate from this source change. |

## Where compiler evidence exists

The [pairwise multiply-add experiment](../../projects/vectors/vectors-bench/jmh-results/vector-api-pairwise-jvm-baseline.md)
inspected generated instructions as well as timing. The tested Graal compiler emitted packed
multiply-add instructions that the tested HotSpot compiler did not. However, the complete Q8
pairwise candidate was still slower than the established Java widening implementation on both
runtimes. That candidate was measured and rejected.

The separate [Q4 experiment](../../projects/vectors/vectors-bench/jmh-results/graal-q4-short-pairwise.md)
retained a Java formulation after correctness and whole-model gains, under a specific Graal
configuration. It also records rejected formulations and allocation failures. This supports a
specific compiler/code-generation concern, not a universal claim that Java cannot perform packed
integer arithmetic. Its historical runtime settings are not a current deployment recommendation.

## Evidence gaps that remain

- **Q5_1:** the [retained comparison](../../projects/models/benchmark-results/2026-10-08-q5-1-rust-shim/NOTES.md)
  shows useful kernel gains, one small-batch mean regression, and no demonstrated end-to-end gain
  for short embedding probes. Long-document end-to-end performance was explicitly unmeasured.
  This does not support claiming that a JVM limitation requires the shim for all embedding work.
  A current paired workload comparison must determine which routes should be retained.
- **Attention:** the earlier Granite gain establishes historical benefit. A current, isolated
  Java-versus-Rust comparison is needed before either claiming an unavoidable compiler barrier or
  removing the route. The arithmetic and generated tokens must be checked alongside timing.
- **Scheduling, reuse, and conversion:** their implementations can be inspected, but that alone
  cannot attribute a remaining performance difference to the JVM. Controlled component comparisons
  are needed before naming any one of them as a blocker.
- **Older descriptions:** the research brief `JVM_NATIVE_INFERENCE_GAP.md` incorrectly described
  native recurrence as necessary. That statement has been corrected alongside removal of the
  unused native code. Historical performance reports remain unchanged.

The corrected article therefore states what Java already does, cites measured differences where
available, and identifies unverified causes. This review found no demonstrated, generally
applicable Java replacement being withheld in the examined evidence. It does not prove that
every possible Java optimization has been tried. A Java candidate that passes the same numerical
and whole-model performance gates should replace its corresponding Rust route; an unverified
optimization opportunity remains engineering work, not a claimed JVM limitation.
