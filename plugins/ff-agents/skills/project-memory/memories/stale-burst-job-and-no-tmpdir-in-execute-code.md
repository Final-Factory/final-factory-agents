---
name: stale-burst-job-and-no-tmpdir-in-execute-code
description: After a recompile an EditMode test can still run the old Burst-compiled job body; the Burst switch is machine-wide; Unity's process has no TMPDIR, so a probe file lands at the drive root (w1290)
---

# A test ran the old Burst job; the Burst switch is machine-wide; no TMPDIR inside Unity

**What happened** (w1290, beast slot3, 2026-10-14). I edited `OverdriverHeatSystem.OverdriverHeatJob.Execute`,
the editor recompiled, and `HeatGatingTest` still failed with master's numbers (an Overdriver made 22 where the fix
gives 0.5), twice. The managed method was the new code: `Execute`'s IL was 121 bytes, against 306 on master (read
with `MethodInfo.GetMethodBody().GetILAsByteArray().Length` through `execute_code`). With
`Unity.Burst.BurstCompiler.Options.EnableBurstCompilation = false`, the same tests passed 15/15. In a fresh sandbox,
after a full Burst compile, they passed 15/15 with Burst on. So the job had run a stale Burst-compiled body.

**How to apply**
- After you edit a job body, a RED or GREEN that does not match your change may come from a stale Burst body. Check
  the managed IL size of the job's `Execute` method (above), then run the test once with Burst off. Settle the
  final verdict with Burst on, after a fresh compile.
- `EnableBurstCompilation` set through `execute_code` is an editor preference. It outlives the editor and reaches
  every other sandbox's editor on the machine (slot2's editor started with it off). If you switch it off, switch it
  back on before you leave. Switching it on starts a full Burst compile: about 3 minutes at ~11 cores on beast,
  during which every MCP call times out. Wait for the editor's CPU to settle before the next call.
- Unity's editor process has no `TMPDIR`: `Environment.GetEnvironmentVariable("TMPDIR")` is null in
  `execute_code`, and `TEMP` is the user's AppData temp. So `GetEnvironmentVariable("TMPDIR") + "/probe.txt"` writes
  `\probe.txt` at the root of the current drive (`F:\w1290-probe1.txt`). That is outside the worker folder, where the
  harness refuses to delete it. Spell the worker temp path out in the code (`F:/ffw/tmp/ffa-<session>/...`), or
  return the text from the call.
