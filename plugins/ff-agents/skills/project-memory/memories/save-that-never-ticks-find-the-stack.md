---
name: save-that-never-ticks-find-the-stack
description: A save that loads but never reaches heartbeat 1 (or a game frozen at 100% CPU) - get the stuck stack from the editor log, a built Mac player's sample, or a macOS crash report before suspecting anything; Burst recursion overflows depend on the platform's stack
metadata:
  type: project
---

**w719 (2026-10-09, Build 89 save `autosave_3`, Discord 1557865115196330065).** FFBox's triage named two
suspects (blueprint ghost instantiation, the placement validator's tile scans); neither was it. The stuck
system was `StationConnectionsJob`, whose walk recursed once per touching Direct structure (solar panels,
radiators, power distributors) and per side-by-side connector, and overflowed the job worker's stack on a
field of about 1,000+ touching panels. Fixed by PR #1314 (iterative walk); nightly `MP-W719-mass-solar-field`.

**How the stack was found, cheapest first:**

1. **Load the save in the editor** (open `Assets/Scenes/main.unity` FIRST: an editor that opened an Untitled
   scene runs `Load Save (from dev_loadsave.trigger)` forever with nothing in the log, not even "Entity
   Prefab Container not yet created"). Right after a domain reload Burst has not compiled the job yet, so it
   runs managed, and a deep recursion becomes a `StackOverflowException` whose whole chain is in
   `Logs/sandbox-editor.log`. The editor may crash on a later one (`~/Library/Logs/DiagnosticReports/Unity-*.ips`
   names `Scripting::RaiseStackOverflowException`).
2. **A built Mac player** (`player_slots.py launch`, `-batchmode -nographics -ffAutomationRole solo
   -ffAutomationSave <name> -ffAgentControl true`): `sample <pid> 3` resolves Burst frames
   (`lib_burst_generated.bundle`, full job and method names) but not Mono JIT frames (`???`). Read the heartbeat
   from `GET /v1/snapshot/session` (`127.0.0.1`, token in `AgentControl/session-<pid>.json`): the session journal
   only records events, so its `hb` stays 0 on a healthy run.
3. **A macOS crash report** of the player (`finalfactory-*.ips`): `EXC_BAD_ACCESS KERN_PROTECTION_FAILURE` "stack
   guard region" on a `Job.Worker N` thread is a stack overflow; the faulting thread's frames name the job.

**The same save can tick on one platform and hang on another.** A recursion's depth limit is the job worker's
stack: autosave_3 ticked at 16 UPS on the Steam 0.50.0.91 Mac player, overflowed in the editor's managed path,
and hung the reporter's Windows player under Proton; a bigger field (2,400 panels) crashed the Mac player too.
So "it loads fine here" does not clear a recursion: build a bigger case (the w719 fixture generator,
`ValidationScenarios/w719/make_mass_field_bp.py` in the game repo) and run it on the pre-fix build for the RED.
