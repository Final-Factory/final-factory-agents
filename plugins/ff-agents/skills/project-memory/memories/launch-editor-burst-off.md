# launch-editor.sh brings editors up with Burst DISABLED — check every relaunch

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
