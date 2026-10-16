# Run the walkthrough

Use Java 25, JBang, and the ModelJars CLI. Each `.java` file declares its Maven dependencies
and runtime flags; run from this directory so generated audio lands in `../recordings/`.
The CLI is useful for discovery and prefetching but is not required by the Java scripts.

```bash
java -version
jbang version
modeljars version
jbang chat.java
jbang safetensors.java
jbang embed.java
jbang rerank.java
jbang tools.java
jbang composite.java
jbang decisions.java
jbang speech.java
jbang spring.java
jbang route.java
jbang rag.java
jbang gemma.java
jbang bonsai.java
```

`route.java` needs no weights: discovery reads each marker jar's descriptor from the
classpath, so it can select between models that have never been downloaded. Opening a
runtime is what fetches.
Run scripts sequentially; they each allow up to 4 GiB of Java heap, in addition to mapped
model files and native memory. This walkthrough was exercised on an Intel Mac with 32 GiB
RAM, Temurin 25.0.3 and JBang 0.141.0. That is a tested configuration, not a minimum-memory claim.

First runs need internet access to resolve JARs and download weights. Models remain in
`~/.modeljars/cache`, verified against their descriptors. Harriet's base is substantially
larger than the smaller chat and embedding examples; allow several gigabytes of disk for
the complete walkthrough. Do not include that download in an inference timing comparison.

To inspect or download an artifact first:

```bash
modeljars show qwen_qwen2_5_0_5b_instruct_bf16
modeljars pull qwen_qwen2_5_0_5b_instruct_bf16
modeljars demo qwen_qwen2_5_0_5b_instruct_bf16 --help
```

The examples cover local generation (GGUF and Safetensors), embeddings, cross-encoder
reranking, tool calls, shared-prefix composition, typed decisions, speech synthesis, Spring AI, routing and retrieval.
GPU and Apple framework integration are explained in the article; these scripts do not
claim to validate either on this Intel laptop.

`tools.java` changes only its own in-memory home state. `speech.java` writes a WAV file.
`rag.java` uses three handwritten documents to demonstrate the API, not a benchmark corpus.
Elapsed times are observations of individual runs, not performance comparisons. Model
outputs can be wrong; the retained Harriet and grounding examples make this explicit.

See [execution evidence](../evidence/runs.json) for the initial run, including the LFM2.5
failure that prompted a library fix. [Final release results](../evidence/walkthrough-results.md) are retained separately so the
original failure is not erased. [Recording instructions](../recordings/README.md).

`gemma.java` is the EmbeddingGemma 2 addition for ModelJars 0.1.57. Its released-artifact run passed and returned 768 dimensions; [the receipt](../evidence/released-run/gemma-receipt.json) records its exact pins and source hash.

`bonsai.java` uses the locally installed exact PTQ1_0 fixture, or a path supplied as its first argument. Download the pinned file linked in the article first; the script verifies its size and SHA-256. Its [recorded released-runtime run](../evidence/released-run/bonsai-receipt.json) passed. It demonstrates direct Models runtime compatibility while catalog production qualification remains pending.
