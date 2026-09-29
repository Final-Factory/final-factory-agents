---
name: automation-realmap-rejoin
description: "A real-terrain rejoin must use the fifth realmap segment; net.rejoin already performs its own leave, and its HTTP chain result is not the rejoin's terminal state."
---

# Real-terrain automation rejoin (074 T115)

`LocalMultiplayerAutomationCommandRunner.ExecuteNetRejoin` accepts the command only from a
connected client (`LocalMultiplayerAutomationCommandRunner.cs:2607-2613`). It defaults
`forceFlatMap` to true; `realmap` disables that flag when supplied as the optional fifth segment
after an explicit settle time (`:2615-2638`). For a real-terrain replay, send exactly:

`ffauto:net.rejoin|<HOST>|<PORT>|45|realmap`

Do not send `net.leave` first: `RejoinAsync` announces the rejoin and shuts the client down itself
before returning to the menu and joining (`:2642-2669`). When `forceFlatMap` remains true,
`RejoinAsync` calls `ForceRejoinedWorldMapGenOff` both after joining and after player readiness
(`:2675-2689`).

The rejoin is fire-and-forget (`ExecuteNetRejoin` calls `RejoinAsync(...).Forget()` at `:2638`), so
an HTTP chain can report cancellation while the rejoin keeps running. Check the restored session
before drawing a verdict. The t12 replay built from `e0cfce3` omitted `realmap`; M3 first diverged
in census at epoch 3 heartbeat 1379. **Proven 2026-09-29 (3-peer soak, sandbox mp-r2):** without `realmap` the rejoined peer runs with
`MapGenState.Off`, so `CometSpawnerSystem` returns early there (`CometSpawnerSystem.cs:55`) while the
host keeps rolling ambient comets. Every roll after the rejoin forks `census` alone, host +N of sig
`[LinearMotion,Comet]` (one or two per roll), and it recurs after every desync recovery because the
peer stays Off. A harness artifact, not a game desync: rerun with `realmap` before reading anything
into a comet-only census fork.
