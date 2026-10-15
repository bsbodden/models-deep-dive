# Models 0.3.58 local installation

All 16 public Models modules were downloaded from Maven Central after release run
38156648214 completed. JARs, POMs and Gradle module metadata were checked against
Central checksums before recording their SHA-256 values in `coordinates.json`.
`sync-releases.py` then fetched those exact bytes and installed them in Maven Local.
The receipt records previous digests where an artifact was already present.

Vectors remains at 0.1.29. These files establish publication and local installation,
not device compatibility or performance. The isolated EmbeddingGemma oracle run is
retained in the Models repository's October 11 onboarding evidence.
