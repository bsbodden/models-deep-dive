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
CEILING=8000          # qwen3-0.6b mean is ~3,200 ms on an idle host
ATTEMPTS=5
QUIET=3.5             # the load this article's published pairs were measured below
PATIENCE=600          # seconds to wait for that before attempting anyway

# Keys come from the environment and nowhere else. An env file read by path would put this
# machine's layout in a public repository and would make the harness look like it owns a
# credential it should only borrow.
for key in OPENAI_API_KEY ANTHROPIC_API_KEY; do
  [ -n "$(eval "printf %s \"\${$key:-}\"")" ] || { echo "$key is unset: export it before running"; exit 1; }
done

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
  mean=$(awk '/^qwen3_0_6b_q4_0 /{print $4}' "$OUT/routed.log" | tail -1)
  echo "  qwen3-0.6b mean: ${mean:-none} ms (ceiling $CEILING); end load: $(sysctl -n vm.loadavg)"
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
      echo "qwen3-0.6b mean: $mean ms (acceptance ceiling $CEILING)"
      echo "waited for quiet: ${waited}s of ${PATIENCE}s, threshold $QUIET"
      echo "host: $(sysctl -n machdep.cpu.brand_string), $(sysctl -n hw.logicalcpu) logical CPUs"
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
