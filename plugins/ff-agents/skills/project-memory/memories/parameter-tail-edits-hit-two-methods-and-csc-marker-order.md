---
name: parameter-tail-edits-hit-two-methods-and-csc-marker-order
description: "A structural python/sed edit keyed on a parameter-list TAIL can land on two methods (ColumnarFastPathLoader.CreateGroupEntities and WriteGroupData share the tail 'finalizedIdToIdMap, oldNewEntityMap)' + 'var count = group.Entities.Length;' — CS7036). After any signature edit, grep -c the new symbol and expect the intended count. A failed compile keeps the last-good DLL (ScriptAssemblies mtime unchanged) while the Editor.log TAIL still shows the OLD errors — judge a compile by the order of the Csc markers, never by the tail."
---

# Parameter-tail edits hit two methods; judge a compile by Csc marker order (074 T110, 2026-09-19)

**The edit trap.** Adding `Entity cometPrefab` to `ColumnarFastPathLoader` by a scripted
replacement of the parameter tail `finalizedIdToIdMap, oldNewEntityMap)` and the following
`var count = group.Entities.Length;` landed on TWO methods — `CreateGroupEntities`
(`Assets/Scripts/Serialization/Columnar/ColumnarFastPathLoader.cs:163`) and `WriteGroupData` (`:301`)
share that tail — and the call site at `:84` then failed with CS7036 (missing argument). Rule:
after ANY signature edit made by script, `grep -c '<newSymbol>'` the file and expect exactly the
intended count (declaration + call sites); anchor structural edits on the method NAME line, not on
a shared tail.

**The compile-judging trap.** A failed compile keeps the last-good DLL: `Library/ScriptAssemblies/
FFSpaghetti.dll` mtime does not move, tests run green against the OLD code, and the Editor.log
TAIL can still show the PREVIOUS compile's errors while the fix is already compiling (or vice
versa). Judge by ORDER: find the last `Csc` / compilation-start marker for the assembly, and read
only what follows it — `error CS` after that marker = this compile failed; a fresh
`Refreshing native plugins`/domain-reload marker with none = it passed. Then confirm the DLL mtime
moved and `Type.GetType("<ns>.<NewType>, <Assembly>") != null` on every editor that will run the
code ([[stale-clone-editor-invalidates-pair-evidence]]).

**Companion rituals that worked this session.** RED for a test that references the fix's NEW
members: keep the new API, blank the detection (compilable RED), then restore. `refresh_unity
scope=scripts` may answer `refresh_triggered:false` yet still compile when `compile=request`;
`scope=all mode=force` imports a new file's `.meta`. The bridge drops ~45 s after every
`run_tests`/refresh and the main editor's port FLIPS 6400↔6402 — re-pin by the port in
`~/.unity-mcp/unity-mcp-status-<hash>.json`, poll the SAME job id.
