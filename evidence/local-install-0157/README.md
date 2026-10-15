# ModelJars local installation

All six library publications were downloaded from Maven Central and compared against
SHA-256 values extracted from the signed CI release bundle. `coordinates.json` holds
the expected values; `maven-local-receipt.json` records the installed bytes and any
previous local digests. The bundle and its digest are retained separately.

The native CLI installation is tracked separately. `jvm-cli-receipt.json` identifies
the locally rebuilt distribution and its source commit. The EmbeddingGemma marker's
independent Central and Maven Local receipts are in `../embeddinggemma-marker-bundle/`.
