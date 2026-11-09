---
name: ffu-add-op
description: Add a new gameplay mutation to Final Factory Universe (FFU), the Rust engine in Final-Factory/ffu, as an `Op` through `Sector::submit` - the enum variant, its op-log encoding and body length, applying it in phase one, refusals, the hash and snapshot rules, rate mode's wake list, the agent API's `set`, and the tests that prove it. Use for any FFU change that lets a player, a bot, the server or the world change a sector; it replaces add-network-operation there.
---

# Adding an op to FFU

Every change to a sector is an `Op` through `Sector::submit`, applied in phase one of the next tick in
(tick, sender, seq) order (ffu `CLAUDE.md`, "The sim's rules"). The engine, the agent API and bots read the sim and
never write it. An op is also the unit the server logs before its tick and replays after a crash, so an op that is
not deterministic or not fully encoded breaks recovery as well as peers.

## Where an op lives (crates/ffu-sim/src)

| Step | File | What |
|---|---|---|
| 1 | `ops.rs`, `pub enum Op` | The variant, with a doc comment: what it does and who may send it (players, or only the world's exchange as `EXCHANGE_SENDER`). Fields are small integers (`u16` tiles, ids); no floats. |
| 2 | `ops.rs`, `StampedOp::encode` / `decode` | A new tag number after the last one, and its fields in a fixed order. Never reuse or renumber a merged tag: op logs on disk hold them. Two open PRs can take the same next tag (w3797: ffu #551 and #557 both took 25 and 26): before you push, look at the tags open PRs claim (`tools/row_numbers.py next op --prs`), and when another PR takes yours first, renumber your unmerged one, including a test that probes the first unused tag (`op_body_len(N).is_err()`). |
| 3 | `ops.rs`, `op_body_len` | The body length for the new tag, or streamed op logs (`ffu_headless::stream`) cannot skip it. |
| 4 | `ops.rs` tests | Add it to the round-trip list of every variant. |
| 5 | `sector.rs`, `fn apply` | Apply it. Return a `SimError` to refuse (a missing building, a wrong kind, an out-of-range value): a refused op moves `ops_rejected`, not the state. Use `get`, `checked_*` or `saturating_*`; no `unwrap`, indexing or unchecked arithmetic in the tick. |
| 6 | `sector/rate.rs` | If it can touch a building, add it to the ops that wake that building's island before it applies, or a dozing island misses it. |
| 7 | `sector.rs`, `building_hash` | A new field it writes goes into the hash (`every_field_and_the_index_change_a_building_hash` lists them). |
| 8 | `snapshot.rs` | A new saved field bumps `SNAPSHOT_VERSION`, keeps the old decoder as the upgrade path and adds a fixture in `crates/ffu-sim/tests/fixtures`; never rewrite an old fixture. |

If players may send it, give it to the agent API too: `crates/ffu-agent/src/lib.rs`, the `set` method's `op` names
and its `discover` schema; run the fuzz target `agent_line` (`tools/fuzz.sh 60 agent_line`) on the new request shape. If the server sends it as world
content (as `Op::Turret` and `Op::Spawner`), say so in the doc comment and refuse it from other senders.

## Prove it

- A unit test in the subsystem: the op applies at the next tick, not before (`submit` with a tick that has passed is
  `TooLate`); a refusal leaves the state and hash unchanged; two ops at one tick apply in (sender, seq) order.
- Record and replay a run that uses it: `ffu-headless run --start ... --ticks N --record dir --ops ops.log`, then
  `ffu-headless replay dir` ends `"equal":true` (`/ff-agents:ffu-determinism`).
- Through the agent API when players send it: `ffu-headless serve`, a `set` with the new op, `step`, `get`
  (`/ff-agents:ffu-drive`).
- `hashcheck` keeps `"golden_match":true` unless the op is in the hashcheck scenario on purpose. If you add a
  `crosscheck` scenario for it, pin its trace with `--write-golden` and say so.
- The full check list (fmt, sim rules, clippy, tests, hashcheck, crosscheck) and the snapshot compatibility check:
  `/ff-agents:ffu-build-test`.

## Do not

- Write a sector from the client, the renderer, the agent API or a bot: they submit ops.
- Read a clock, a file, the environment or a thread id in `apply`; iterate an unordered collection; use a float.
- Change an existing tag's encoding. A new layout is a new tag, or an op-log version bump (`OPLOG_VERSION`) with the
  old decoder kept.
