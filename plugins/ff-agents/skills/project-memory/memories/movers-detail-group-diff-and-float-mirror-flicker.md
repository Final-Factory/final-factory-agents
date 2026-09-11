---
name: movers-detail-group-diff-and-float-mirror-flicker
description: "Diff MoversDetail by field group (v/h/d/f/m/p/r + raw vel/hd) before theorising; the cross-platform movers flicker is float ULP noise that CombatMoverRailMirrorSystem quantizes from LinearMotion.Velocity into the compared rail."
---

# MoversDetail group diffs, and what the movers flicker actually is (2026-09-11)

Since 14cff52ad every MoversDetail record prints `sub=` plus per-group folds `v=` (velocity)
`h=` (heading) `d=` (destination) `f=` (collision+gravity forces) `m=` (deadline/ordinal/
flags/schema) `p=` (research/miner physical) `r=` (target refs) and raw `vel=x,y,z hd=x,y,z`.
Parse `key=… kind=… pos=… flags=… sub=… v=… …` per ` | ` segment and diff by key: the first
question is *which group*, not *which system*. The dump retains only the first 64 records by
key (`MaxMoverDetailRecords`); when the diverging rail is outside them (it was — keys
0x085C–0x088D of 1,870), raise the constant **temporarily** for a diagnostic build/editor and
restore 64 before committing.

**The flicker.** Windows-host / Mac-client built players (snapshot `lothsahn_desync_20260910`)
forked `movers` only, in short self-healing runs (e1 hb 42–49, 129/131/176, 153/155/200), each
run tripping a desync verdict → recovery. An editor peer against a built peer differs on
*every* heartbeat. Attribution (legs xplat4/5/6, group diffs then raw values): a different
handful of fleet rails each heartbeat differ ONLY in Velocity and Heading, by raw fp deltas of
4…8192 on magnitudes ~5e10 (float ULP noise), positions identical. Mechanism:
`CombatMoverRailMirrorSystem.cs:243-262` (`MirrorRailJob`) writes
`rail.Velocity = Quantize(LinearMotion.Velocity)` and `Heading = normalizesafe(velocity)` every
heartbeat for every non-authority (legacy float) rail, and the movers fingerprint folds both;
`LinearMotion.Velocity` comes from float unit-motion code whose codegen differs editor vs
player and x64 vs arm64. Same family as 055 R25 (player-root velocity excluded from the
mirror). Whether mirrored rails should fold Velocity/Heading at all is Ben's fingerprint-scope
call (069 handoff); frame-rate mismatch was ruled out (clone capped to 12 fps: no divergence).

**Cross-platform leg recipe that works:** BEAST hosts an adapter-driven built player
(`run_saved_cross_platform_peer.py` under Git-bash + Python 3.13, `--role Host --host
100.86.157.116 --port 7827`), and the M5 *editor* can be the client with a plain
`.ff-local-automation.json` (Role Client, that host/port) — no Mac rebuild needed to test an
editor-side change against Windows.
