---
name: stale-unity-lockfile-after-sandbox-editor-stop
description: After the sandbox tool stops an editor, Temp/UnityLockfile can stay behind and run_build_multiplayer_audit.sh refuses to build; confirm no Unity process has the project, then delete it
metadata:
  type: reference
---

# A stale `Temp/UnityLockfile` blocks the batchmode build

2026-10-02, w210, BEAST sandbox. `mcp__sandbox__unity stop` reported `stopped`, then
`scripts/audit/run_build_multiplayer_audit.sh --build-only` exited 2 within a second:

```
ERROR: the project is open in the editor (Temp/UnityLockfile present); a batchmode
       build cannot acquire the project lock.
```

The stop kills an editor that does not quit in 15 s, and a killed editor leaves its lock file.
Run in the background, the script's quick exit looks like a finished build: read its log before
waiting on it.

1. Confirm no editor has the project:
   `Get-CimInstance Win32_Process -Filter "Name='Unity.exe'" | Where-Object { $_.CommandLine -like '*<sandbox name>*' }`
   returns nothing. Other sandboxes' editors and the live game run on the same machine; never
   judge by "a Unity.exe exists".
2. `rm -f Temp/UnityLockfile`, then build.

With the editor stopped is also the moment to fix the CRLF FMOD plists that raise "Repair FMOD
Libraries" after every domain reload ([[beast-sandbox-editor-driven-from-m5]]).

Timings on BEAST for this build: about 15 minutes cold, about 3 for a one-line change.
`FF_BUILD_DIR` and `FF_LOG_DIR` put the player and logs under the sandbox's gitignored `Builds/`;
a player is 2.2 GB, delete it once the runs are recorded.
