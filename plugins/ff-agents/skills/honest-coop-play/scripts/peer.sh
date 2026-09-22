#!/bin/bash
# usage: peer.sh <host|m3|beast> METHOD ROUTE [JSON]
# Drives ONE peer's own player through its agent channel. The body travels on stdin, so no JSON
# quoting survives an ssh hop (BEAST's `bash -lc` cannot carry pipes). Needs ahttp.py deployed at
# $E/ahttp.py (M5, M3) and C:\Users\rydin\ff-worker\ahttp.py (BEAST), and the player pids in
# $E/peer-pid-{host,m3,beast} (write them after launch).
set -u
E=${FF_COOP_LAB:-/Users/benryding/nevergames/ff-audit-artifacts/074-20260921}
peer=$1; method=$2; route=$3; body=${4:-}
case "$peer" in
  host)  printf '%s' "$body" | python3 "$E/ahttp.py" "$(cat "$E/peer-pid-host")" "$method" "$route" ;;
  m3)    printf '%s' "$body" | ssh -o ConnectTimeout=10 m3 "python3 $E/ahttp.py $(cat "$E/peer-pid-m3") $method $route" ;;
  beast) printf '%s' "$body" | ssh -o ConnectTimeout=10 -o Hostname=10.0.0.158 beast "python C:\\Users\\rydin\\ff-worker\\ahttp.py $(cat "$E/peer-pid-beast") $method $route" ;;
  *) echo "unknown peer $peer (host|m3|beast)"; exit 2 ;;
esac
