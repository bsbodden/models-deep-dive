# Released walkthrough results

All eleven exact article scripts exited successfully with released Maven dependencies.
Source and raw-cast hashes were checked against `released-run/runs.json`.
These are API demonstrations with real weights, not accuracy or throughput benchmarks.

| Script | Exit | Output | Original recording |
| --- | --- | --- | --- |
| [chat.java](../code/chat.java) | 0 | [chat.log](released-run/chat.log) | [01-chat.cast](released-run/01-chat.cast) |
| [safetensors.java](../code/safetensors.java) | 0 | [safetensors.log](released-run/safetensors.log) | [02-safetensors.cast](released-run/02-safetensors.cast) |
| [embed.java](../code/embed.java) | 0 | [embed.log](released-run/embed.log) | [03-embed.cast](released-run/03-embed.cast) |
| [rerank.java](../code/rerank.java) | 0 | [rerank.log](released-run/rerank.log) | [04-rerank.cast](released-run/04-rerank.cast) |
| [tools.java](../code/tools.java) | 0 | [tools.log](released-run/tools.log) | [05-tools.cast](released-run/05-tools.cast) |
| [composite.java](../code/composite.java) | 0 | [composite.log](released-run/composite.log) | [06-composite.cast](released-run/06-composite.cast) |
| [decisions.java](../code/decisions.java) | 0 | [decisions.log](released-run/decisions.log) | [07-decisions.cast](released-run/07-decisions.cast) |
| [speech.java](../code/speech.java) | 0 | [speech.log](released-run/speech.log) | [08-speech.cast](released-run/08-speech.cast) |
| [spring.java](../code/spring.java) | 0 | [spring.log](released-run/spring.log) | [09-spring.cast](released-run/09-spring.cast) |
| [route.java](../code/route.java) | 0 | [route.log](released-run/route.log) | [10-route.cast](released-run/10-route.cast) |
| [rag.java](../code/rag.java) | 0 | [rag.log](released-run/rag.log) | [11-rag.cast](released-run/11-rag.cast) |

Harriet’s binary billing decision remains weak and disagrees with its queue result.
RAG returns an extractive fallback after the policy rejects the short generated answer.
Granite reports physical prefix sharing; equality against recomputation is tested separately
by the real-weight release gate. The generated audio format and hash are in
[speech-audio.json](released-run/speech-audio.json).
