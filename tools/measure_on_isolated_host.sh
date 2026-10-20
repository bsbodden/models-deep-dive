#!/usr/bin/env bash
# Measure code/grouping.java on a host that is doing nothing else.
#
# A batch of typed decisions is seconds of local compute, and this workstation runs an editor and
# a screen recorder: two runs of identical code have differed by 2x here. That is survivable for
# the fleet comparison, where the finding is which arm is predictable, and useless for a
# before-and-after of two library versions. So this provisions a dedicated-vCPU host, runs both
# versions on it twice each, brings the logs back, and deletes the host.
#
# It spends money. It refuses to run without --confirm, prints the live price first, and deletes
# the server and its firewall on every exit path, including a failure. Follow
# ../../VPS-BENCHMARK-OPERATIONS.md if you change any of this; every rule in it was learned by
# leaving something running.
set -euo pipefail

# Exported, not just set: the helpers below read these through os.environ, and a shell variable
# that is merely assigned is invisible to them -- which fails with a KeyError after the price
# lookup rather than before it.
export VERSIONS=${VERSIONS:-"0.1.61 0.1.62"}
export PASSES=${PASSES:-2}
export TYPE=${TYPE:-ccx33}
export LOCATION=${LOCATION:-ash}
export IMAGE=${IMAGE:-ubuntu-24.04}
export SSH_KEY_ID=${SSH_KEY_ID:-114663461}        # Hetzner key 'vectors-bench-v2'
export CEILING_HOURS=${CEILING_HOURS:-3}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/evidence/harriet-decisions"
export STAMP="$(date -u +%Y%m%d%H%M)"
export NAME="modeljars-bench-cpu-${STAMP}"

[ "${1:-}" = "--confirm" ] || {
  echo "This provisions a paid Hetzner $TYPE and deletes it afterwards."
  echo "Re-run with --confirm to proceed. Versions: $VERSIONS, passes: $PASSES."
  exit 2
}

# shellcheck source=isolated_host.sh
source "$(dirname "${BASH_SOURCE[0]}")/isolated_host.sh"
CEILING_HOURS=$CEILING_HOURS isolated_host_up "modeljars-bench-cpu"
isolated_host_install_java

mkdir -p "$OUT"
remote 'lscpu | grep -E "^Model name|^CPU\(s\)|^Thread|^Core"; free -h | head -2; uptime' > "$OUT/host-baseline.txt"

remote 'mkdir -p ~/probe'
push "$ROOT/code/grouping.java" '~/probe/grouping.java'

for version in $VERSIONS; do
  remote "cd ~/probe && sed 's|harriet:[0-9.]*|harriet:$version|' grouping.java > grouping-$version.java"
done
# One warm-up run that nothing reads, so no measured run pays for the weight download.
remote 'export PATH=/opt/java/bin:~/.jbang/bin:$PATH JAVA_HOME=/opt/java; cd ~/probe && jbang grouping-'"${VERSIONS%% *}"'.java >/dev/null 2>&1'

for pass in $(seq 1 "$PASSES"); do
  for version in $VERSIONS; do
    remote 'export PATH=/opt/java/bin:~/.jbang/bin:$PATH JAVA_HOME=/opt/java; cd ~/probe
      { echo "harriet '"$version"', pass '"$pass"'"; echo "load at start: $(cat /proc/loadavg)";
        jbang grouping-'"$version"'.java 2>&1 | grep -viE "^WARNING|incubator|^\[jbang\]|^INFO|^\[";
        echo "load at end: $(cat /proc/loadavg)"; }' > "$OUT/grouping-${version//./}-pass$pass.log"
    echo "measured $version pass $pass"
  done
done

# The article quotes one log per version; the last pass of each is the one it reads, and every
# pass is kept beside it so the spread is visible rather than asserted.
for version in $VERSIONS; do
  cp "$OUT/grouping-${version//./}-pass$PASSES.log" "$OUT/grouping-${version//./}.log"
done
echo "logs in $OUT"
