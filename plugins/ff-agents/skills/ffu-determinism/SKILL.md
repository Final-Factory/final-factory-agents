---
name: ffu-determinism
description: Prove or debug determinism in Final Factory Universe (FFU), the Rust engine in Final-Factory/ffu - the hashcheck, the cross-machine crosscheck and crosscompare (Linux, Windows, macOS), thread-count invariance, recording and exact replay, planting a fault, and bisecting two recordings to the first differing tick, subsystem and field. Use when an FFU change could move a hash, when two runs or machines disagree, or before merging a sim change; it replaces determinism-audit there (no editors, no paired sessions).
---

# Determinism in FFU

The sim is deterministic by construction (fixed-point, ordered iteration, ops only through `Sector::submit`), and
these commands prove it. Build `ffu-headless` with `--features agent-api,fault-injection` and call the binary
(`/ff-agents:ffu-drive`, top). Each command ends with one JSON line on stdout.

## Did my change move the hash?

```sh
$B/ffu-headless hashcheck --golden golden/hashcheck.txt                # 512 ticks of factory:20000:1
$B/ffu-headless hashcheck --golden golden/hashcheck.txt --threads 16   # the same at 16 threads
$B/ffu-headless crosscheck --threads 1,4,16 --golden golden/crosscheck # every scenario, every tick
```

- `hashcheck` prints `"golden_match":true` when the 512-tick hash equals the pinned one. A change meant to move it
  updates `golden/hashcheck.txt` in the same PR and says why; otherwise a mismatch is a bug.
- `crosscheck` runs each scenario in `crosscheck::SCENARIOS`, compares its hash on every tick with
  `golden/crosscheck/<scenario>.csv` and across the thread counts, and names the first tick and hash part that differ.
  `--scenario a,b` picks some; `--inject-float` plants libm rounding from tick 100 to show the check failing.
  Re-pin with `--write-golden` only for a change meant to move the hash, and say so in the PR.
- A new scenario is an entry in `crosscheck::SCENARIOS` plus its golden trace from `--write-golden`.

## Across machines

CI runs `crosscheck --out` on Linux (biscuit), Windows (BEAST) and ARM macOS (the M3), and its `crosscompare` job
compares them tick by tick. To do it by hand, run on each machine and bring the folders together:

```sh
$B/ffu-headless crosscheck --threads 1,4,16 --golden golden/crosscheck --out "$TMPDIR/cc-<machine>"
$B/ffu-headless crosscompare linux=<dir> windows=<dir> macos=<dir> --summary cross.md
```

`crosscompare` names the first tick and hash part that differ between the first folder and each other one, and
appends a table of every run's hashes and times. Hand folders between machines with `publish_attachment`, never by
copying across machines yourself. A cross-OS check matters for a change that could differ by platform (float, libm,
thread scheduling, a platform crate).

## Record, replay, bisect

```sh
$B/ffu-headless run --start factory:2000:1 --ticks 600 --record "$TMPDIR/a"                    # ops, keyframes, hashes
$B/ffu-headless replay "$TMPDIR/a"                                                             # "equal":true
$B/ffu-headless run --start factory:2000:1 --ticks 600 --record "$TMPDIR/b" --fault 300:5     # a planted desync
$B/ffu-headless bisect "$TMPDIR/a" "$TMPDIR/b"
```

- `--record dir` writes the op log, a keyframe every `--keyframe K` ticks (default 100) and every tick's hash.
- `replay dir` re-runs the recording and checks every hash; `replay dir --fault tick:building` plants a fault in the
  replay instead. `--fault` needs the `fault-injection` feature.
- `bisect a b` finds the first tick whose hashes differ by binary search over keyframes, replays from the keyframe
  before it and names the subsystem and fields, and whether the two op logs differ. Measured (w2895, lothdesktop):
  the fault above gave `"first_tick":300,"subsystems":["belts"],"fields":["building 5 field delivered: 0 vs 1"]` in
  one replay of 100 ticks.
- Op logs and hash files stream a record at a time, so a day-long recording needs no more memory than a short one.
- A served sector: `ffu-server --dir "$TMPDIR/sec" --start factory:2000:1 --listen 127.0.0.1:0 --ticks 2000` runs it
  and reports its port; `ffu-server follow --connect ADDR --seconds 30` follows it on its own copy and exits 1 on a
  hash mismatch it did not plant. `--plant-fault-every N` (built with `--features fault-injection`) corrupts the
  follower's copy every N ticks to show a resync mends it.

## When two runs differ

1. `bisect` the two recordings: the tick, the subsystem and the field are usually enough to name the code.
2. `"ops_differ"` true means the inputs differ (an op arrived on one side only): look at who submitted it, not at the
   sim.
3. Same ops, different state: look in that subsystem for a float, an unordered map or set, an iteration order that
   is not by id, a thread-count-dependent job split, or a read of something outside the sector. `tools/check_sim_rules.sh`
   catches the banned types; `threads_never_change_the_hash` holds thread invariance.
4. Fix it with a test that fails before the fix (a planted case, a `crosscheck` scenario, or a unit test in the
   subsystem), and run `hashcheck` and `crosscheck` again.
