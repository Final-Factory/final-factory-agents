---
name: ffu-drive
description: Run and look at Final Factory Universe (FFU), the Rust engine in Final-Factory/ffu - bounded headless runs, the `ffu` window, offscreen stills, clips and frame stats, the agent state API (`ffu-headless serve`, JSON-RPC - query, get, set as ops, step, watch, capture), the `ffu-mcp` sidecar that survives the engine's crash, and the hot-reload edit-to-running loop. Use when asked to run, inspect, screenshot or drive FFU, or to answer "why is this stalled" in an FFU sector; it replaces drive-game there (a goal-directed playtest is ffu-playtest, a server and clients ffu-multiplayer, a panel ffu-ui).
---

# Driving FFU

Every command here is an ffu binary or a cargo build in an ffu checkout (`/ff-agents:ffu-build-test` sets up the
toolchain and `$CARGO_TARGET_DIR`). Build the tools once, then call the binaries directly; `cargo run` rebuilds on
every call:

```sh
cargo build --release -p ffu-headless --features agent-api,fault-injection
cargo build --release -p ffu-mcp
cargo build --release -p ffu-client --features agent-api      # the `ffu` binary, with the agent API for captures
B="$CARGO_TARGET_DIR/release"                                 # or target/release
```

A sector starts from `--start factory:N[:seed]` (a generated factory of about N buildings), `combat:N[:seed[:turrets]]`
(Stingers flying at Gatling Turrets) or a `file.snap` a run saved. Every `ffu-headless` command ends with one JSON line
on stdout: read that line, not stderr, unless it fails.

`combat:N`'s Stingers stay round their camps (spawners 4 tiles in from each edge and corner); they do not fly to the
centre, whatever `scenario.rs`'s doc says. A turret at the centre never fires; one 8 tiles from a spawner fights
(measured, w2895 FP.22: combat:8 seed 3, a turret at (64,12) from tick 136 had 51 kills by tick 2403).

## Headless: run, inspect, measure

```sh
$B/ffu-headless run --start factory:20000:1 --ticks 256 --timings t.csv      # mean/worst tick ms, final_hash
$B/ffu-headless run --start factory:2000:1 --ticks 600 --save end.snap       # a snapshot to start from later
$B/ffu-headless inspect --start factory:2000:1 --ticks 200 --stalled 3       # stalled buildings and why
$B/ffu-headless inspect --start end.snap --at 64,2                            # one building
$B/ffu-headless phases --start combat:400:1 --ticks 600                      # µs per tick phase
```

`--threads N` runs the parallel phases on N threads (no thread count changes a hash). `--rate-mode [--doze-at T0]
[--redoze R]` and `--churn N` exercise rate mode. A timing you report needs the bench ticket
(`/ff-agents:ffu-build-test`, "Timing claims").

## The agent state API (JSON-RPC 2.0, one request per line)

`$B/ffu-headless serve --start factory:2000:1` reads requests on stdin and answers on stdout; `--port N` serves
127.0.0.1:N instead. Pipe a scripted session through it, one line each:

```sh
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"stats"}' \
  '{"jsonrpc":"2.0","id":2,"method":"query","params":{"stalled":true,"limit":5}}' \
  '{"jsonrpc":"2.0","id":3,"method":"get","params":{"x":64,"y":2}}' \
  '{"jsonrpc":"2.0","id":4,"method":"set","params":{"op":"remove","x":64,"y":2}}' \
  '{"jsonrpc":"2.0","id":5,"method":"step","params":{"n":16}}' \
  | $B/ffu-headless serve --start factory:2000:1
```

