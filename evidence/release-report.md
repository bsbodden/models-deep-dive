# Article discoveries: corrections and release

Completed October 11, 2026 UTC (October 10 in Phoenix).

## Published and installed

- [ModelJars 0.1.56](https://github.com/ModelJars/modeljars/releases/tag/v0.1.56) is public on Maven Central. All six JARs, POMs and Gradle module descriptors match the signed bundle.
- Dependencies remain **Vectors 0.1.29 → Models 0.3.57 → ModelJars 0.1.56**. The resolved consumer graph is retained. Models documentation corrections are merged; these findings required no new Models or Vectors runtime release.
- All five native CLI builds passed. Homebrew, Scoop and the executable JAR on GitHub Packages were published. SDKMAN publication remains disabled by repository configuration.
- `/usr/local/bin/modeljars` is **0.1.56**, matches the published macOS binary checksum, and passes the Homebrew smoke test.
- The public website's dependency snippets use 0.1.56. All three canonical main checkouts are clean and match their remotes. Merged task branches are removed; the three continuation branches remain.

## Corrections and validation

[Eight findings and their regression evidence](article-findings.md) cover CLS embedding loading,
the Granite demo generator, generated Jackson pins, tool argument bounds, the real Granite
sharing assertion, obsolete GPU setup, CUDA documentation and native recurrence documentation.
Real LFM2.5 and Granite integration gates now run in PR and release validation.

All eleven article scripts passed against released artifacts with real cached weights.
The installed native CLI also generated and successfully executed its Granite demo, reporting
ANSWERABLE and physical prefix sharing. The original failures are preserved.

## Article deliverables

- [Draft article](../article.md), with eleven complete inline scripts and five Mermaid diagrams.
- [Walkthrough results](walkthrough-results.md), raw logs, original casts and source hashes.
- [Interactive recordings](../recordings/index.html), eleven MP4/WebM pairs and poster frames. Speech includes the generated WAV in both video formats.
- [Sources and limits](sources.md): retained weak Harriet output, explicit RAG fallback, and separation of laptop smoke checks from historical GPU experiments.

The article remains a local draft. Library publication is complete; the prose has not been posted to Medium.

## Receipts

[Final release verification](release-final-verify.json) · [Central finalization](release-finalization.json) ·
[Central artifacts installed locally](local-install/maven-local-receipt.json) ·
[Consumer dependency graph](local-install/maven-dependency-tree.log) ·
[CLI platform release](cli-release.json) · [Native installation](local-install/native-cli-receipt.json) ·
[Installed CLI real-weight execution](released-cli/native-run-receipt.json) ·
[Website deployment](site-release.json) · [Clean checkouts](final-checkouts.json) ·
[Video verification](video-verification.json) · [Diagram render hashes](diagram-renders.json).
