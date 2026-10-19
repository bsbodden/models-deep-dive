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

: "${HETZNER_TOKEN:?export HETZNER_TOKEN (it lives in projects/.env; do not copy that file anywhere)}"
api() { curl -fsS -H "Authorization: Bearer $HETZNER_TOKEN" "$@"; }

PRICE="$(api 'https://api.hetzner.cloud/v1/server_types' \
  | python3 -c "import json,sys,os
d=json.load(sys.stdin)
t=next(x for x in d['server_types'] if x['name']==os.environ['TYPE'])
p=next(x for x in t['prices'] if x['location']==os.environ['LOCATION'])
print(f\"{t['cores']} {t['cpu_type']} vCPU, {t['memory']} GB, USD {float(p['price_hourly']['gross']):.4f}/hour\")")"
echo "shape: $PRICE in $LOCATION; ceiling ${CEILING_HOURS}h"

export MY_IP="$(curl -fsS https://ipv4.icanhazip.com)"
export FIREWALL
FIREWALL="$(python3 -c "import json,os;print(json.dumps({'name':os.environ['NAME']+'-ssh','rules':[{'direction':'in','protocol':'tcp','port':'22','source_ips':[os.environ['MY_IP']+'/32']}],'labels':{'purpose':'modeljars-benchmark','owner':'integrallis','delete-by':os.environ['STAMP']}}))" \
  | api -X POST 'https://api.hetzner.cloud/v1/firewalls' -H 'Content-Type: application/json' --data-binary @- \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["firewall"]["id"])')"
echo "firewall $FIREWALL permits TCP/22 from this workstation only"

SERVER="$(python3 -c "import json,os;print(json.dumps({'name':os.environ['NAME'],'server_type':os.environ['TYPE'],'image':os.environ['IMAGE'],'location':os.environ['LOCATION'],'ssh_keys':[int(os.environ['SSH_KEY_ID'])],'firewalls':[{'firewall':int(os.environ['FIREWALL'])}],'labels':{'purpose':'modeljars-benchmark','owner':'integrallis','delete-by':os.environ['STAMP']}}))" \
  | api -X POST 'https://api.hetzner.cloud/v1/servers' -H 'Content-Type: application/json' --data-binary @-)"
SERVER_ID="$(python3 -c 'import json,sys;print(json.load(sys.stdin)["server"]["id"])' <<<"$SERVER")"
SERVER_IP="$(python3 -c 'import json,sys;print(json.load(sys.stdin)["server"]["public_net"]["ipv4"]["ip"])' <<<"$SERVER")"
echo "server $SERVER_ID at $SERVER_IP"

KNOWN_HOSTS="$(mktemp)"
cleanup() {
  echo "deleting server $SERVER_ID"
  api -X DELETE "https://api.hetzner.cloud/v1/servers/$SERVER_ID" -o /dev/null || true
  sleep 20
  echo "deleting firewall $FIREWALL"
  api -X DELETE "https://api.hetzner.cloud/v1/firewalls/$FIREWALL" -o /dev/null || true
  rm -f "$KNOWN_HOSTS"
  # The audit is the point: an API that accepted a delete is not the same as an account with
  # nothing running in it.
  api 'https://api.hetzner.cloud/v1/servers' \
    | python3 -c 'import json,sys;print("servers remaining:", [s["name"] for s in json.load(sys.stdin)["servers"]])'
}
trap cleanup EXIT

until [ "$(api "https://api.hetzner.cloud/v1/servers/$SERVER_ID" | python3 -c 'import json,sys;print(json.load(sys.stdin)["server"]["status"])')" = running ]; do sleep 10; done
remote() { ssh -o UserKnownHostsFile="$KNOWN_HOSTS" -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=15 "root@$SERVER_IP" "$@"; }
until remote 'true' 2>/dev/null; do sleep 10; done
ssh-keygen -lf "$KNOWN_HOSTS"

mkdir -p "$OUT"
remote 'lscpu | grep -E "^Model name|^CPU\(s\)|^Thread|^Core"; free -h | head -2; uptime' > "$OUT/host-baseline.txt"

remote 'set -e
apt-get -qq update >/dev/null 2>&1 && apt-get -qq install -y curl unzip zip >/dev/null 2>&1
curl -fsSL -o /tmp/jdk.tar.gz "https://api.adoptium.net/v3/binary/latest/25/ga/linux/x64/jdk/hotspot/normal/eclipse"
mkdir -p /opt/java && tar -xzf /tmp/jdk.tar.gz -C /opt/java --strip-components=1
curl -fsSL https://sh.jbang.dev | bash -s - app setup >/dev/null 2>&1 || true
mkdir -p ~/probe'
scp -q -o UserKnownHostsFile="$KNOWN_HOSTS" "$ROOT/code/grouping.java" "root@$SERVER_IP:~/probe/grouping.java"

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