- Methods: `discover` (each method's params as JSON Schema; call it first), `schema`, `stats`, `get {x,y}`,
  `query {kind?, stalled?, rect?, limit?}`, `set {op: place|remove|set_recipe|insert, x, y, kind?, dir?, param?,
  item?, count?}`,
  `watch {x,y}`, `unwatch {id}`, `step {n?}`, `save {path}`, `capture {path, width?, height?, view?}`, `ui_tree`.
- "Why is this stalled": `query {"stalled": true}` gives `stall_reasons` counts and each building's `stalled` text;
  `get` on one gives its `stalled` and the tile it `faces`, with the building there.
- `set` never writes the sector: it submits an op for the next tick through `Sector::submit` and answers the op and
  `would_apply`. `step` runs the tick that applies it; `get` then shows the result (measured, w2895: a `remove` at
  (64, 2), then `step`, then `get` answers "no building at (64, 2)").
- `capture` needs a renderer: serve from the client, `$B/ffu --headless serve --start ...`. Plain `ffu-headless serve`
  answers -32002. `ui_tree {index | x,y, width?, height?}` answers a building's inspector as a tree of nodes with
  bounds and focus (`/ff-agents:ffu-ui`). `insert` puts `count` of `item` into a Cargo Hold, all or nothing.

## The MCP sidecar

`$B/ffu-mcp --start factory:2000:1 --state-dir "$TMPDIR/ffu-state"` is an MCP server on stdio. Each method is a tool
`ffu_<method>` (`ffu_query`, `ffu_get`, `ffu_set`, `ffu_step`, ...), plus `ffu_engine`: the engine's pid, restarts,
snapshot tick and last crash. The engine is a child saved to `<state-dir>/last.snap` after every `set` and `step`; if
it dies mid-call, that call answers `isError: true` with the exit status and the engine comes back from the snapshot
(later ticks and all watches lost, submitted ops kept). `--engine $B/ffu` makes `ffu_capture` draw (measured, w2895: a
640x360 PNG on lothdesktop's Arc B580). To give a Claude Code session these tools:
`{"mcpServers":{"ffu":{"command":"<path>/ffu-mcp","args":["--start","factory:2000:1"]}}}` with `--mcp-config`.

## Looking at it: window, stills, clips, frame stats

```sh
$B/ffu --start factory:20000:1 --seconds 30                                    # a window; ends by itself
$B/ffu --start factory:20000:1 --warm 480 --still out.png [--view x,y,zoom]   # offscreen PNG, no window
$B/ffu --start factory:20000:1 --warm 480 --clip out.mp4 --seconds 10         # needs ffmpeg
$B/ffu --start factory:250000:1 --frames 600 --stats frames.json              # frame times
```

`--warm 480` first runs 480 ticks so smelters have output. In the window: WASD or arrows pan, wheel or +/- zoom, drag,
space pauses, `[` and `]` slow and speed the clock, F12 saves `ffu-shot-N.png` in the working folder, 1 to 5 pick
belt, miner, crafter, sink and remove (Tab the next), R rotates, a left click places and a right click removes.
`--pack DIR` draws each kind that has a baked model in DIR's `*.ffpack` (`ffu-bake` writes them). Always give a window `--seconds N` so nothing you start outlives your work.
A still of a live window on Windows (a `--connect` client, a launcher check): run `window_shot.ps1 -Out shot.png`
(beside this file) while the window runs. Never use a desktop grab: on BEAST other sandboxes' editors sit on top, and in
w3321 the grab showed slot2's Unity and none of the client. The script uses PrintWindow on the window itself, which drew
the client while it was covered (measured).
Each call takes about 5 s and returns a half-size grab (640x360 for a 1280x720 window, measured w3754), so a
dozen stills need about a minute of window. Copy `ffu.exe` to a name of your own (`ffu-wNNN.exe`) and pass
`-ProcessName ffu-wNNN`, so the grab never picks another sandbox's `ffu` window. Stills of `ffu --world --window` need
a zoomed-out view (`--view x,y,8`): a world:N:2:3 station keeps its buildings in a strip at one corner, so the default
zoom 24 at a station's centre shows empty floor (w3754: three blank stills). `--autopilot --fly-speed 10` flies
world:16's 534-tile tour in about 53 s.
`ffu --headless <cmd>` is `ffu-headless <cmd>`. Judge motion from a clip, not a still (`/ff-agents:watch-video`'s
viewing rules hold; its recorder is for Unity players).
A connected clip (`--connect ... --clip`) draws the builder's notice, as the window does: a refusal, or FP.20's
"2 tiles taken" (ffu #654, w2895). Before that PR a clip drew panels but no notice, so no still could show one.
`--autodrag N` drags an N-tile belt line east from the free tile nearest the view's centre, then releases it.

## Art previews

New or recreated art (a model, texture, material or effect under `art/`) follows the evidence-gate visual checklist,
items 5c (the art language: two solid main colours plus one bright, bloomy HDR accent) and 5o (w2895). Before a fresh
critic grades it or Ben sees it: a capture of the FF1 original as the built FF1 game draws it (its lighting, bloom,
camera, placement; if the built game never shows it, it is not rebuilt), and an `ffu` still of ours at the same zoom
beside it. Give the critic both, Ben's art-language words and 5o's four questions; never only the texture or model
file or the source pack. A flaw that comes back round after round goes to Ben as 2 or 3 different takes, not one more
near-match. The PR's `## Evidence` carries `Reference capture:` and `Art language:`, and
`python3 <evidence-gate>/pr_evidence.py --repo Final-Factory/ffu --pr <n>` passes before you ask Ben or merge.

## The edit-to-running loop (hot reload)

```sh
cargo run --release -p ffu-client --features hot-reload -- --start factory:20000:1
# edit crates/ffu-sim, then in another shell:
cargo build --release -p ffu-client --features hot-reload
```

When the rebuilt `ffu` has sat unchanged for 0.5 s, the window saves its sector and restarts as the new build from
it, with the same camera and no warm-up. On Windows the window runs from a copy in `target/<profile>/hot-reload/`,
since cargo cannot replace a running `ffu.exe`. An edit that changes the snapshot layout follows the snapshot rule
(version bump, old decoder kept). `tools/measure_edit_loop.sh [ROUNDS] [OUT_DIR]` times the loop under a bench ticket
and writes `rounds.csv`; it needs a display.

## When it crashes

Every ffu binary writes a crash report on a panic, and a monitor process writes a minidump on a native fault, to
`FFU_CRASH_DIR` when set, else the platform's folder (`%LOCALAPPDATA%\FinalFactoryUniverse\crashes` on Windows,
`~/Library/Logs/FinalFactoryUniverse/crashes` on macOS, `$XDG_STATE_HOME/ffu/crashes` on Linux), named
`crash-<app>-<ms>-<pid>.txt` or `.dmp`. Set `FFU_CRASH_DIR="$OUT/crashes"` for a run you start, so its reports stay
in your folder.

```sh
cargo build --release -p ffu-crash --features symbolicate --bin ffu-minidump
$B/ffu-minidump "$OUT/crashes/crash-ffu-<ms>-<pid>.dmp" $B/ffu        # the crashing stack with file:line
./tools/check_crash_report.sh $B/ffu-headless "$OUT/crash-check" $B/ffu-minidump   # plants a panic, segv and abort
```

The symbols come from the binary's own debug info (the release profile keeps it), so symbolicate with the exact
binary that crashed.
