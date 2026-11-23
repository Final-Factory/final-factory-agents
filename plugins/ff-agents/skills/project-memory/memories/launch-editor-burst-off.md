# launch-editor.sh brings editors up with Burst DISABLED — check every relaunch

**Cause found (w5270, 2026-11-23):** the launch script was never the cause. `BurstCompiler.Options` is backed by the
user-wide EditorPref `BurstCompilation`: com.unity.burst `BurstEditorOptions` reads it at load and writes all five
Burst prefs back on ANY option change (`GlobalOnOptionsChanged`). The game's `LocalMultiplayerAutomationLauncher`
auto-start called `DisableBurstForAutomationSession()` (`EnableBurstCompilation = false`) for every config without
Audit* fields, so one automation run turned Burst off for every editor of that user on the machine, from each one's
next domain reload. On BEAST that held 2026-11-22 ~23:00Z to 11-23 11:37Z (sandbox tests ran ~4x slower); m5's pref
was 0 too. Fixed in FinalFactory#4225 (the call is gone; `BurstPrefGuard` turns the pref back on in every editor;
`NoCodeTurnsBurstPrefOffGuardTest` refuses new code that writes it off) and ff-factory#1093 (the daemon turns it on
before it starts a sandbox editor). A run that truly needs managed jobs starts its own editor with
`--burst-disable-compilation` or `UNITY_BURST_DISABLE_COMPILATION=1` (per process). The checks below still hold for
an editor that predates the fix.


**Observed three times, 2026-08-22/23** (M5 main editor once, both M3 editors once each):
an editor launched via `scripts/launch-editor.sh` comes up with
`BurstCompiler.Options.EnableBurstCompilation = false`, even when the previous instance had
it enabled. This compounds the known one-way-switch trap: nothing re-enables it, every job
runs managed (~3.7x slower), and a Burst-asymmetric editor pair rate-modulates the 062
containers fork class.

**How to apply:** after EVERY `launch-editor.sh`, run `scripts/editor-preflight.sh <project>`
(it fails rc=5 with an exact message on this) BEFORE any paired or timing-sensitive work;
on failure, enable via execute_code/eval (`BurstCompiler.Options.EnableBurstCompilation =
true`) and drain to a STABLE zero — two zero readings of
`UnityEditor.Progress.EnumerateItems()` Burst items, 60s apart, because the queue refills in
waves after a recompile. A single zero reading has produced two false-ready preflights.

**Process match rule (2026-09-08):** a Unity project process may have trailing arguments such as
`-logFile`, so process ownership must match the exact `-projectPath <project>` argument followed
by a space or end-of-command, not only the command end. `scripts/editor-preflight.sh:30-32` and
`scripts/launch-editor.sh:24-28` use `-projectPath ${PROJECT}( |$)`: preserve that boundary and
test both the intended project and a sibling path. A false zero result permits a duplicate editor
launch against one project.
