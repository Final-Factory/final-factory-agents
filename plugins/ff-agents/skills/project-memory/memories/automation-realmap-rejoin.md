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
in census at epoch 3 heartbeat 1379. The command is wrong for the fixture; its causal link to the census fork is not yet proven.
Repeat with the correct mode and exact first-divergent CensusDetail before classifying or fixing a game defect.
