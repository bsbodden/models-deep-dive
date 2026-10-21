#!/usr/bin/env bash
# Measure every candidate grounding arm on one idle host, in one run.
#
# Spends money: a few hours of a Hetzner ccx33 and a hundred gpt-5.1 calls. Refuses without
# --confirm, prints the live price first, and deletes the server and its firewall on every exit
# path -- see ../../tools/isolated_host.sh.
#
# The samples and the scorer come from ../routing-accuracy, unchanged: an arm that wins here has to
# win on the same questions and the same measuring stick that failed the 1B arm.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LIMIT=${LIMIT:-50}
ARMS=${ARMS:-"llama1b qwen3-8b llama3.1-8b frontier"}
# Selectable so the confirmation run can re-measure one dataset without recompiling anything.
DATASETS=${DATASETS:-"squad2 hotpotqa"}
# Skip this many items first, so a sample too big for one supervised run can be
# measured in windows and merged. The window ends up in the result file's name.
OFFSET=${OFFSET:-0}

[ "${1:-}" = "--confirm" ] || {
  echo "Provisions a paid host and calls gpt-5.1. Re-run with --confirm."
  echo "Arms: $ARMS, datasets: $DATASETS, items: $LIMIT from offset $OFFSET"
  exit 2
}
: "${OPENAI_API_KEY:?export OPENAI_API_KEY; the frontier arm needs it}"

# shellcheck source=../../tools/isolated_host.sh
source "$ROOT/tools/isolated_host.sh"
# `|| exit`: isolated_host_up returns non-zero when Hetzner refuses the create, and a
# runner that ignores that goes on to ssh at an empty address for the rest of its life.
CEILING_HOURS=6 isolated_host_up "grounding-arms" || exit 1
remote 'lscpu | grep -E "^Model name|^CPU\(s\)"; free -h | head -2; df -h / | tail -1' \
  > "$HERE/host-baseline.txt"
isolated_host_install_java

remote 'mkdir -p ~/arms'
# The provider key goes to the host in a file the key's owner can read and nobody else can. It used
# to be interpolated into each remote command, which put it in `ps` output and in the host's shell
# history for the whole run.
KEY_FILE="$(mktemp)"
chmod 600 "$KEY_FILE"
printf 'export OPENAI_API_KEY=%s\n' "$OPENAI_API_KEY" > "$KEY_FILE"
push "$KEY_FILE" '~/arms/.provider-key'
remote 'chmod 600 ~/arms/.provider-key'
rm -f "$KEY_FILE"
push "$HERE/arms.java" '~/arms/arms.java'
push "$ROOT/experiments/routing-accuracy/sample-squad2.json" '~/arms/sample-squad2.json'
push "$ROOT/experiments/routing-accuracy/sample-hotpotqa.json" '~/arms/sample-hotpotqa.json'

part=""
[ "$OFFSET" = 0 ] || part=".from$OFFSET"

for arm in $ARMS; do
  for dataset in $DATASETS; do
    echo "=== $arm / $dataset ${part#.} ==="
    remote "export PATH=/opt/java/bin:~/.jbang/bin:\$PATH JAVA_HOME=/opt/java
      cd ~/arms
      { date -u +'started %Y-%m-%dT%H:%M:%SZ'; echo \"load: \$(cat /proc/loadavg)\";
        . ./.provider-key; jbang arms.java $arm sample-$dataset.json $LIMIT $OFFSET;
        date -u +'finished %Y-%m-%dT%H:%M:%SZ'; }" \
      > "$HERE/log-$arm-$dataset$part.txt" 2>&1 \
      || { echo "FAILED: $arm/$dataset"; tail -12 "$HERE/log-$arm-$dataset$part.txt"; }
    pull "~/arms/results-$arm-$dataset$part.jsonl" "$HERE/" 2>/dev/null \
      && echo "  $(wc -l < "$HERE/results-$arm-$dataset$part.jsonl") rows" \
      || echo "  no rows"
  done
done
echo "collection complete; score with python3 score_arms.py"
