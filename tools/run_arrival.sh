#!/usr/bin/env bash
# The two states a fleet is in before and after a model is added, produced for real.
#
# The only difference between the runs is one Maven coordinate on the classpath, passed with
# `jbang --deps`. That is the whole act a user performs to add a model: the marker jar carries the
# descriptor, ModelJars fetches the weights on first open, and `CatalogDiscovery` reports the
# candidate from then on, carrying whatever the catalog measured about it.
#
# `code/arrival.java` is byte-identical across both runs. It never learns which phase it is in
# beyond the label it prints, filters nothing, and declares no capability, tag or quality.
#
# An earlier version of this script tried to stage the arrival by moving the artifact out of the
# model cache. It did not work and the failure is worth recording: `ModelJarsCatalog.cached()`
# checks the descriptor's local path AND the content-addressed cache, so the renamed file was
# still found and both phases discovered the same two candidates. The coordinate is the real seam.
set -euo pipefail

ARRIVAL=${ARRIVAL:-org.modeljars.huggingface:cactus-compute.needle2-cact.cq2_mixed:2.0.0-cq2_mixed.2}
OUT=${OUT:-evidence/arrival}
mkdir -p "$OUT"

echo "== phase one: the fleet as it stands"
jbang code/arrival.java before-the-model-is-added > "$OUT/before.log" 2>&1 || {
  tail -20 "$OUT/before.log"; exit 1; }
grep -vE '^\[jbang\]|WARNING: Using incubator' "$OUT/before.log" | tail -30

echo
echo "== phase two: the same script, plus one coordinate"
echo "   --deps $ARRIVAL"
jbang --deps "$ARRIVAL" code/arrival.java after-the-model-is-added > "$OUT/after.log" 2>&1 || {
  tail -20 "$OUT/after.log"; exit 1; }
grep -vE '^\[jbang\]|WARNING: Using incubator' "$OUT/after.log" | tail -30

{
  echo "arrival coordinate: $ARRIVAL"
  echo "script sha256: $(shasum -a 256 code/arrival.java | cut -d' ' -f1)"
  echo "modeljars: $(grep -m1 'DEPS org.modeljars:modeljars:' code/arrival.java | sed 's/.*://')"
  echo "models-router: $(grep -m1 'DEPS com.integrallis:models-router:' code/arrival.java | sed 's/.*://')"
  echo "recorded: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$OUT/.meta"
echo
echo "== wrote $OUT/{before,after}.log and .meta"
