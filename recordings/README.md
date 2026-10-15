# Recorded walkthrough

The thirteen Java scripts are the source of both the inline article code and these real-weight terminal demos. The original eleven passed against ModelJars 0.1.56. The two additions use Models 0.3.58: EmbeddingGemma 2 through ModelJars 0.1.57, and Bonsai directly through Models. All thirteen runs passed. Execution receipts distinguish each script's actual dependency versions.

Open [the interactive player](index.html) through a local HTTP server; each episode links its Java source, original cast, MP4 and WebM. The source and cast hashes are retained in [the execution receipts](../evidence/released-run/runs.json).

## Preparation

1. Run the full sequence in [code/README.md](../code/README.md). This resolves dependencies,
   downloads and verifies real weights, and warms compilation caches.
2. Capture `java -version`, `jbang version`, `modeljars version` and the dependency pins.
3. Use a 120-column terminal, readable monospace font, and the same terminal theme as the
   Vectors recordings. Avoid showing unrelated shell history or environment variables.
4. Record discovery separately from inference. Label inference sessions “weights cached.”

To run the full sequence and retain raw casts plus source/dependency receipts:

```bash
python3 ../tools/run_examples.py --record --output ../evidence/released-run
```

The output directory must be new. The runner propagates child failures (`asciinema --return`)
and extracts terminal output into companion logs. It never shortens recorded timing.

For individual clips, with asciinema 3 run from this directory:

```bash
asciinema record --help
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang chat.java' 01-chat.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang safetensors.java' 02-safetensors.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang embed.java' 03-embed.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang rerank.java' 04-rerank.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang tools.java' 05-tools.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang composite.java' 06-composite.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang decisions.java' 07-decisions.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang speech.java' 08-speech.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang spring.java' 09-spring.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang route.java' 10-route.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang rag.java' 11-rag.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang gemma.java' 12-gemma.cast
asciinema record --return -f asciicast-v2 -c 'cd ../code && jbang bonsai.java' 13-bonsai.cast
```

The original eleven episode numbers remain stable; the two additions are appended. Each clip needs a short title, the command and the
actual output. Preserve the original cast timing. Edited exports can shorten idle periods,
but must label that editing; they are demonstrations, not wall-clock benchmark evidence.

For the speech clip, play the generated `speech.wav` as the audio track in the edited
export. The terminal cast contains no audio. Preserve the WAV and record its sample rate,
channel count and duration beside the export.

## Editing notes

- Chat: point out runtime-owned template and resource lifetime; do not interpret one-token
  decode throughput as a useful benchmark.
- Embedding: show dimensions and a component preview, then connect to Vectors.
- EmbeddingGemma 2: distinguish hidden width 512 from embedding output width 768, and show the query/document prefixes.
- Bonsai: keep the 64-token context and exact-file verification visible; eight matching completion tokens establish compatibility, not production RAG qualification.
- Reranking: show all candidates and scores without calling scores probabilities.
- Tools: include proposed calls and the handler's resulting in-memory state.
- Decisions: keep the weak binary billing answer and disagreeing queue classification.
- Routing: keep the “no matching host measurement” warning; estimates are not measurements.
- RAG: keep retrieval, raw generation, grounding outcome and returned answer in view.

## Video exports

The exports follow the Vectors article: a terminal player, 1920×1080 MP4/WebM clips and PNG
poster frames. Playback uses the original output with `idleTimeLimit: 3`, speed 1. Longer
pauses are shortened and labeled in the frame; the original casts retain full timing.
The speech video adds the generated `speech.wav` in the final hold. The terminal-only capture
is retained as `08-speech-terminal.webm`; both deliverable formats include the voice.

From the article root, serve the files locally:

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/recordings/`. To regenerate videos with the same installed
Puppeteer/Chrome tools used for the diagram exports and `ffmpeg`/`ffprobe` on PATH:

```bash
node tools/export_recordings.mjs /private/tmp/models-article-mermaid/node_modules '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' http://127.0.0.1:8765
```

Append an episode name, such as `speech`, to regenerate only that video. The exporter
checks that all thirteen released runs passed and their source hashes match before rendering. Source/cast/export hashes
and audio placement are in [video-exports.json](../evidence/video-exports.json).
The [WAV receipt](../evidence/released-run/speech-audio.json) records the actual sample rate,
channels, duration and digest. The original capture environment is preserved; the native
CLI installation completed separately from Java inference recording.

