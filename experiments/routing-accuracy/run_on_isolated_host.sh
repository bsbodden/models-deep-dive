#!/usr/bin/env bash
# Score both arms on all four datasets, on a host that is doing nothing else.
#
# Spends money twice over: a few hours of one Hetzner ccx33, and provider calls for the all-API
# arm and any item the router escalates. It refuses to run without --confirm, prints the live
# hourly price and the ceiling first, and deletes the server and its firewall on every exit path
# including a failure -- see ../../tools/isolated_host.sh.
#
# The protocol, the decision rule and the kill criteria are in README.md and were frozen before
# the first call. This script only collects; score.py decides.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LIMIT=${LIMIT:-100}

[ "${1:-}" = "--confirm" ] || {
  echo "This provisions a paid Hetzner host and makes provider calls for the all-API arm."
  echo "Re-run with --confirm. Items per dataset: $LIMIT."
  exit 2
}
: "${OPENAI_API_KEY:?export OPENAI_API_KEY; the all-API arm cannot run without it}"

# shellcheck source=../../tools/isolated_host.sh
source "$ROOT/tools/isolated_host.sh"
CEILING_HOURS=6 isolated_host_up "routing-accuracy"
remote 'lscpu | grep -E "^Model name|^CPU\(s\)"; free -h | head -2; uptime' > "$HERE/host-baseline.txt"
isolated_host_install_java

# The harness compiles the article's own fleet.java through //SOURCES, so the directory shape has
# to survive the copy: experiments/routing-accuracy/accuracy.java expects ../../code/fleet.java.
remote 'mkdir -p ~/run/code ~/run/experiments/routing-accuracy'
push "$ROOT/code/fleet.java" '~/run/code/fleet.java'
push "$HERE/accuracy.java" '~/run/experiments/routing-accuracy/accuracy.java'
for file in "$HERE"/sample-*.json "$HERE"/rubrics-*.json; do
  push "$file" "~/run/experiments/routing-accuracy/$(basename "$file")"
done

# One warm run so no measured item pays for the weight download. Its output is discarded.
echo "warming the local arms (weights download on first use)"
remote "export PATH=/opt/java/bin:~/.jbang/bin:\$PATH JAVA_HOME=/opt/java
  cd ~/run/experiments/routing-accuracy && jbang accuracy.java qa routed sample-squad2.json 1" \
  > "$HERE/warmup.log" 2>&1 || { tail -20 "$HERE/warmup.log"; exit 1; }
echo "warm"

# The key reaches the host as an environment variable on each command and is never written to a
# file there. The host is deleted when this script exits, and nothing on it outlives that.
for stage_dataset in "qa squad2" "qa hotpotqa" "decide snips" "decide trec"; do
  set -- $stage_dataset
  stage=$1; dataset=$2
  for arm in routed api; do
    echo "=== $stage/$dataset/$arm ==="
    remote "export PATH=/opt/java/bin:~/.jbang/bin:\$PATH JAVA_HOME=/opt/java
      export OPENAI_API_KEY='$OPENAI_API_KEY'
      cd ~/run/experiments/routing-accuracy
      { echo 'load at start:' \$(cat /proc/loadavg); date -u +'started %Y-%m-%dT%H:%M:%SZ';
        jbang accuracy.java $stage $arm sample-$dataset.json $LIMIT;
        date -u +'finished %Y-%m-%dT%H:%M:%SZ'; }" \
      > "$HERE/log-$stage-$arm-$dataset.txt" 2>&1 \
      || { echo "FAILED: $stage/$dataset/$arm"; tail -15 "$HERE/log-$stage-$arm-$dataset.txt"; }
    pull "~/run/experiments/routing-accuracy/results-$stage-$arm-$dataset.jsonl" "$HERE/" || true
    echo "  $(wc -l < "$HERE/results-$stage-$arm-$dataset.jsonl" 2>/dev/null || echo 0) rows"
  done
done

echo "collection complete; score with python3 score.py"
