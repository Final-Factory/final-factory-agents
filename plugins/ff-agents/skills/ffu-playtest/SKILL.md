---
name: ffu-playtest
description: Run a goal-directed agent playtest of Final Factory Universe (FFU), the Rust engine in Final-Factory/ffu - pick a goal and a stop condition, play it as ops through the agent state API or the `ffu-mcp` tools (place, remove, set_recipe, insert), observe with query, get, watch and stats, look with captures and clips, judge the outcome, and file a bug as a start snapshot plus the request script that reproduces it to the same hash. Use when asked to playtest FFU, pursue a goal in an FFU sector, verify a feature by playing it, or hunt FFU gameplay bugs; it replaces playtest there.
---

# Playtesting FFU

A playtest is a goal, a stop condition, and evidence. The engine is deterministic and the agent API is the only way
in, so every playtest is also its own repro: the same requests from the same snapshot reach the same hash. The
commands are `/ff-agents:ffu-drive`'s; this skill is how to use them for a playtest.

## 1. Set it up

```sh
cargo build --release -p ffu-headless --features agent-api
cargo build --release -p ffu-client --features agent-api        # for captures
OUT="$TMPDIR/pt-$(date +%H%M%S)"; mkdir -p "$OUT"
```

- Write the goal and its stop condition down first, in the sim's terms: "the crafter at (10, 0) makes 5
  medium_density_structure within 2,000 ticks", "no building stays stalled for want of input after 600 ticks".
- Start from a scenario (`factory:N[:seed]`, `combat:N[:seed[:turrets]]`) or a snapshot. Save the start as the first
  request (`save {path}`) so the run can be replayed: a snapshot taken after a few warm-up `step`s keeps the repro
  short.
- Call `discover` and `schema` once: `schema` lists the building kinds (belt, miner, crafter, sink, link, hold, solar),
  the directions (east is x+1, north is y+1), every item and recipe, each kind's fields, and the Cargo Hold's rules
  (one item, up to `hold_cap`; it pushes onto its belt only while a Solar Panel faces it).

## 2. Play it

Send one JSON-RPC request per line to `ffu-headless serve --start ...` (or call the `ffu_*` tools of `ffu-mcp`, which
survives an engine crash). Keep every request you send, in order, in `$OUT/script.jsonl`: that file is the repro.

```sh
$B/ffu-headless serve --start "$OUT/start.snap" < "$OUT/script.jsonl" > "$OUT/answers.jsonl"
```

- Act with `set`: `{"op":"place","x":..,"y":..,"kind":"crafter","dir":"east","param":"<recipe>"}`, `remove`,
  `set_recipe` (`param`), `insert` (`item`, `count` into a hold, all or nothing). `set` answers `would_apply`; the op
  lands on the next `step`. A refused op is a finding when the game should have allowed it.
- Observe with `query` (`kind`, `stalled`, `rect`, `limit`; `stall_reasons` counts why things wait), `get` on one
  building (its `stalled` text and the tile it faces), `watch` on the buildings the goal is about (each `step` answers
  their changes as `events`), and `stats` (tick, buildings, ops applied and rejected, hash).
- Advance with `step {n}` in chunks sized to the goal (16 ticks is one second); poll the stop condition between
  chunks rather than stepping blind to the end.
- Look only when motion or layout matters: `capture {path, width, height, view}` from `ffu --headless serve`, or
  `ffu --start "$OUT/start.snap" --warm T --clip c.mp4 --seconds 10` and judge the clip by `/ff-agents:watch-video`'s
  viewing rules. A panel's state is `ui_tree`'s JSON (`/ff-agents:ffu-ui`).

## 3. Judge and report

- Pass or fail against the stop condition you wrote, with the numbers from the answers: the tick, the counts, the
  stall reasons. Label each claim measured (you saw it in an answer), sourced or a guess.
- A bug report is the three files and one line: `start.snap`, `script.jsonl`, `answers.jsonl`, and "expected X at tick
  T, got Y (answer id N)". Prove it reproduces before filing: run the script from the snapshot twice and compare the
  last `stats` hash. Measured on lothdesktop (w2895, ffu main 821bcea): a remove, a watch and 64 ticks from a saved
  tick-201 snapshot gave `bb3cda20ed019602` at tick 265 on both runs.
- A bug that needs a server and clients is `/ff-agents:ffu-multiplayer`'s; a hash that differs between two runs of
  the same script is a determinism bug for `/ff-agents:ffu-determinism`, not a gameplay one.
- Hand a person the bug's still or clip through the portal's review tools, with the report; the files stay in
  `$OUT`.
