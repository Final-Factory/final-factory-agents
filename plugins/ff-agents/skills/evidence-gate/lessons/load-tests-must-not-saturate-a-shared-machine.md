---
name: load-tests-must-not-saturate-a-shared-machine
description: "A test that needs CPU load (busy loops, a stress or failover test) must not saturate a machine that hosts CI runners or other agents: cap the hogs at cores/2, run them at Idle priority (`start /low` on Windows, `os.setpriority(..., 19)` or `nice -n 19` on Mac/Linux), bound their time, and prefer a machine without runners (timed_place). w6066 planted 16 to 96 Normal-priority busy loops on a 16-thread LothDesktop and made the ffu CI jobs beside it 10 to 25 times slower (w6164)."
date: 2026-11-26
---

# A load test must not starve the machine's CI runners

**Rule.** If a test needs load, it must not saturate a machine that hosts CI runners or other agents' work:

- Cap the hogs: at most cores/2 (not 16 to 96 on 16 threads).
- Run them at Idle priority: `start /low` on Windows, `os.setpriority(os.PRIO_PROCESS, pid, 19)` or `nice -n 19` elsewhere. CI jobs there run at BelowNormal, so Normal hogs beat them.
- Bound their time: a hard timeout on every hog (`timeout -s TERM <n>`), and `ff-leftovers end` afterwards.
- Prefer a machine without runners (`timed_place`, or ask where the leg runs).

**Why (2026-11-26, w6066 and w6110).** From 12:54 to 14:53Z a failover-test worker (w6066) on LothDesktop planted 16 to 96 Python busy loops at Normal priority on a 16-thread machine. The ffu CI jobs beside them (BelowNormal) slowed 10 to 25 times: crosscheck took 56.6 min against a normal 1.1 to 4.2 min, clippy 50.2 min against a normal 6.5 min, and both hit their timeouts (ff-factory PRs #1377 and #1390; w6110, ffu CI slow on LothDesktop). w6110's enforce mode now lowers agents' tools to Idle beside a job on LothDesktop; no other machine has that guard, so the test itself must be polite.

**How to apply.** Before writing a hog: count the cores, check for runners (`list_machines`, the CI runner processes), set the cap and priority in the hog's launch line, and write the time bound beside it. A CI job that suddenly runs many times slower or times out while an agent's load test runs beside it is this, not a code regression: read the machine's load first.
