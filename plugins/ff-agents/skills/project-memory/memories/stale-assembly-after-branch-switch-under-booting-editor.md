---
name: stale-assembly-after-branch-switch-under-booting-editor
description: "A branch switch that lands while the sandbox editor is still booting can leave FFSystems.dll compiled from the PREVIOUS branch's source, and a forced refresh does not rebuild it (same content hash). Symptom: the previous branch's tests fail on develop code. Compare the DLL's time with the changed file's, then make a real content change, compile, revert, compile"
metadata:
  node_type: memory
  type: project
  modified: 2026-10-01T20:30:00.000Z
---

# A branch switch under a booting editor can leave a stale assembly that a forced refresh keeps

**Learned:** 2026-10-01, w157 (BEAST sandbox slot-5), switching from another task's branch to a
branch off `origin/develop` while the sandbox editor was starting.

**What happened.** `switch_branch` reported "no Unity instance connected; Unity was not refreshed".
The editor's startup compile and the checkout overlapped (the changed system file was written at
11:29:22, `Library/ScriptAssemblies/FFSystems.dll` at 11:29:41). The DLL held the OLD branch's
version of one system. Everything looked fine: `refresh_unity` and `wait_for_unity compiled` both
said compiled with no errors. Then the fast suite failed three tests in `AsteroidLowOreWarningTest`,
a fixture the previous branch had changed and the task never touched. CI on the same commit was
green.

**Why a forced refresh did not fix it.** Touching the file and `refresh_unity(mode=force,
compile=request)` logged "script compilation time: 0.001s" and left the DLL's time unchanged. The
build system compares content, and the file on disk already had the content it had recorded.

**Tell.** A test of code you did not touch fails locally and passes in CI, and the failing code
differs between the branch you came from and the one you are on
(`git diff <old-branch> origin/develop -- <file>`). Compare the times:
`ls -la --time-style=+%H:%M:%S Library/ScriptAssemblies/FFSystems.dll <the changed .cs>`.

**Fix.** Force a real rebuild of that assembly: append a comment line to one of its files,
compile, `git checkout -- <file>`, compile again. Poll the DLL's time rather than trusting
`wait_for_unity compiled since:last`, which can answer from the earlier compile. Then rerun the
suite. Do this before believing ANY test result after such a switch: the stale assembly also
serves play mode.

**Avoid it.** Wait for the editor to be up (`wait_for_unity ready`) before switching the branch, so
the tool closes the scenes, refreshes and recompiles itself.
