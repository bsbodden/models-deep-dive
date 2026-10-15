# Models and ModelJars deep dive — working outline

The article follows the Vectors deep dive's progression: a concrete Java operation, the
mechanism underneath it, then another runnable step. The original planning document is
preserved in [evidence/outline-2026-10-09.md](evidence/outline-2026-10-09.md).

## Part I: How the layers fit

1. Continue the Vectors story: make embeddings before retrieval and answers after it.
2. Vectors → Models → ModelJars, with the website, CLI, marker and runtime responsibilities.
3. Exact model identity: immutable coordinates, multi-file bundles, verification and cache.
4. Loading sequence: qualification, artifact verification, backend, chat template and lifetime.
5. Java's execution tools: mapped memory, SIMD, FFM; prefill versus decode; quantized blocks.
6. Native boundaries: CPU Rust C ABI, Rust-to-PTX CUDA, separate Swift platform integration.
7. Explain each CPU shim family and distinguish exported capability from selected routing.
8. Retirement conditions, not predicted dates: numerical parity, whole-model speed, lifecycle,
   supported machines, explicit requalification when a numeric contract changes.
9. Model families, workload-specific qualification, compositions and evidence limitations.

Diagrams: [stack](diagrams/stack.mmd), [loading](diagrams/loading.mmd),
[native boundary and replacement checks](diagrams/native-boundary.mmd).

## Part II: Runnable walkthrough and recording sequence

| Episode | Script | Teaching point |
| --- | --- | --- |
| 0 | CLI discovery and pull | Declare exact artifacts; separate downloads from inference. |
| 1 | `chat.java` | Qwen3 GGUF, template, resource lifetime and runtime metrics. |
| 2 | `safetensors.java` | Qwen2.5 BF16 bundle through the same public facade. |
| 3 | `embed.java` | LFM2.5 sequence embeddings, CLS pooling and vector dimensions. |
| 4 | `rerank.java` | Query/document scoring differs from embedding similarity. |
| 5 | `tools.java` | Needle 2 CACT, schema constraints and validated local handlers. |
| 6 | `composite.java` | Granite base + adapter, answerability and observable prefix sharing. |
| 7 | `decisions.java` | Harriet's closed outcomes; expose weak and inconsistent decisions. |
| 8 | `speech.java` | Soprano audio generation and a real WAV artifact. |
| 9 | `spring.java` | Spring AI ChatClient over the local runtime. |
| 10 | `route.java` | Local catalog discovery, selection and measured versus estimated profiles. |
| 11 | `rag.java` | MiniLM → Vectors collection → Qwen → explicit grounding outcome. |
| 12 | `gemma.java` | EmbeddingGemma 2 text prefixes, hidden width and projected output. |
| 13 | `bonsai.java` | Exact PTQ1_0 weights, explicit context and runtime compatibility. |

End with the [RAG diagram](diagrams/rag.mmd) and the connection to the previous article's
persistence and object-storage stages. Do not imply that every architecture or catalog
artifact is exercised by these examples.

## Publication gates

- Fix defects found through the walkthrough and publish corrected artifacts before pinning them.
- Execute every final script against the public release, including real local weights.
- Keep output, source hashes, release identities and command records together.
- Inline code and Mermaid must match the companion files; run `tools/sync_article.py --check`.
- Record the final released scripts with warm caches; preserve unretimed original casts.
- Retain failures and poor model outputs. Distinguish API demonstration from quality evaluation.
- GPU evidence is attributed to retained experiments; no laptop GPU benchmark is claimed.

The prose is in [article.md](article.md), setup in [code/README.md](code/README.md), and
recording instructions in [recordings/README.md](recordings/README.md).
