---
name: verify-compile-dll-string-check
description: refresh_unity can compile BEFORE a just-written Edit lands, or silently skip compiling entirely (refresh_triggered false); positively confirm edits are live via DLL mtime, a new UTF-16 literal, or by reflecting the live method's IL
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9863d74f-feac-4abd-bec8-c8be45179774
  modified: 2026-07-27T04:11:19.219Z
---

While debugging the "No item to move" error (2026-07-23), a `refresh_unity` compile finished at
02:32:22 but the Edit-tool write of ConstructionBotTaskSystem.cs landed at 02:32:24 — the editor
compiled the PRE-edit source and never re-imported, so the play session kept running the old code
(old error text, old Burst lib hash) while `editor/state` showed a fresh successful domain reload
and zero CS errors. Looked exactly like a stale Burst cache; it was actually a stale managed DLL.

**Why:** the CLAUDE.md "PASSED doesn't prove your change compiled" trap has a variant where even a
fresh domain reload doesn't prove it — the compile can race the file write.

**How to apply:** after editing + refresh_unity, positively confirm the change is in the built
assembly before trusting any run: search `Library/ScriptAssemblies/<Assembly>.dll` for a NEW
string literal from the edit (UTF-16LE encode it, e.g. python `data.count("my new text".encode('utf-16-le'))`),
and confirm the OLD text is gone. Also compare the DLL mtime vs the source file mtime — source
newer than DLL = the compile missed the edit; run refresh_unity again (editor must be out of play
mode). Bonus workflow: `FFEditor.DevProfileLoadSave.ProfileLoad("<SaveName>")` via execute_code
loads any save by name (enters play mode itself, waits for world-ready); note the sim resumes and
heartbeats advance while SaveProcessState is still "Performing".

**Two more failure modes seen 2026-07-27 (camera-zoom work):**

1. `refresh_unity` can report success WITHOUT compiling at all — the result carried
   `refresh_triggered: false` and the message "Refresh recovered after Unity disconnect/retry; editor
   is ready", yet the DLL was 29 minutes older than the source. `scope: "all"` + `mode: "force"` then
   returned `refresh_triggered: true` and actually rebuilt. Always check the `refresh_triggered` field,
   and always confirm DLL mtime > source mtime before believing any result.
2. The UTF-16 string-literal grep only works when the edit ADDS a literal. For pure logic changes
   (e.g. swapping `a * b` for `math.pow(a, b)`) reflect the live method's IL instead — via
   `execute_code`: `type.GetMethod(name, NonPublic|Instance).GetMethodBody().GetILAsByteArray()`, scan
   for opcodes `0x28` (call) / `0x6F` (callvirt), `Module.ResolveMethod` the following 4-byte token,
   and assert the expected callee is present (and the replaced one absent). This proves what is loaded
   in the domain, not merely that a file changed. Note `strings` is NOT installed in this Git-Bash
   environment, so the DLL-grep route needs PowerShell or python anyway.
