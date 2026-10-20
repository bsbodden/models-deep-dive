# Reproducing this experiment

```bash
export HF_TOKEN=...            # the HotpotQA rows API needs it; the other three sources do not
python3 fetch_datasets.py 100  # downloads, hashes and cuts the frozen samples

export OPENAI_API_KEY=...      # the all-API arm
export HETZNER_TOKEN=...
LIMIT=100 ./run_on_isolated_host.sh --confirm

python3 score.py               # writes RESULTS.json and prints the verdict per dataset
```

The committed `sample-*.json` files are the frozen samples; re-running the fetcher with the same
seed and sample size reproduces them, and `MANIFEST.json` records every source's SHA-256 so a
changed upstream file is visible rather than silent.

## Pins

| | |
| --- | --- |
| harness | `accuracy.java`, which compiles the article's `code/fleet.java` through `//SOURCES` so the fleet under test is the one the article publishes |
| libraries | whatever `code/fleet.java` pins: ModelJars 0.1.62, Models 0.4.3, Vectors 0.1.30 |
| local models | `bartowski_llama_3_2_1b_instruct_gguf_q4_k_m` for grounded answers, `unsloth_qwen3_5_4b_gguf_q4_k_m` through Harriet for decisions, `google_embeddinggemma_300m_gguf_q8_0` for the task classifier, `qwen3_0_6b_q4_0` for the token ruler |
| provider | `gpt-5.1`, the model the article's no-router arm uses, at 64 output tokens for answers and 16 for labels |
| host | one Hetzner `ccx33`, 8 dedicated vCPU EPYC-Milan, provisioned by the runner and deleted on every exit path |
| datasets | SQuAD v2 dev, HotpotQA distractor validation, SNIPS 2017 validation, TREC coarse — all public, none written here, all hashed in `MANIFEST.json` |
| sample | 100 items per dataset, seed 20261019; SQuAD v2 is cut 50 answerable and 50 unanswerable |
| rubrics | `rubrics-snips.json` and `rubrics-trec.json`, written here from each dataset's own label definitions and given to **both** arms verbatim |
| scoring | SQuAD normalisation, exact match and token F1 for answers; label accuracy for decisions; 10,000-resample paired bootstrap intervals, seed 20261019 |

## What each file is

| file | role |
| --- | --- |
| `README.md` | the protocol: hypothesis, decision rule, kill criteria. Frozen before collection. |
| `fetch_datasets.py` | downloads the four public sources, hashes them, cuts the frozen samples |
| `MANIFEST.json` | every source's URL, byte count and SHA-256, plus each sample's hash |
| `sample-*.json` | the frozen items, committed so a later run scores the same ones |
| `rubrics-*.json` | the label definitions both arms read |
| `accuracy.java` | the measured path: builds one prompt per item, hands it to each arm, writes answers |
| `run_on_isolated_host.sh` | provisions the host, runs all eight combinations, brings results back, deletes the host |
| `results-*.jsonl` | one line per item: answer, latency, token counts, selected model, prompt hash |
| `score.py` | scores the results against gold and applies the protocol's decision rule |
| `RESULTS.json` | what `score.py` concluded, including n and the intervals |
| `FINDINGS.md` | written after scoring: what the numbers say, including anything they cannot say |

The harness writes answers and the scorer writes verdicts, deliberately in that order and in
separate files: the thing that produced the answers never knew what would count as a win.
