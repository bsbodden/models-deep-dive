# Walkthrough re-verified on ModelJars 0.1.62

The thirteen non-keyed scripts were re-run after the 0.1.62 pins, on 2026-10-19,
by `tools/run_examples.py`. Every one exited 0. `fleet.java` is the fourteenth and is keyed; it is
measured separately by `tools/measure_fleet.sh`, and its pairs live in
`fleet-routing/runs/`.

These are API demonstrations with real weights, not accuracy or throughput benchmarks. Source
hashes, exact dependency lists and per-script timings are in
[runs.json](walkthrough-0.1.62/runs.json); the environment it ran under is in
[environment.json](walkthrough-0.1.62/environment.json).

Two outputs moved against the 0.1.61 run, and neither is a regression in the library:
`speech.java` reported RTF 1.470 against 1.350, which is one run of a synthesis script on a laptop
that was also doing other things, and `decisions.java` returned the same three verdicts to three
decimal places (`true p=0.920`, `billing p=0.991`, `today p=0.389`), which is what a runtime change
that only moves where a prefix is resumed should do.

| Script | Exit | Dependencies | Output |
| --- | --- | --- | --- |
| [chat.java](../code/chat.java) | 0 | `org.modeljars:modeljars:0.1.62<br>org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1` | [chat.log](walkthrough-0.1.62/chat.log) |
| [safetensors.java](../code/safetensors.java) | 0 | `org.modeljars:modeljars:0.1.62<br>org.modeljars.huggingface:qwen.qwen2.5-0.5b-instruct.bf16:2.5.0-bf16.2` | [safetensors.log](walkthrough-0.1.62/safetensors.log) |
| [embed.java](../code/embed.java) | 0 | `org.modeljars:modeljars:0.1.62<br>org.modeljars.huggingface:liquidai.lfm2.5-embedding-350m-gguf.q4_0:2.5.0-q4_0.1` | [embed.log](walkthrough-0.1.62/embed.log) |
| [rerank.java](../code/rerank.java) | 0 | `org.modeljars:modeljars:0.1.62<br>org.modeljars.huggingface:cstr.ms-marco-minilm-l-6-v2-gguf.q4_k_imatrix_g7c_f7:2.0.0-q4_k_imatrix_g7c_f7.2` | [rerank.log](walkthrough-0.1.62/rerank.log) |
| [tools.java](../code/tools.java) | 0 | `org.modeljars:modeljars:0.1.62<br>org.modeljars.huggingface:cactus-compute.needle2-cact.cq2_mixed:2.0.0-cq2_mixed.2` | [tools.log](walkthrough-0.1.62/tools.log) |
| [composite.java](../code/composite.java) | 0 | `org.modeljars.composite:granite-answerability:0.1.62` | [composite.log](walkthrough-0.1.62/composite.log) |
| [decisions.java](../code/decisions.java) | 0 | `org.modeljars.composite:harriet:0.1.62` | [decisions.log](walkthrough-0.1.62/decisions.log) |
| [speech.java](../code/speech.java) | 0 | `org.modeljars:modeljars:0.1.62<br>org.modeljars.huggingface:walkingcat.soprano-1.1-80m-gguf.bf16:1.1.0-bf16.1` | [speech.log](walkthrough-0.1.62/speech.log) |
| [spring.java](../code/spring.java) | 0 | `org.modeljars:modeljars:0.1.62<br>org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1` | [spring.log](walkthrough-0.1.62/spring.log) |
| [route.java](../code/route.java) | 0 | `org.modeljars:modeljars:0.1.62<br>org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1<br>org.modeljars.huggingface:qwen.qwen2.5-0.5b-instruct.bf16:2.5.0-bf16.2` | [route.log](walkthrough-0.1.62/route.log) |
| [rag.java](../code/rag.java) | 0 | `org.modeljars:modeljars:0.1.62<br>org.modeljars.huggingface:second-state.all-minilm-l6-v2-embedding-gguf.q4_k_m:2.0.0-q4_k_m.2<br>org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1` | [rag.log](walkthrough-0.1.62/rag.log) |
| [gemma.java](../code/gemma.java) | 0 | `org.modeljars:modeljars:0.1.62<br>org.modeljars.huggingface:ggml-org.embeddinggemma-2-gguf.q8_0:2.0.0-q8_0.1` | [gemma.log](walkthrough-0.1.62/gemma.log) |
| [bonsai.java](../code/bonsai.java) | 0 | `-` | [bonsai.log](walkthrough-0.1.62/bonsai.log) |
