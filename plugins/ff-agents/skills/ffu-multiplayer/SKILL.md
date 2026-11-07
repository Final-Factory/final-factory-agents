---
name: ffu-multiplayer
description: Run and check multiplayer in Final Factory Universe (FFU), the Rust engine in Final-Factory/ffu - an `ffu-server` sector or world shard, followers, joining clients and the window as a client, seeded bots and the thin `ffu-bots` fleet, the delay and loss proxy, peered shards with a replica and a standby, replaying one station alone, and reading each command's JSON line. Use for any FFU session with a server and clients, a bot or soak run, a latency leg, or a shard handover; it replaces the paired-editor sessions of determinism-audit and honest-coop-play there.
---

# Multiplayer in FFU

There are no editors to pair. A server is one process, every client is another, and each prints one JSON line when it
starts and one when it ends. Build once (`/ff-agents:ffu-build-test` has the toolchain), then call the binaries:

```sh
cargo build --release -p ffu-server -p ffu-bots
cargo build --release -p ffu-client                     # the `ffu` window as a client
B="$CARGO_TARGET_DIR/release"                           # or target/release
```

Every process you start must end by itself: give a server `--ticks N` or `--exit-on-stdin-close` fed by a `sleep`,
and a client `--seconds S` or a `timeout -s TERM` (the scripts in `tools/` do both). Put each run in a new
`$TMPDIR/<leg>-<time>` folder.

## A sector server and its clients

```sh
sleep 40 | $B/ffu-server --dir "$OUT/sector" --start factory:2000:1 --tps 16 --listen 127.0.0.1:0 \
    --exit-on-stdin-close > "$OUT/server.out" &                  # first line: {"cmd":"server","listen":...,"hash":...}
$B/ffu-server bot --connect 127.0.0.1:PORT --seed 42 --seconds 12            # K seeded ops a tick, as "bot"
$B/ffu-server follow --connect 127.0.0.1:PORT --seconds 10 --probe-every 16  # its own copy, resync on a mismatch
$B/ffu-server enter --connect 127.0.0.1:PORT --ticks 16                      # a new client joining mid-game
$B/ffu --connect 127.0.0.1:PORT --seconds 30                                  # the window, following the server
```

- `--listen 127.0.0.1:0` picks a free port; read it from the start line's `listen`. `--tps 0` runs as fast as it can.
- A `--dir` that already holds a snapshot is recovered from its log and `--start` is ignored: a crashed server comes
  back where its log ends (`recovered`, `replayed`, `truncated_bytes` on the start line).
- `follow`'s line is the verdict: `mismatches_unplanted` must be 0 (exit 1 otherwise), `resyncs` counts mends.
  `--probe-every N` places a belt every N ticks as a click would and adds `click_to_shown_ms` (p50, p95, max);
  `--probe-log FILE` logs every tick and probe. `--plant-fault-every N` corrupts the follower to show a resync mends
  it (a server built with `--features fault-injection`).
- `enter`'s line has the join cost: `welcome_bytes`, `wire_bytes_per_building`, `welcome_ms`, `first_tick_ms`.
- Measured on lothdesktop (w2895, ffu main 821bcea): a 2,000-building sector at 16 tps with one bot, a 10 s `follow`
  read 161 ticks with 0 resyncs and 0 mismatches, 10 probes shown at p50 63 ms; `enter` joined in a 10,307-byte
  Welcome. Those times are not bench numbers: a timing you report needs the bench ticket.

## Latency, loss and soak

```sh
$B/ffu-server proxy --connect 127.0.0.1:PORT --rtt-ms 150 --jitter-ms 15 --loss 0.01 --seed 1 --trace p.trace
./tools/proxy_leg.sh "$OUT" 150 15 0.01 600        # server, a bot direct, a follower through the proxy
python3 tools/proxy_why.py "$OUT" 10               # why the slowest probes were slow, from the leg's logs
./tools/bots_hour.sh 1000 3600 "$OUT"              # ffu-bots: N thin bots and a referee against one server
```

