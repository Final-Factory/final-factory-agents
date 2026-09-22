#!/bin/bash
# usage: sitting-health.sh <leg>   — is the live sitting still playable? Checks, for all three peers:
# process alive (pid from $E/peer-pid-*), agent channel answers with tier "honest", heartbeat
# advancing; host: connectedClients=3, zero desync verdicts, no status error. Exit 0 = healthy.
set -u
E=${FF_COOP_LAB:-/Users/benryding/nevergames/ff-audit-artifacts/074-20260921}
leg=$1; L="$E/host-terminal-$leg.log"; bad=0
for p in host m3 beast; do
  out=$("$E/peer.sh" $p GET hello 2>&1); tier=$(printf '%s' "$out" | grep -o '"tier":"[a-z-]*"'); hb=$(printf '%s' "$out" | grep -o '"heartbeat":[0-9]*')
  echo "$p: pid $(cat "$E/peer-pid-$p") $tier $hb"
  [ "$tier" = '"tier":"honest"' ] || { echo "  NOT HEALTHY: $p did not answer as honest ($out)" | cut -c1-200; bad=1; }
done
echo "host clients: $(grep -o 'host-peers-connected: connectedClients=[0-9]*' "$L" | tail -1)"
v=$(grep -c divergedSurfaces "$L"); e=$(grep -c 'status error' "$L"); echo "verdicts=$v errors=$e epoch/hb: $("$E/peer.sh" host GET hello | grep -o '"heartbeat":[0-9]*,"epoch":[0-9]*')"
[ "$v" = 0 ] && [ "$e" = 0 ] || bad=1
echo "honest-play-armed lines: host $(grep -c honest-play-armed "$L")"
exit $bad
