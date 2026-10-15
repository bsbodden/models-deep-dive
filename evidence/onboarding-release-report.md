# October 11 model onboarding and article follow-up

Completed October 11, 2026. Runtime, catalog, CLI, local installations and article assets are verified. Bonsai production qualification remains open as described below. See [live release receipts](onboarding-release-progress.json).
This supplements the [earlier article release report](release-report.md); it does not
rewrite the dependency pins or results of the original eleven recordings.

## Released runtime

[Models 0.3.58](https://github.com/integrallis/models/releases/tag/v0.3.58) adds the
EmbeddingGemma 2 text encoder and exact Bonsai 2 27B PTQ1_0 text path. All ten release
jobs passed, including independent Maven and Gradle consumers. All sixteen public
modules were checksum-verified on Central and installed in Maven Local;
[installation receipt](local-install-0358/maven-local-receipt.json).
Vectors remains 0.1.29.

EmbeddingGemma's released runtime passed all eight existing oracle probes, with
minimum cosine 0.9998087162015021 and maximum norm deviation 7.675834412523841e-9.
Every output has 768 dimensions. This qualifies numerical conformance for the exact
Q8_0 text artifact; it does not qualify the separate image, audio or video towers.

## Catalog and dependency changes

[ModelJars PR #216](https://github.com/ModelJars/modeljars/pull/216) is merged. Version
0.1.57 uses Models 0.3.58 and Vectors 0.1.29. Its candidate inventory has 459 entries;
the generated public catalog has 101 qualified physical artifacts and two compositions.
The exact EmbeddingGemma marker and all six library publications are public on
Central and match their signed staging bundles. All six independent Maven and six
Gradle consumers pass with matching dependency graphs. The GitHub release is
published. All five native CLI builds, Homebrew, Scoop and the executable JAR
publication passed. SDKMAN publication remains disabled by repository configuration.
The live website serves the current dependency snippets and qualified catalog.
`/usr/local/bin/modeljars` reports 0.1.57, matches the published macOS Intel checksum,
and passes Homebrew testing. Its generated EmbeddingGemma demo also ran successfully
with the real weights, returning 768 finite, normalized components.

The CLI and site now say “Hidden width” for the model descriptor field, avoiding
confusion between EmbeddingGemma's hidden width 512 and output width 768. Granite
and Harriet catalog dependencies now select their 0.1.57 composition libraries.
A new build check rejects composition coordinates, versions or download URLs that
drift from the library release. All Models dependency locks advance to 0.3.58.

Validation before merge included 325 Node tests and 402 Java tests. Seven default
optional/live tests were skipped; the dedicated real-weight EmbeddingGemma and
LFM2.5 tests each executed and passed. Catalog, modality, profile, qualification,
release dependency and consumer checks passed. Authenticated CI verified the gated
remote metadata that the local shell could not access.

## Bonsai compatibility and remaining qualification

The 5,946,648,928-byte PTQ1_0 file is installed locally and verified by SHA-256.
The Java runtime matches eight greedy completion tokens from the independent
Prism reference, including a separate repeated session. The article's direct
Models 0.3.58 example also completed successfully with those weights.

The complete nine-case source-runtime RAG smoke returned four model answers,
four extractive fallbacks and one retrieval abstention. All passed the small
synthetic workload's checks; no attempt failed or truncated. This meets the absolute
contribution smoke floors, but is not a general quality or performance result.
Merged [Models PR #265](https://github.com/integrallis/models/pull/265) retains raw outputs,
source identity, timings and limits. The measured runtime source trees match the
0.3.58 release source, but the run is still identified as a local source build.

Bonsai remains an unpublished catalog candidate. The exact PTQ1_0 artifact still
needs an authoritative comparator accepted by the existing policy, controlled
paired relative gates, and released-runtime workload evidence. The publisher's
reference fork supplies compatibility evidence but does not substitute for that
comparator. Neither the qualification policy nor its thresholds were weakened.

## Article corrections

The native execution routes and Java replacement gates now form one connected
Mermaid figure. CPU and PTX routes lead to a candidate; numeric, whole-model and
supported-host gates determine replacement. All rejection paths keep the current
route. The original screenshot and diagrams are archived in
[diagram-before-connection](diagram-before-connection/).

The draft has thirteen inline application-code excerpts and four source-synchronized
Mermaid figures. Library/toolchain release numbers are omitted from prose and diagrams;
full runnable companion scripts retain their tested pins. The original eleven recordings preserve their tested ModelJars 0.1.56 pins.
Both additions passed against released artifacts. All thirteen runs have original
casts, source hashes, MP4/WebM exports and poster frames. The two new posters were
visually checked, and all twenty-six deliverable videos passed stream/digest checks.

The first Bonsai recording exposed allocation of the full advertised context with
an insufficient heap. The short example now explicitly requests a 64-token context;
[the original failure remains available](bonsai-context-failure/bonsai.log). File size
is not presented as total runtime memory. The video exporter now verifies source
and cast hashes against successful run receipts before rendering.

The article remains a local draft; it has not been published to Medium.

## Final receipts

- [Marker publication](onboarding-marker-finalization.json) and [byte verification](embeddinggemma-marker-bundle/central-verification.json).
- [Library publication](onboarding-library-finalization.json), [independent consumers](onboarding-central-consumers/results.json), and [installed JVM artifacts](local-install-0157/maven-local-receipt.json).
- [Native release jobs](onboarding-cli-release.json), [installed binary](local-install-0157/native-cli-receipt.json), and [generated real-weight demo](onboarding-cli/verification.json).
- [Website deployment](onboarding-site-release.json) and [live catalog verification](onboarding-site/verification.json).
- [Thirteen successful walkthroughs](released-run/runs.json), [video verification](video-verification.json), and [four regenerated diagram pairs](diagram-renders.json).
- [Clean main checkouts](onboarding-checkouts.json): each project retains only its main branch and one continuation branch locally.

The first native CLI lookup occurred before Pages had deployed the new registry and
therefore saw the previous published catalog. Those logs remain under
`onboarding-cli/before-site-deployment/`; the subsequent default online lookup,
script generation and real-weight execution all passed after deployment.
