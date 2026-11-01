# Sourced by the Hetzner round runners: provision one benchmark box on the
# account's reserved IPv4, and give the box back without giving the IP back.
#
# A Usenet account is only ever used from one public IP. A fresh server gets a
# fresh address, so every round on a new box would show the provider a new IP;
# instead the box borrows a Primary IP that outlives it. That IP is the
# account's identity: teardown deletes the server and never the IP, and
# verifies afterwards that the IP still exists and is free for the next round.
# The box gets no IPv6 at all, so there is no second address to fall back to.
#
# Callers set NAME TYPE IMAGE LOCATION SSH_KEY and may set KEEP; they call
# box_provision, then use $IP and ssh_to, and `trap box_teardown EXIT INT TERM`.

# id or name of the reserved Primary IPv4 the benchmark account belongs to
RESERVED_IP="${HETZNER_PRIMARY_IP:-bench-usenet-owner}"
RESERVED_IP_ID=""
SERVER_ID=""
IP=""

box_say () { echo "== $1 $(date -u +%FT%TZ)"; }
box_die () { echo "!! $1" >&2; exit 1; }

ssh_to () { ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o ServerAliveInterval=30 "root@$IP" "$@"; }

box_provision () {
  local fields assignee
  fields=$(hcloud primary-ip describe "$RESERVED_IP" -o format='{{.ID}} {{.IP}} {{.AssigneeID}}' 2>/dev/null) \
    || box_die "reserved Primary IP '$RESERVED_IP' does not exist. Never create a new one for an
    account that already has an owner IP: that is a second IP. See usenet-providers.md"
  read -r RESERVED_IP_ID IP assignee <<<"$fields"
  # a second round on the same IP would run two benchmarks on one account at once
  [ "${assignee:-0}" = 0 ] || box_die "reserved IP $IP is attached to server $assignee: another round is running"

  box_say "PROVISION $NAME ($TYPE, $IMAGE, $LOCATION) on reserved IP $IP"
  hcloud server create --name "$NAME" --type "$TYPE" --image "$IMAGE" \
    --location "$LOCATION" --ssh-key "$SSH_KEY" \
    --primary-ipv4 "$RESERVED_IP_ID" --without-ipv6 >/dev/null
  SERVER_ID=$(hcloud server describe "$NAME" -o format='{{.ID}}')
  local got
  got=$(hcloud server ip "$NAME")
  [ "$got" = "$IP" ] || box_die "server came up on $got, not the reserved $IP"
  echo "   id $SERVER_ID at $IP (reserved, id $RESERVED_IP_ID), no IPv6"

  # A provider recycles addresses, and the reserved IP carries the previous
  # round's host key. accept-new refuses a CHANGED key, which would lock the
  # run out and look like a server that never booted.
  ssh-keygen -R "$IP" >/dev/null 2>&1 || true
  box_say "WAIT for ssh"
  local _
  for _ in $(seq 1 40); do
    ssh_to true >/dev/null 2>&1 && break
    sleep "${BOX_SSH_RETRY_S:-5}"
  done
  ssh_to true >/dev/null 2>&1 || box_die "never became reachable over ssh"
  # verify from the inside: the only egress is the reserved IPv4
  local egress v6
  egress=$(ssh_to 'curl -4 -s --max-time 10 https://ifconfig.me' || true)
  v6=$(ssh_to 'ip -6 addr show scope global | grep -c inet6' || true)
  [ "$egress" = "$IP" ] || box_die "box egress is '$egress', not the reserved $IP"
  [ "${v6:-0}" = 0 ] || box_die "box has a global IPv6 address; the account would see a second IP"
  echo "   reachable; egress $egress, no global IPv6"
}

box_teardown () {
  local status=$?
  set +e
  if [ -n "${KEEP:-}" ]; then
    echo
    box_say "KEEPING $NAME (${IP:-no ip}) because --keep was given. Delete it with:"
    echo "   hcloud server delete $NAME   # never delete the Primary IP"
    return
  fi
  [ -z "$SERVER_ID" ] && return
  echo
  box_say "TEARDOWN $NAME"
  hcloud server delete "$NAME" >/dev/null 2>&1 \
    && echo "   server deleted" \
    || echo "   server delete reported an error; verifying anyway"

  local leftover=0 assignee
  if hcloud server describe "$NAME" >/dev/null 2>&1; then
    echo "   !! server $NAME still exists and is billing"; leftover=1
  fi
  assignee=$(hcloud primary-ip describe "$RESERVED_IP_ID" -o format='{{.AssigneeID}}' 2>/dev/null)
  if [ -z "$assignee" ]; then
    echo "   !! the reserved IP $IP is GONE: the account has lost its owner IP"; leftover=1
  elif [ "$assignee" != 0 ]; then
    echo "   !! the reserved IP $IP is still attached to server $assignee"; leftover=1
  fi
  if [ "$leftover" = 0 ]; then
    box_say "VERIFIED: server gone, reserved IP $IP kept and free"
  else
    echo "!! CHECK BY HAND: hcloud server list; hcloud primary-ip list" >&2
    [ "$status" = 0 ] && status=1
  fi
  [ -n "$IP" ] && ssh-keygen -R "$IP" >/dev/null 2>&1
  exit $status
}
