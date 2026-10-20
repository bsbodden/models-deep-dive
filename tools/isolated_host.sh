# Provision a Hetzner CPU host, hand back ssh helpers, and delete it on every exit path.
#
# Sourced, not run. Two scripts need a quiet machine for a few hours, and two copies of the
# teardown logic is how an orphan host happens -- the operations runbook has a list of them.
# Everything money-related lives here: the live price lookup, the firewall, the trap, the audit.
#
# Provides, after isolated_host_up:
#   SERVER_ID, SERVER_IP, KNOWN_HOSTS   the host and where its key is recorded
#   remote <command...>                 run a command on it
#   push <local> <remote>               copy a file or directory to it
#   pull <remote> <local>               copy results back
#
# Requires HETZNER_TOKEN in the environment. Never reads projects/.env: a path to a secrets file
# in a public repository is a map, and the key belongs to the caller's shell.

export TYPE=${TYPE:-ccx33}
export LOCATION=${LOCATION:-ash}
export IMAGE=${IMAGE:-ubuntu-24.04}
export SSH_KEY_ID=${SSH_KEY_ID:-114663461}        # Hetzner key 'vectors-bench-v2'
export CEILING_HOURS=${CEILING_HOURS:-6}

hetzner() { curl -fsS -H "Authorization: Bearer $HETZNER_TOKEN" "$@"; }

isolated_host_up() {
  : "${HETZNER_TOKEN:?export HETZNER_TOKEN; it lives in projects/.env and stays there}"
  export STAMP="$(date -u +%Y%m%d%H%M)"
  export NAME="${1:-modeljars-bench}-${STAMP}"

  hetzner 'https://api.hetzner.cloud/v1/server_types' | python3 -c "import json,sys,os
d=json.load(sys.stdin)
t=next(x for x in d['server_types'] if x['name']==os.environ['TYPE'])
p=next(x for x in t['prices'] if x['location']==os.environ['LOCATION'])
hourly=float(p['price_hourly']['gross'])
print(f\"shape: {t['cores']} {t['cpu_type']} vCPU, {t['memory']} GB, USD {hourly:.4f}/hour in \"
      f\"{os.environ['LOCATION']}; ceiling {os.environ['CEILING_HOURS']}h = \"
      f\"USD {hourly*float(os.environ['CEILING_HOURS']):.2f}\")"

  export MY_IP="$(curl -fsS https://ipv4.icanhazip.com)"
  export FIREWALL
  FIREWALL="$(python3 -c "import json,os;print(json.dumps({'name':os.environ['NAME']+'-ssh','rules':[{'direction':'in','protocol':'tcp','port':'22','source_ips':[os.environ['MY_IP']+'/32']}],'labels':{'purpose':'modeljars-benchmark','owner':'integrallis','delete-by':os.environ['STAMP']}}))" \
    | hetzner -X POST 'https://api.hetzner.cloud/v1/firewalls' -H 'Content-Type: application/json' --data-binary @- \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["firewall"]["id"])')"
  echo "firewall $FIREWALL permits TCP/22 from this workstation only"

  local created
  created="$(python3 -c "import json,os;print(json.dumps({'name':os.environ['NAME'],'server_type':os.environ['TYPE'],'image':os.environ['IMAGE'],'location':os.environ['LOCATION'],'ssh_keys':[int(os.environ['SSH_KEY_ID'])],'firewalls':[{'firewall':int(os.environ['FIREWALL'])}],'labels':{'purpose':'modeljars-benchmark','owner':'integrallis','delete-by':os.environ['STAMP']}}))" \
    | hetzner -X POST 'https://api.hetzner.cloud/v1/servers' -H 'Content-Type: application/json' --data-binary @-)"
  export SERVER_ID SERVER_IP KNOWN_HOSTS
  SERVER_ID="$(python3 -c 'import json,sys;print(json.load(sys.stdin)["server"]["id"])' <<<"$created")"
  SERVER_IP="$(python3 -c 'import json,sys;print(json.load(sys.stdin)["server"]["public_net"]["ipv4"]["ip"])' <<<"$created")"
  KNOWN_HOSTS="$(mktemp)"
  echo "server $SERVER_ID at $SERVER_IP"
  trap isolated_host_down EXIT

  until [ "$(hetzner "https://api.hetzner.cloud/v1/servers/$SERVER_ID" | python3 -c 'import json,sys;print(json.load(sys.stdin)["server"]["status"])')" = running ]; do sleep 10; done
  until remote 'true' 2>/dev/null; do sleep 10; done
  ssh-keygen -lf "$KNOWN_HOSTS"
}

remote() {
  ssh -o UserKnownHostsFile="$KNOWN_HOSTS" -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=15 -o ServerAliveInterval=30 "root@$SERVER_IP" "$@"
}

push() { scp -q -r -o UserKnownHostsFile="$KNOWN_HOSTS" "$1" "root@$SERVER_IP:$2"; }
pull() { scp -q -r -o UserKnownHostsFile="$KNOWN_HOSTS" "root@$SERVER_IP:$1" "$2"; }

isolated_host_install_java() {
  remote 'set -e
    apt-get -qq update >/dev/null 2>&1 && apt-get -qq install -y curl unzip zip >/dev/null 2>&1
    curl -fsSL -o /tmp/jdk.tar.gz "https://api.adoptium.net/v3/binary/latest/25/ga/linux/x64/jdk/hotspot/normal/eclipse"
    mkdir -p /opt/java && tar -xzf /tmp/jdk.tar.gz -C /opt/java --strip-components=1
    curl -fsSL https://sh.jbang.dev | bash -s - app setup >/dev/null 2>&1 || true
    /opt/java/bin/java -version 2>&1 | head -1'
}

isolated_host_down() {
  [ -n "${SERVER_ID:-}" ] || return 0
  echo "deleting server $SERVER_ID"
  hetzner -X DELETE "https://api.hetzner.cloud/v1/servers/$SERVER_ID" -o /dev/null || true
  sleep 20
  echo "deleting firewall ${FIREWALL:-none}"
  [ -n "${FIREWALL:-}" ] && hetzner -X DELETE "https://api.hetzner.cloud/v1/firewalls/$FIREWALL" -o /dev/null || true
  rm -f "${KNOWN_HOSTS:-/dev/null}"
  # An API that accepted a delete is not an account with nothing running in it.
  hetzner 'https://api.hetzner.cloud/v1/servers' \
    | python3 -c 'import json,sys;print("servers remaining:", [s["name"] for s in json.load(sys.stdin)["servers"]])'
  unset SERVER_ID
}
