# EditorApplication.delayCall never drains in a sandbox editor: use a one-shot update

**What:** in an FF Factory sandbox editor with no window in front (headless Macs, an unfocused or locked-screen
editor), callbacks added to `EditorApplication.delayCall` are never run, while `EditorApplication.update` ticks.

**Why (w5270, 2026-11-23, m5 slot3):** the game's new `BurstPrefGuard` first used `delayCall` from its
`[InitializeOnLoad]` constructor and never ran; reflection on `EditorApplication.delayCall` showed 29 callbacks still
queued minutes after the reload. Seen before from `execute_code` (074 T136, 2026-09-21, and 2026-09-29: see the
built-pair lab trap memories), but only recorded there, so the next worker missed it.

**How to apply:** run once-after-load work from a one-shot update callback:
`EditorApplication.update += Once;` with `static void Once() { EditorApplication.update -= Once; ... }`, guarded by a
`SessionState` flag when it must run once per editor process rather than per domain reload.
