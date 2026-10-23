---
name: no-real-bench-ticket-for-harness-tests
description: "Testing FF Factory's own bench, yield or priority code (harness work, not a timed game run) never takes a real exclusive bench ticket on a shared machine: an exclusive turn quiets the whole machine and ends other workers' batch builds. Use unit tests, or a bench queue rooted in your own temp folder that pauses nobody."
date: 2026-10-23
---

# Harness tests never take a real exclusive bench ticket

**Rule.** When the code under test is FF Factory's own (the bench queue, the bench turn, the person-play yield, process
priorities), exercise it with its unit tests or with an instance rooted in your own `$TMPDIR` (a fake `FF_WORKER_ROOT`
whose `tmp/bench.queue` nobody else reads). Never take a real exclusive ticket (`bench_lock --timing` or `--machine`) on a
shared machine to try it. An exclusive ticket is for a timed game run whose numbers you report, and only then
([checklists/bench.md](../checklists/bench.md)).

**Why.** w1894 (2026-10-23, the yield to a person playing on LothDesktop): to compare game fps with agents' load at
Normal and at Idle priority, a worker on BEAST took exclusive ticket t00000849. Its own script failed before the first
leg, but a turn was granted, and another worker's batch build in beast/slot2 was ended: w1826's host player build, which a
two-machine check waited on. The orchestrator, for lothsahn: "Release BEAST's exclusive bench ticket t00000849 now. It
just killed another worker's batch build in beast/slot2 ... Your work is FF Factory code, not a timed run. Don't take real
exclusive tickets on BEAST. Exercise the yield and priority logic with unit tests, or with a lock instance in your own temp
folder that doesn't pause other workers."

**How to apply.**
- Harness logic: the ff-factory tests (`server/benchTurn*.test.ts`, `server/personPlay.test.ts`) with fakes for procs and
  editors; a live call only against a queue under `$TMPDIR`.
- A fact about Windows or the OS (does a lowered priority inherit to children): a throwaway process tree of your own,
  no lock (w1894: `os.setPriority(PRIORITY_LOW)` reads back as Idle and children started under it inherit it).
- A real before/after the request needs (fps under load): the request's own live check, on the machine it names, when
  that machine is free for it, with the shortest exclusive hold that answers it.
- Whatever took a ticket by mistake: give it back at once (end the script or `bench_queue.py hold` that holds it) and check that
  `bench_queue.py status` shows the lock free and your ticket gone.
