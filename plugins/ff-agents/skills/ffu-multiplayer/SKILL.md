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
- **macOS has no `timeout` command** (no coreutils): a brief's `timeout -s TERM 1200 ... soak.sh` on a Mac leg dies
  at once with exit 127 and nothing listens, so the other leg's soak.sh exits 3 at 90 s ("peer links did not come up",
  "Connection refused"). w3923 (m3, 2026-11-10) lost its first start that way. On a Mac, check `command -v timeout`
  before you send SOAK_START_AT, and run soak.sh from a script that backgrounds it and sends it TERM from a
  `( sleep 1200; ... -TERM $pid ) &` watchdog subshell. Read the run's output a few seconds after launch: a launch that
  exited at once is a failed start, not a run, so starting it again is no rerun.

- **A run against the shared world (biscuit, 100.98.100.42:7777) checks what the world runs before anything else**
  (w3397, 2026-11-07): the brief named ffu main 66db990, but the world was redeployed from 75745c0 while the legs
  queued for tickets, and every 66db990 client died at once with `snapshot decode: unsupported version 10`. Before you
  take a bench ticket, read the latest `world` run (`gh run list -R Final-Factory/ffu --workflow world --limit 3
  --json headSha,createdAt,conclusion`), build that commit (`git merge-base --is-ancestor <brief commit> <it>` says the
  feature is in it), and probe a join: `$B/ffu-server chat --connect 100.98.100.42:7777 --name probe --seconds 3` ends
  with `"error":null`. Say the commit you ran, and why, in the report.
  Read it again right before each leg starts its processes, not only before the tickets: in w3444 the world was
  redeployed again (a2bc925 to d25cb01, 21:04Z) while both legs queued, and the echoer died on start with
  `snapshot decode: unsupported version 11`. A rebuild at the new commit took 16 s, so rebuild, re-probe and go.
  - **Confirm the world's snapshot version matches your commit before the pair run**, with the binary you built:
    `$B/ffu-server enter --connect 100.98.100.42:7777 --ticks 16`. It decodes the world's Welcome and follows 16 ticks,
    so a JSON line with `welcome_bytes` means your build reads what the world sends. `snapshot decode: unsupported
    version N` means the world writes snapshot version N and your commit reads less (compare
    `grep -n 'SNAPSHOT_VERSION: u32' crates/ffu-sim/src/snapshot.rs`): build the world's commit instead. In w3469
    (2026-11-08, FP.6 on lothdesktop, ffu main eaf82b73) the world wrote v16 and the client read up to v11, and every
    Welcome was refused.
- **A window or clip you start in the background (`nohup ffu ... &`) can outlive its `--seconds`**: before ffu #469
  (w3646), a `--connect ... --clip` run that never joined kept redialling for good. In w3469 it passed try 141 (about
  5 min) past `--seconds 75`, wrote no clip and no JSON line, and `ff-leftovers list` did not show it, because `nohup
  ... &` detached it from the session. Since #469 such a run ends at `--join-seconds`, else `--seconds` (a clip's
  default: 10 s), prints `{"joined":false,"error":"snapshot decode: unsupported version N",...}` and exits 1; an older
  build does not. Either way, record the PID when you start it (`$!`). When it has not ended by its time, end it by
  that PID (`taskkill //PID <pid> //T //F` on Windows, `kill <pid>` elsewhere), then check that it is gone (`tasklist
  //FI "PID eq <pid>"`, or `tasklist | grep -i ffu`), since ff-leftovers can miss it.
- **Agree a pair start time as UTC and parse it as UTC** (`date -u -d '20:39:50' +%s`): plain `date -d` reads the
  time in the machine's zone (biscuit is -07:00), and w3444's scheduled echoer would have waited seven hours. An echo
  that must outlast the other leg's queue starts with a long `--seconds` (1500) on the other leg's go; `ffu-server
  chat` ignored SIGINT in w3444 and writes its JSON line only when `--seconds` runs out, so let it end.
