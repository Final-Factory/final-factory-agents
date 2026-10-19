---
name: compile-check-before-you-start-the-editor
description: "A worker that reverts, deletes or renames code with its Unity editor stopped, then starts the editor, lands on Unity's native \"Enter Safe Mode?\" prompt when anything still references what went (w1470, worker d582a5da on m5/slot1, 2026-10-18: a reverted file a test still used; Ben: \"keeps happening you should be able to get past this\"). Change code with the editor running and refresh, or, with it stopped, search for every name you removed and compile-check offline before you start or restart it. The claim \"no automation channel can click it\" was wrong: the daemon's dialog watch presses Ignore when it can see the dialog, and from w1495 it closes an editor nobody answers and reports the errors."
date: 2026-10-18
---

# Compile-check before you start the editor after a revert or a delete

**Rule.** A compile error on disk when an editor starts puts it on Unity's native "Enter Safe Mode?" prompt
(Ignore / Quit / Enter Safe Mode). The MCP bridge loads only after the prompt, so from the worker's side the editor
looks hung. So:

1. **Change code while the editor runs**, then `refresh_unity` and `read_console` for `error CS`. A compile error
   in a running editor is just a console error: the bridge stays up and reports it. This covers reverts (`git
   checkout -- <path>`, `git restore`), deletes, renames and a merge that removes a type.
2. **With the editor stopped, check before you start it.** For every type, member or file you removed, `git grep -n
   <name> -- '*.cs'` across `Assets/`, tests included (any assembly trips the prompt, `FFEditorTests` too: w1157).
   Then run the offline compile check with the editor's last response file (editor-ops
   `references/recovery.md`, "Check the code compiles before you (re)start an editor") for each assembly you
   touched and the assemblies that reference it. Start the editor only when both are clean.
3. **If an editor is already on the prompt**, the daemon's dialog watch presses Ignore on its next look (30 s).
   With a daemon that has w1495 (ff-factory #436), an editor nobody answers within 90 s is closed, and its `error CS`
   lines come to you as a `[unity]` message and in `unity status`. Fix those, then start it. Do not restart into the
   same errors: it stops at the same prompt.

**Why.** w1470 (2026-10-18, m5/slot1): worker d582a5da reverted files with the editor stopped while a test file still
referenced them, started the editor, and it sat on the prompt until Ben clicked it. w1157 (biscuit) restarted into the
same prompt three times before checking the code offline. w1438 wrote down that "no automation channel can click it",
and editor-ops repeated it. That was wrong: FF Factory's dialog watch had an always-Ignore rule for it, and
measured on Windows it pressed Ignore 7 s after the dialog appeared. It failed on m5 because a Mac's watch pauses
while the screen is locked or the display asleep. w1495 measured that no launch argument skips the prompt into a
normal editor: `-ignoreCompilerErrors` is batch-mode only, and the "Show Enter Safe Mode Dialog" preference only
enters Safe Mode, where the bridge does not load. So the daemon now closes an editor nobody answers and reports the
errors ([research the route before you say "can't"](research-the-route-before-you-say-cant.md)).

**How to apply.** Before any `mcp__machine__unity start` or `restart`, and before a batch build, after a revert,
delete or rename made with the editor stopped: grep for every removed name, then compile-check offline. A `[unity]`
message saying the editor "stopped at its \"Enter Safe Mode?\" prompt" is a compile error you left on disk. Fix the
errors it lists, then start the editor.
