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

  # Sweep up after any run that was killed between its server delete and its firewall delete. The
  # teardown deletes the server, waits for the firewall to detach, and only then deletes it; a run
  # killed inside that wait leaves a firewall behind, which has happened twice. Unattached and
  # carrying this project's label is enough to identify one -- a firewall in use is never
  # unattached.
  hetzner 'https://api.hetzner.cloud/v1/firewalls' | python3 -c 'import json,sys
for firewall in json.load(sys.stdin)["firewalls"]:
    if not firewall["applied_to"] and firewall.get("labels", {}).get("purpose") == "modeljars-benchmark":
        print(firewall["id"])' | while read -r orphan; do
    echo "sweeping orphan firewall $orphan from an earlier killed run"
    hetzner -X DELETE "https://api.hetzner.cloud/v1/firewalls/$orphan" -o /dev/null || true
  done

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
  # A create that failed is an error to report, not a blank id to carry forward. Hetzner refuses
  # with `resource_limit_exceeded` once the account's dedicated cores are committed -- a second
  # host while the first is up -- and the old code fed the error body to a JSON parser, printed a
  # stack trace, and then waited forever for a server that does not exist, with the firewall
  # already created and nothing to tear it down.
  if ! SERVER_ID="$(python3 -c 'import json,sys
created = json.load(sys.stdin)
if "server" not in created:
    error = created.get("error", {})
    code = error.get("code", "?")
    message = error.get("message", created)
    sys.exit("hetzner refused the server: " + str(code) + ": " + str(message))
print(created["server"]["id"])' <<<"$created")"; then
    isolated_host_down
    return 1
  fi
  SERVER_IP="$(python3 -c 'import json,sys;print(json.load(sys.stdin)["server"]["public_net"]["ipv4"]["ip"])' <<<"$created")"
  KNOWN_HOSTS="$(mktemp)"
  echo "server $SERVER_ID at $SERVER_IP"
  # EXIT alone is not enough: a parent killed with SIGTERM -- a stopped background task, a closed
  # terminal, a CI cancellation -- skips the EXIT trap and leaves a paid server running. That
  # happened on 2026-10-20 and left a ccx33 billing until it was deleted by hand. INT and TERM are
  # trapped so the teardown runs on the paths that actually occur, and TERM re-raises afterwards so
  # the caller still sees a terminated process.
  trap isolated_host_down EXIT
  trap 'isolated_host_down; trap - TERM; kill -TERM $$' TERM
  trap 'isolated_host_down; exit 130' INT

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
  if [ -n "${SERVER_ID:-}" ]; then
    echo "deleting server $SERVER_ID"
    hetzner -X DELETE "https://api.hetzner.cloud/v1/servers/$SERVER_ID" -o /dev/null || true
    sleep 20
    unset SERVER_ID
  fi
  # Independent of the server, not nested under it. The firewall is created first, so a teardown
  # that lands between the two calls -- a supervisor killing the run seconds in, which happened on
  # 2026-10-20 -- has a firewall and no server. The old guard returned early on an empty SERVER_ID
  # and left the firewall behind.
  if [ -n "${FIREWALL:-}" ]; then
    echo "deleting firewall $FIREWALL"
    hetzner -X DELETE "https://api.hetzner.cloud/v1/firewalls/$FIREWALL" -o /dev/null || true
    unset FIREWALL
  fi
  rm -f "${KNOWN_HOSTS:-/dev/null}"
  # An API that accepted a delete is not an account with nothing running in it.
  hetzner 'https://api.hetzner.cloud/v1/servers' \
    | python3 -c 'import json,sys;print("servers remaining:", [s["name"] for s in json.load(sys.stdin)["servers"]])'
  hetzner 'https://api.hetzner.cloud/v1/firewalls' \
    | python3 -c 'import json,sys
left=[f["name"] for f in json.load(sys.stdin)["firewalls"] if not f["applied_to"]]
print("unattached firewalls:", left)'
}