- **A timed pair run lines its tickets up by queueing both at once**, not one after the other's grant: in w3397 each
  leg's grant lapsed unused while the other still queued (a big computer's queue and biscuit's CI drain took 10 to
  50 min). A leg that times nothing itself (an echoer, when every number comes from the sender's clock) may run without
  a ticket when both legs agree, with that caveat in the report.
- **Check the world commit and probe a join again right before the timed run**, not only at setup. In w3444
  (2026-11-07, a beast+biscuit pair timing chat latency for w3383) the world was redeployed at 21:04Z while the legs
  queued for tickets (the deployed commit moved a2bc925 to d25cb01), and clients built at the old commit failed to join
  with `snapshot decode: unsupported version 11`. Re-read `gh run list -R Final-Factory/ffu --workflow world.yml
  --status success -L 1 --json headSha`, rebuild if it moved (ffu-server release took 19 s on BEAST, measured) and rerun
  the 3 s probe.
- **Don't agree a fixed wall-clock start before both exclusive tickets are in force.** On a big computer the turn can
  run out while its CI jobs drain: in w3444 beast's first ticket (granted 20:17Z) spent its whole 20-minute turn in
  `granted, but N CI job(s) run here` and was revoked at 20:37Z, 3 min before the agreed start. What worked: the leg
  whose ticket comes later messages "GO" at its grant; the other leg starts its long-lived side at once (an echoer with
  `--seconds 1500`, not 150), and the first leg starts its ~100 s timed part the moment its own drain ends (the log line
  `granted <ticket>: time now; it is held until ...`). The second ticket (granted 21:22Z, drained 21:30Z) ran the
  measurement in that window.
- **A run "at N bots" is only at N bots if the server kept them: read `clients_whole_window` and count the drops.** A
  remote fleet (`bots_ff1.sh` with `FFU_CONNECT`, M2.14e) over Tailscale loses most bots in the join burst. w4054
  (2026-11-13, server on beast, fleet on lothdesktop, ffu 2eb76789): at N = 1500, 2400 and 4000 the server closed
  1431, 2362 and 3999 clients with `a write timed out` within ~10 s of the joins (the 4000 run's join window sent
  2.8 GB of Welcomes), and the steady windows held 70, 44 and 37 clients. The fleet still said 0 mismatches, with its
  errors as `os error 10060` read timeouts. Before you report numbers at N bots, check `stats.json`'s
  `clients_whole_window` and `grep -c "write timed out" server.log`, and say what load the windows actually carried.
  After the fleet fix (ffu #741, `--joins 32`, w4061 at ab047204) the same pair held 1434 of 1500 in every steady
  window (42 write timeouts), but at 2400 and 4000 the windows topped out at 1,725 and 1,713 whole-window clients
  (1,762 and 1,776 at the end): the fleet's joins were still running at 300 s (`joined_by_ms` 302441 and 303981,
  Welcome max 61 s), and the server closed 391 and 267 with write timeouts. No tick went over 100 ms at any N, so
  the limit there was the join path over the link, not the server's tick.
- **Measure the link and the fleet machine before you blame either.** beast <-> lothdesktop is Tailscale direct over
  the internet, not a LAN (idle RTT 25-30 ms, 140-490 ms under a run). w4087 (2026-11-13, ffu b06aaf06, PR #763):
  with plain frames (`-- --plain`) at 2400 and 4000 bots lothdesktop's Tailscale adapter received a flat 340-354
  Mbit/s, so that route tops out near 350 Mbit/s and plain frames fill it; with squeezed frames the same runs moved
  only ~80-100 Mbit/s yet still dropped bots, while the fleet burned 8-9 cores (`cpu_s` 2472 and 2661 over 300 s) on
  a machine other sandboxes share. Sample the fleet machine through the run, 10 s apart: PowerShell
  `Get-NetAdapterStatistics -Name Tailscale` (bytes received) and `Get-Counter '\Processor(_Total)\% Processor Time'`.
  The fleet's `cpu_s` read exactly 195.62 in two different `--plain` runs: don't trust it there.
  "No other live agent" on lothdesktop does not mean idle: it also hosts ffu's own CI runners
  (`V:/ffw/ffu-runners/ffu-lothdesktop-N`). In w4090 (2026-11-13, ffu 406e5c53, 4000 squeezed bots, fleet pinned to
  0xFF00) a runner job started mid-run: rustc at 2-4 cores from 22:13Z, then its `ff1_import` test at 14 cores and the
  machine at 100% for the fleet's last seconds. Check `Get-Process | ? Path -like '*ffu-runners*'` before you arm, and
  log every other process over one core in the samples. That run also showed where 4000 bots break: the fleet used a
  median 1.5 cores, yet Tailscale rx sat at 350-377 Mbit/s with squeezed frames, 940 bots dropped and the server
  closed 1922 on write timeouts. On this route the link, not the fleet CPU, is the limit at 4000.
- **Size a ping loop alongside the run by time, not count.** On Windows `ping -n 1 -w 2000` plus `sleep 1` gives one
  sample per ~1.7 s (70 samples spanned 117 s, measured in w3444).
- `publish_review` accepts only images, video, `.md`/`.txt`/`.json` and `.zip`: copy a `.jsonl` log or a script to
  `<name>.txt` before you publish it.
- **A latency check against a millisecond limit keeps lothdesktop out** (`request_pair` `avoid: ["lothdesktop"]`) and
  logs a timestamped ping beside the run. lothdesktop's link to the world (biscuit, 100.98.100.42) swung 30-1151 ms
  with loss (w3432, w3383, 2026-11-07): FP.8's chat failed 250 ms twice there (max 794 ms), then passed on beast and
  biscuit at max 148 ms with the ping at 4-138 ms (w3444, measured). Without the ping beside it, a slow line cannot be
  told from a slow link.
- **A frame that is not tick state (chat) is handed on as it is read, never held to the next tick**: the server and
  follower read frames between ticks, so a held one waits up to 62.5 ms a hop at 16 tps. ffu #392 (`Client::chat_to`)
  sends each chat frame to a channel on read; `chat.rs`'s
  `a_line_is_handed_on_as_it_is_read_without_waiting_for_the_next_tick` holds it (w3383).
- **The second world, the FF1 factory (`ffu-world-ff1`, 100.98.100.42:7778; FP.12, w3679)** is deployed by the same
  `world.yml` run after the first world (`-f world=ff1`). Its start is the `TrailerStaging-0.50.0.54` golden fixture
  imported by `deploy.sh`. Lessons:
  - **A main change that alters what an old snapshot decodes to, without a `SNAPSHOT_VERSION` bump, blocks every
    deploy of a kept world**: `the new build cannot load a copy of the kept world. Deploy refused`. ffu #485 (the 2x1
    power footprint) did that: restoring the ff1 world hit `power_unplaced` and returned `BadParam`. To find the cause,
    build main's merge commits between the world's running build and main, and run `ffu-server --dir <a copy of the
    kept dir>` on each one; the first build that refuses is the culprit. The ff1 world can start afresh with
    `gh workflow run world.yml -f action=reimport -f world=ff1`. Hand up a compat fix for the culprit.
  - **A reimport stops the server before it moves `sector/` aside.** The running server writes
    `snap-<tick>.bin` by path every 256 ticks and recreates `sector/`, and the check then loads the old snapshots.
    That happened in world run 42557618673. ffu #537 stops the unit first and puts the old world back if the reimport
    is refused.
  - **A world run on a push to main that is red on the ff1 step still deployed the first world.** Read its
    `deploy: before ... after` line before calling the first world broken.
  - **A loot test runs on a local `ffu-server` holding a fresh FF1 import, not on :7778** (w3968, FP.17). No op lets
    a client plant a wreck (wrecks are world-only), and the import's wrecks expire, so the shared world may have none
    left. Two clients with `--autoloot` on 127.0.0.1 looted two wrecks, and the other client agreed (ffu #656).
  - **The release client's `--connect --clip` end line carries `"buildings"` and `"buildings_joined"`** (since ffu
    e521738). Check a clip's count against the import's `placedCount` from that line. Measured at main 99427e7: both
    read 3776, with 0 resyncs.

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
- **Peers on a Windows machine: check the firewall *after* the server first listens.** When `ffu-server.exe` at a new
  path (`$TMPDIR/tgt/release`) first listens on `0.0.0.0`, Windows shows a firewall prompt that nobody answers. It then
  adds inbound **Block** rules named `ffu-server` for that exe path (Private and Public profiles). A Block rule beats
  allow-all rules such as `Tailscale-In`. The other machine's links then hang in SYN-SENT and time out, while loopback
  and the Windows side's own outbound links work. w3346 (beast, 2026-11-07): the M2.15b soak stalled at tick 13, and
  the firewall check had been done before the exe ever ran, so it showed nothing. Before a cross-machine run with a
  Windows leg, do a short dry listen first. Start `ffu-server` on the peer port, check
  `netsh advfirewall firewall show rule name=all dir=in verbose | grep -i -B12 ffu-server` for `Action: Block`, and
  test from the peer with `bash </dev/tcp/IP/PORT`. A non-admin worker cannot delete the rule: hand its removal, or an
  allow rule for the path, to ops before the timed run.
  w3347 (LothLaptop, 2026-11-08) hit it again: the brief ordered the netsh check before the build, it showed
  nothing, and the first launch added the Block rules; the pre-flight ended at tick 2 with no peer link. A plain
  PowerShell `TcpListener` on `0.0.0.0:47102` (not ffu-server) got no connection from biscuit either (5 s timeout),
  though `Tailscale-In` allows Domain,Private and the Tailscale profile is Private; outbound to biscuit:47100 worked.
  So do the dry listen and the remote connect test before the pair is placed and the bench tickets are taken, and
  when writing a pair brief with a Windows leg, put the firewall check after a first listen, never before the build.
- **A shard's snapshot is copied a share of stations a tick and encoded off the tick** (w4130, ffu #787, M2.16b).
  Copying all 174 stations of the overload world (1,044,000 buildings) on one tick cost 22-32 ms and encoding them
  72-89 ms (MEASURED, `crates/ffu-server/tests/snap_timing.rs`, ticket t00007163), so `shard.rs` `Capture` copies a
  share in the 32 ticks before the due tick, keeps each copy's records, and the log thread replays, checks and encodes
  them: the `snap` max fell from 507.6 to 2.343 ms (t00007166). Two traps: a record for tick t is built while
  `world.tick()` is t-1, so a station copied at world tick c has `sector.tick() == c` and replays from record c+1 (an
  off-by-one there fails as "a snapshot copy at tick 8 has a record for tick 9"). And `tools/overload.sh` snapshots
  only every 4096 ticks, twice in a 720 s run: judge a snapshot change from `SOAK_TRACE=1`'s per-tick `trace-0.jsonl`
  (fields `snapshot`, `snap_us`, `tick_us`, `send_us`) against each 60 s window's p99, not from the phase summary.

## When two peers disagree

A follower's mismatch or two `replay-station` hashes that differ is a desync: take the two runs to
`/ff-agents:ffu-determinism` (record, replay, bisect to the first tick, subsystem and field). Ops from a client reach
the sim only through the server's op log, as `/ff-agents:ffu-add-op` describes; nothing a client draws feeds back.
