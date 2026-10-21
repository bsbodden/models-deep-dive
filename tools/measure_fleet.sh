#!/usr/bin/env bash
# Measure both arms of fleet.java and write the logs straight into evidence/.
#
# Two things this guards against, both of which have already cost a published figure:
#
#   Load contamination. A contended run still prints a complete, plausible table -- once with 96.1%
#   of wall clock inside model calls while every per-call figure was inflated eightfold, because
#   contention slows the calls themselves rather than descheduling the process between them. So the
#   gate is a known model's mean against its quiet baseline, checked after the run, not the share.
#
#   Logs in temp. The scratchpad is cleaned without warning, and figures whose artifact has
#   evaporated cannot be published under this article's own provenance rule. These land in
#   evidence/ directly.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/evidence/fleet-routing"
# The acceptance probe is the liveness arm, and it changed with the fleet. It used to be
# qwen3-0.6b, which served chat until it was measured declining 62 of 100 CoQA items and stopped
# being an arm at all -- it is still loaded for its tokenizer, so it is warmed but never called,
# and its mean no longer appears in the timing table. A gate reading an absent number rejects every
# run forever, which is a harness that has stopped measuring rather than a host that is busy.
#
# smollm2-360m answers the three heartbeats on every run, identical prompts every time, and its
# mean across the six archived pairs and today's runs is 169, 173, 173, 197, 208, 211 and 221 ms.
# The ceiling is 2.5x the slowest of those, the same multiple the old 8000/3200 gate used.
CEILING=550           # smollm2-360m mean is 169-221 ms on a quiet host
ATTEMPTS=5
QUIET=3.5             # the load this article's published pairs were measured below
PATIENCE=600          # seconds to wait for that before attempting anyway

# Keys come from the environment and nowhere else. An env file read by path would put this
# machine's layout in a public repository and would make the harness look like it owns a
# credential it should only borrow.
# OPENAI_API_KEY is required: both arms send the appendix and the synthesis prompt to an OpenAI
# model, and a run without it measures a different workload.
[ -n "${OPENAI_API_KEY:-}" ] || { echo "OPENAI_API_KEY is unset: export it before running"; exit 1; }
# ANTHROPIC_API_KEY is not. The fleet declares claude-haiku-5-5 as a third provider and the router
# has never been able to select it for this prompt set -- the only prompt that reaches the remotes
# at all is the 245,741-token appendix, and Haiku's 200,000-token window rules it out in
# `eligible`. Refusing to run without the key made the harness demand a credential for a call it
# cannot make. Which keys were present is recorded in the pair's .meta instead, because a reader
# comparing two pairs is entitled to know whether an arm was unavailable or merely unchosen.
PROVIDER_KEYS="openai"
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  PROVIDER_KEYS="openai,anthropic"
else
  echo "note: ANTHROPIC_API_KEY is unset; claude-haiku-5-5 is declared but cannot be called"
fi

cd "$ROOT/code"
strip() { grep -viE "^WARNING|incubator|^\[jbang\]|^Oct |^INFO: vectors"; }

for attempt in $(seq 1 $ATTEMPTS); do
  # Wait for a quiet host, but not forever: an open editor and a screen recorder can hold this
  # box above the threshold all afternoon, and a wait with no bound silently collects nothing.
  # Attempting anyway is safe because acceptance is decided after the run, on a known model's mean.
  echo "attempt $attempt: waiting up to ${PATIENCE}s for load < $QUIET"
  waited=0
  until [ "$(sysctl -n vm.loadavg | awk -v q="$QUIET" '{print ($2 < q)}')" = "1" ] \
     || [ "$waited" -ge "$PATIENCE" ]; do sleep 30; waited=$((waited + 30)); done
  start_load="$(sysctl -n vm.loadavg)"
  echo "  start load: $start_load (waited ${waited}s)"
  jbang fleet.java 2>&1 | strip > "$OUT/routed.log"
  mean=$(awk '/^smollm2_360m_instruct_q8_0 /{print $4}' "$OUT/routed.log" | tail -1)
  echo "  smollm2-360m mean: ${mean:-none} ms (ceiling $CEILING); end load: $(sysctl -n vm.loadavg)"
  if [ -n "${mean:-}" ] && [ "$mean" -lt "$CEILING" ]; then
    echo "  accepted"
    jbang fleet.java all-remote 2>&1 | strip > "$OUT/all-remote.log"
    # Archive every accepted pair. The ratio between the arms swings with the provider's queue --
    # measured from 1.08x to 1.86x on identical code -- so a single pair cannot describe it and
    # the article quotes a range over these.
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    mkdir -p "$OUT/runs"
    cp "$OUT/routed.log"     "$OUT/runs/$stamp-routed.log"
    cp "$OUT/all-remote.log" "$OUT/runs/$stamp-all-remote.log"
    # The load readings are not in either log, and a pair cannot be judged without them.
    {
      echo "stamp: $stamp"
      echo "load at start of routed arm: $start_load"
      echo "load after routed arm: $(sysctl -n vm.loadavg)"
      echo "smollm2-360m mean: $mean ms (acceptance ceiling $CEILING)"
      echo "waited for quiet: ${waited}s of ${PATIENCE}s, threshold $QUIET"
      echo "host: $(sysctl -n machdep.cpu.brand_string), $(sysctl -n hw.logicalcpu) logical CPUs"
      echo "provider keys present: $PROVIDER_KEYS"
      # The library versions the arms actually ran. A pair measured before a runtime change is not
      # comparable with one measured after it, and the logs do not say which is which.
      grep -E "^//DEPS org\.modeljars" "$ROOT/code/fleet.java" | sed 's|^//DEPS |pin: |'
    } > "$OUT/runs/$stamp.meta"
    cd "$ROOT"
    python3 tools/derive_fleet_figures.py > evidence/fleet-routing/DERIVED.txt
    python3 tools/run_variance.py > evidence/fleet-routing/VARIANCE.txt
    python3 tools/refresh_article_blocks.py
    python3 tools/article_figures.py
    echo "MEASURE COMPLETE"
    exit 0
  fi
  echo "  rejected, retrying"
done
echo "MEASURE FAILED: no clean run in $ATTEMPTS attempts"
exit 1
