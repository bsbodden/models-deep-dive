# Sources and verification boundaries

## Release baseline

The initial scripts ran with Vectors 0.1.29, Models 0.3.57 and ModelJars 0.1.55.
`runs.json` preserves their source hashes and exit codes; `run-*.log` contains actual output.
Nine scripts exited successfully. LFM2.5 failed at ModelJars' public pooling switch.
Successful execution is not a model-quality score.

The source baselines are:

- Vectors release: `1440ca7555e492ae7c2a17cde7cb3ffe6c07b7b5`.
- Models release: `7bde1c2ef31c608069294e47c17d2efccbc58afb`.
- ModelJars release: `32a90dcaba05df338654cd6b4bda13af5c497a57`.

## Runtime and native boundary

Read the implementation alongside the README. ModelJars' README still described Tornado,
and Models' native README described recurrence as routed; both contradicted current code.
Those documentation defects are corrected as part of the article work.

- [CPU Rust ABI and capabilities](https://github.com/integrallis/models/blob/7bde1c2ef31c608069294e47c17d2efccbc58afb/backend-native/src/main/rust/model-kernels/src/lib.rs): ABI 6, 24 capability flags, including scheduling/group variants.
- [Production CPU dispatcher](https://github.com/integrallis/models/blob/7bde1c2ef31c608069294e47c17d2efccbc58afb/backend-native/src/main/java/com/integrallis/models/backend/nativekernel/RustGgufBatchedMatrixKernel.java): both recurrence capability methods return false; Q5_0 grouped capability does not force grouped routing.
- [Q5_1 experiment](https://github.com/integrallis/models/blob/7bde1c2ef31c608069294e47c17d2efccbc58afb/benchmark-results/2026-10-08-q5-1-rust-shim/NOTES.md): exact arithmetic contract, kernel improvements, and short-probe end-to-end null result.
- [CUDA dispatch experiment](https://github.com/integrallis/models/blob/7bde1c2ef31c608069294e47c17d2efccbc58afb/benchmark-results/2026-10-07-g4-dualpath/README.md): RTX 4090, Granite 4.1 3B, retained measurements; not rerun on the article laptop.
- [CUDA parity run](https://github.com/integrallis/models/blob/7bde1c2ef31c608069294e47c17d2efccbc58afb/benchmark-results/2026-10-07-g1-parity/README.md): 20 prompts, 1,280 matching tokens; does not establish all-device parity.
- [Apple bridge](https://github.com/integrallis/models/blob/7bde1c2ef31c608069294e47c17d2efccbc58afb/backend-apple/README.md): Swift bridge to the platform framework, separate from the Rust CPU/GPU kernels.

## Java capabilities

Primary references, checked while writing:

- [MemorySegment, Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [Linker, Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html).
- [Vector API module, Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/module-summary.html).
- [Float, Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Float.html): half-float conversion already exists.
- [OpenJDK Babylon](https://github.com/openjdk/babylon): research direction, not a promised replacement date.

API availability is not evidence of a kernel's lowering or speed. Graduating an API from
incubation does not impose a lane-independent floating-point reduction order.

## Catalog and qualification

The source candidate inventory contains 457 rows. The October 10 deployed catalog snapshot
at `../../../audit-2026-10-10/modeljars-deployed-catalog.json` contains 102 public entries,
including two compositions. The build independently reports 100 qualified model artifacts
plus two compositions. Task tracks overlap; summing them would double-count models.

The earlier outline's 101/one-composition counts were stale. Its reference to the disabled
recurrence route was correct, despite the contradictory README. Current quantized decode
routing is active; removed native toggle properties must not be used to manufacture an A/B arm.

Qwen BF16 smoke [evidence](https://github.com/integrallis/models/tree/9ca046e0d6eacb4aced8ece99307a3436d2bf260/benchmark-results/2026-10-10-release-0357)
records nine passing pipeline cases: five model answers, three extractive fallbacks and one
abstention. These are not nine independently correct generated answers.

LightOnOCR-3 remains a candidate awaiting runtime/evaluation work. Whisper frontend support
does not establish a complete speech-to-text pipeline. No fresh whole-catalog qualification
is claimed by this article.

## Article observations and regression

- `lfm-regression-before.log`: real public loading path fails on `pooling=cls`.
- `lfm-regression-after.log`: same integration test passes after mapping CLS to Models' existing enum.
- `run-decisions.log`: Harriet's weak binary billing output disagrees with its queue choice.
- `run-rag.log`: raw Qwen answer is followed by an extractive fallback including both retrieved sources.
- `run-speech.log` and `initial-source/speech.wav`: actual generated audio; no stock audio substituted.
- `mermaid-validation.json`: parser versions and SHA-256 digests for all current Mermaid files.

The inputs are intentionally small API demonstrations. They are not published evaluation
datasets and do not support accuracy, calibration or general performance claims. GPU and
Apple framework execution were not run on this Intel Mac.

## Additional CLI defects found during the walkthrough

The released `modeljars demo granite-hybrid` emitted a Qwen-specific entrypoint against a
Granite-only dependency. `granite-generator-before.log` records the resulting compilation
failure. The corrected generator selects Granite's actual public recipe and has a Java
compilation regression test. The initial real-weight composition run returned `ANSWERABLE`,
with physical prefix sharing and 182 shared tokens; see `run-composite-initial.log`.

Tool demos now derive Jackson from the CLI's resolved dependency policy and reject
brightness values outside 0–100, including values that overflow a Java integer. The
handler regression compiles and executes the generated code, rather than checking only
that the source contains a validation statement.

The full Granite integration gate additionally exposed a stale test assertion: shared
execution reports 182 physically shared tokens, while the recomputed control correctly
reports zero. The output-equality assertion already passed. The correction keeps output
equality and verifies the two distinct sharing counts; no runtime arithmetic is changed.
The gate is now included in PR and release validation. Original failure details are retained
in `granite-integration-before.xml` and `granite-integration-before.log`.

Current explanatory documentation is corrected on Models main at
`46842b835432c3a6f5e3d17ccc268a1c67086aeb`:
[CPU routing](https://github.com/integrallis/models/blob/46842b835432c3a6f5e3d17ccc268a1c67086aeb/backend-native/README.md),
[CUDA status](https://github.com/integrallis/models/blob/46842b835432c3a6f5e3d17ccc268a1c67086aeb/backend-cuda/README.md).
The older CUDA reasoning is retained as labeled history. These are documentation changes;
the article continues to use the released Models 0.3.57 runtime.

## Corrected public release

ModelJars 0.1.56 is published from `42fadd26b8cacc1b205e0218f79f321858bfb28f`.
All six released JARs, POMs and Gradle module descriptors were downloaded from Maven Central
and hash-checked against the signed release bundle. See
[installation receipt](local-install/maven-local-receipt.json) and
[resolved dependencies](local-install/maven-dependency-tree.log).
The direct released-runtime LFM2.5 smoke is in `embed-central-release.log`.
The released CLI JAR also generates a Granite script that compiles with JBang;
source and compilation output are in `released-cli/`.

The eleven final Java recordings use Maven Central 0.1.56 while the platform-native CLI
builds run independently. `released-run/environment.json` preserves the CLI version present
at capture start; Java examples do not invoke that executable. The [final native installation receipt](local-install/native-cli-receipt.json) records the later
CLI update to 0.1.56 separately, including its match to the published binary checksum.

## October 11 additions

Models 0.3.58 adds the exact EmbeddingGemma 2 Q8_0 text encoder and Bonsai 2 27B
PTQ1_0 text path. Released-runtime EmbeddingGemma evidence lives under
`benchmark-results/2026-10-11-model-onboarding/` in Models, with all runtime
JARs fetched from Central and checksum receipts. The unchanged eight-probe
oracle gate passes at minimum cosine 0.9998087162015021.

`released-run/bonsai-receipt.json` records the Bonsai script against Models 0.3.58.
It completes the pinned eight-token reference text. Its 64-token context is explicit;
`bonsai-context-failure/` retains the initial heap exhaustion when the example
requested the full advertised context. Neither clip is a performance measurement.
The model remains unqualified for catalog publication under the current comparator policy.

`local-install-0358/` records installation of all 16 published Models modules from
Central, including JARs, POMs and Gradle module metadata.

The native-boundary and shim-retirement figures were joined after the preview showed
them as disconnected components. The combined `native-boundary.mmd` explicitly links
both Rust paths to replacement evaluation and uses plain-text labels. Four Mermaid
figures remain in the article; the prior five-figure versions are historical evidence.

The completed [Bonsai default RAG smoke](https://github.com/integrallis/models/blob/3490dff4b848eb6221b47cbf5a81d247709c05aa/benchmark-results/2026-10-11-model-onboarding/README.md#bonsai-default-rag-smoke-result) retains four model answers, four fallbacks and one abstention. Its source build and uncontrolled shared-host timings are explicitly identified; the absence of a supported authoritative comparator remains a publication constraint.
