#!/usr/bin/env bash
# Measure every candidate grounding arm on one idle host, in one run.
#
# Spends money: a few hours of a Hetzner ccx33 and a hundred gpt-5.1 calls. Refuses without
# --confirm, prints the live price first, and deletes the server and its firewall on every exit
# path -- see ../../tools/isolated_host.sh.
#
# The samples are this experiment's own committed ones; the scorer is ../routing-accuracy's,
# imported unchanged, so an arm that wins here wins on the measuring stick that failed the others.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LIMIT=${LIMIT:-50}
ARMS=${ARMS:-"small llama1b llama3.1-8b frontier"}
# Selectable so the confirmation run can re-measure one dataset without recompiling anything.
DATASETS=${DATASETS:-"coqa quac"}

[ "${1:-}" = "--confirm" ] || {
  echo "Provisions a paid host and calls gpt-5.1. Re-run with --confirm."
  echo "Arms: $ARMS, datasets: $DATASETS, items per dataset: $LIMIT"
  exit 2
}
: "${OPENAI_API_KEY:?export OPENAI_API_KEY; the frontier arm needs it}"

# shellcheck source=../../tools/isolated_host.sh
source "$ROOT/tools/isolated_host.sh"
# `|| exit`: isolated_host_up returns non-zero when Hetzner refuses the create, and a
# runner that ignores that goes on to ssh at an empty address for the rest of its life.
CEILING_HOURS=6 isolated_host_up "local-only-chat" || exit 1
remote 'lscpu | grep -E "^Model name|^CPU\(s\)"; free -h | head -2; df -h / | tail -1' \
  > "$HERE/host-baseline.txt"
isolated_host_install_java

remote 'mkdir -p ~/chat'
# The provider key goes to the host in a file the key's owner can read and nobody else can. It used
# to be interpolated into each remote command, which put it in `ps` output and in the host's shell
# history for the whole run.
KEY_FILE="$(mktemp)"
chmod 600 "$KEY_FILE"
printf 'export OPENAI_API_KEY=%s\n' "$OPENAI_API_KEY" > "$KEY_FILE"
push "$KEY_FILE" '~/chat/.provider-key'
remote 'chmod 600 ~/chat/.provider-key'
rm -f "$KEY_FILE"
push "$HERE/chat.java" '~/chat/chat.java'
for dataset in $DATASETS; do
  push "$HERE/sample-$dataset.json" "~/chat/sample-$dataset.json"
done

for arm in $ARMS; do
  for dataset in $DATASETS; do
    echo "=== $arm / $dataset ==="
    remote "export PATH=/opt/java/bin:~/.jbang/bin:\$PATH JAVA_HOME=/opt/java
      cd ~/chat
      { date -u +'started %Y-%m-%dT%H:%M:%SZ'; echo \"load: \$(cat /proc/loadavg)\";
        . ./.provider-key; jbang chat.java $arm sample-$dataset.json $LIMIT;
        date -u +'finished %Y-%m-%dT%H:%M:%SZ'; }" \
      > "$HERE/log-$arm-$dataset.txt" 2>&1 \
      || { echo "FAILED: $arm/$dataset"; tail -12 "$HERE/log-$arm-$dataset.txt"; }
    pull "~/chat/results-$arm-$dataset.jsonl" "$HERE/" 2>/dev/null \
      && echo "  $(wc -l < "$HERE/results-$arm-$dataset.jsonl") rows" \
      || echo "  no rows"
  done
done
echo "collection complete; score with python3 score_chat.py"
