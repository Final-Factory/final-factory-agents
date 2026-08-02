---
name: watch-logs-without-full-scans
description: "Never poll a large log by re-scanning the whole file each tick, and always prove the watcher works with one direct query first"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 822bc922-d77f-4c91-8be4-7e361f39d590
  modified: 2026-07-25T23:08:20.229Z
---

When waiting for a marker line in a big log, do NOT arm a loop that re-scans the entire file
every tick. On 2026-07-25 I watched for `LOAD PROFILE: MeltCPU` with
`Select-String -Path Editor.log` on a 5s interval against a ~28MB log. Each scan cost more than
the 5s interval, so the watcher fell permanently behind and never reported — the load had
finished minutes earlier and Ben had to point out the shell was still running. A single `grep`
found the marker instantly.

**Why:** a poll whose per-tick cost exceeds its interval never converges, and its silence is
indistinguishable from "the thing hasn't happened yet". That turns a watcher meant to save time
into a stall the user has to notice for me — the exact failure the CLAUDE.md monitoring rule
("the user must never have to ask for the verdict") is meant to prevent.

**How to apply:**
- **Query once, directly, before arming any watcher.** If the event already happened, a plain
  `grep`/`Read` answers immediately and no watcher is needed. This also proves the pattern
  actually matches before I depend on it.
- **Poll only the tail, not the file.** `tail -c 200000 <log> | grep -a <pattern>`, or record the
  byte offset (`stat -c %s`) up front and read only from there. Cost must stay ~constant as the
  log grows.
- **Interval must exceed the per-tick cost** with margin. If a tick can take seconds, use a
  30s+ interval, not 5s.
- **Prefer a command that exits on the condition** with Bash `run_in_background` (one
  notification) over a Monitor loop, per the Monitor tool guidance.
- **If a watcher has produced nothing while the underlying work plausibly finished, verify
  directly instead of waiting longer** — then kill it with TaskStop.

Related: [[unity-editor-log-gotchas]] for the Editor.log specifics on this machine.
