# Artifacts excluded from this repository

Four build outputs are not committed. Each is 22–53 MB, each is a reproducible artifact rather than
a record of reasoning, and each has its SHA-256 committed beside it so any claim that depends on it
stays checkable.

| Excluded file | Size | Digest file | SHA-256 |
| --- | --- | --- | --- |
| `local-install/modeljars-macos-x86_64` | 52.9 MB | `local-install/modeljars-macos-x86_64.sha256` | see file |
| `local-install-0157/native-release/modeljars-macos-x86_64` | 52.9 MB | same name + `.sha256` | see file |
| `release-bundle/modeljars-central-bundle.zip` | 22.3 MB | same name + `.sha256` | `6ea25072bcbd5c36df8f44cbf2544b73444d8c2ff639e4a4f569e77e2a2a3f22` |
| `release-bundle-0157/modeljars-central-bundle.zip` | 22.3 MB | same name + `.sha256` | `a5744b61b35e96af4750f1d54f607ea1a5236921f907139047f98a84f07dd2e3` |

The two native CLI binaries are produced by the ModelJars `cli-release` workflow. The two Central
bundles are the signed release bundles the `publish` workflow uploads; both are retrievable from
Maven Central under the coordinates recorded in the `coordinates.json` beside them.

Every digest above was verified against the file it names before the file was excluded, rather than
copied from a manifest.