`ffu-bots arena --bots N --out a.snap` writes the arena `bots_hour.sh` serves; `ffu-bots run --connect ADDR --bots N`
plays the fleet (one line: mismatches, errors, CPU and memory per bot; exit 1 on a hash difference);
`ffu-bots cost --bots N` times one bot's step with no server. CPU, memory and step times are measurements only under
an exclusive bench ticket, which holds at most a 30-minute turn: run an hour's soak under a shared ticket and measure
in a shorter exclusive run (`bots_hour.sh`'s header says the same).

`./tools/soak.sh [STATIONS] [BOTS] [IDLE] [SECONDS] [OUT]` is the many-station soak (M2.15, ffu #279): one shard
server, a fleet process per station with a referee that keeps a cargo ledger (`ffu-bots run --audit --window 960`),
then `replay-station` for every station and `tools/soak_audit.py`, whose `summary.json` `"ok"` is the verdict (exit 1
on a mismatch, a ledger error, an unbalanced window or a short fleet). Measured on lothdesktop (w2895, release,
`soak.sh 120 100 20 86400`): 10,000 bots over 120 stations ran 24 h to tick 507,523 with 0 mismatches, 0 ledger errors,
527 windows balanced and an awake fraction of 0.594, at 5.9 UPS for the one server process (shared machine, no ticket).

- A run longer than your turn needs a `wake_me` pending for its whole length, renewed until it ends. `blocked_on`
  cancels the check-in, and FF Factory's clean-up then ends everything your session started about 2 minutes after
  your process stops: w2895's first 24 h soak was killed at 12 h that way. Wait on CI or another PR only after the run
  has finished.
- A soak over machines (`SOAK_SHARDS=K SOAK_HOSTS=... SOAK_LOCAL=...`, M2.15b) dies at once if one peer port is
  unreachable. Windows Firewall adds two inbound Block rules named after the exe ("ffu-server", Private+Public) the
  first time a new exe path listens and nobody answers its prompt. A Block rule beats an allow-all rule for the
  Tailscale IP, and a worker that isn't an admin can't remove it. w3346 (2026-11-07): beast's fresh
  `$TMPDIR/tgt/release/ffu-server.exe` was blocked, so biscuit could not reach 47102/47103. Every shard stalled at
  tick 13, every fleet died within 75 s, and the 1 h soak failed (no rerun, per Ben). Before you agree on
  SOAK_START_AT: on Windows, run `Get-NetFirewallRule -DisplayName ffu-server | ? Action -eq Block` (any hit means an
  admin must remove it first, or build into a CARGO_TARGET_DIR whose exe already has an allow rule). In the first
  minute after the start, each other leg runs `timeout 5 bash -c "</dev/tcp/<ip>/<port>"` against every remote peer
  port. A refused port means stop and say so; the run is lost anyway.

## A world shard: stations, peers, standbys

```sh
$B/ffu-server --dir "$OUT/world" --start world:4:1 --tps 0 --ticks 64     # a shard of 4 stations
$B/ffu-server replay-station --dir "$OUT/world" --station 0                  # one station alone, from its own log
$B/ffu --connect 127.0.0.1:PORT --station 2 --seconds 30                      # a client follows one station
$B/ffu-server replica --dir "$OUT/replica" --listen 127.0.0.1:0 --exit-on-stdin-close
```

- A shard keeps one snapshot and one op log per station (`station-<id>/`), so `replay-station` checks any station
  without the others: its `last_hash` per station is what two runs compare.
- Peered shards take `--shard-id ID --peer-listen ADDR`, one `--peer ID@ADDR/S,S,...` per other shard, `--host S,...`
  and `--replica ADDR`; `--until-tick T` ends a peered run once every peer holds this shard's batches. A standby is
  `--standby-listen ADDR [--takeover-after-ms N]`: it follows the owner and fences it once it has been gone N ms.
  `ffu-server --help` has every flag; the directory (who owns which station at which epoch) is the `ffu-directory`
  crate, tested by `cargo test -p ffu-directory`.

## When two peers disagree

A follower's mismatch or two `replay-station` hashes that differ is a desync: take the two runs to
`/ff-agents:ffu-determinism` (record, replay, bisect to the first tick, subsystem and field). Ops from a client reach
the sim only through the server's op log, as `/ff-agents:ffu-add-op` describes; nothing a client draws feeds back.
