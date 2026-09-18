---
name: built-pair-lab-traps-2026-09-18
description: "Six more built-pair lab traps from the 073 g10/g11 legs (Mac host + BEAST Windows client): macOS sed has no `\\b` (a leg script kept the old leg's file names silently); scp to Windows OpenSSH needs `C:/Users/...` targets, `/c/Users/...` fails with 'No such file'; `snapshot/nearby?x=&z=&r=` takes TILE coordinates (a world-unit probe returns 0 structures); PowerShell Select-String is case-INsensitive so `BC[0-9]{4}` matches a cache-hit hash — pass -CaseSensitive and `\\b`; `PowerSatisfactionDetail` carries a per-peer `nCalc` counter — mask it before diffing rows; the client's auto-written report on a kick lives under LocalLow/DeterminismAudit (copy to a plain path, then scp)."
---

# Built-pair lab traps, day 3 (073 g10/g11 legs, 2026-09-18)

1. **macOS sed ignores `\b`.** `sed 's/-g9\b/-g10/'` on BSD sed matches nothing and says nothing; the
   generated `launch-host-g10.sh` still opened `host-config-g9.json` and `host-terminal-g9.log`. Generate leg
   files with plain substitutions (`s/g9/g10/g` then re-pin the build sha) and `grep` the result for the old
   leg id before launching.
2. **scp to Windows OpenSSH wants the Windows path.** `rydin@beast:/c/Users/rydin/ff-worker/x` → "dest open …
   No such file or directory"; `rydin@beast:C:/Users/rydin/ff-worker/x` works. Git-bash `/c/…` paths are for
   commands run INSIDE bash.exe, not for the OpenSSH server's file API.
3. **`snapshot/nearby?x=&z=&r=` is in TILES.** Probing world (70,-220) returned 0 structures; tile (7,-22)
   returned 44 (`nearby_dp.py` was always called with tiles; the r≥40 rule for asteroids still holds).
4. **PowerShell Select-String is case-insensitive.** A "Burst error" gate written as `BC[0-9]{4}` fired on
   `…bc0110…` inside a Bee cache-hit hash and rejected a clean build. Use `-CaseSensitive -Pattern
   "\bBC[0-9]{4}\b"` and print the matching line before believing a count.
5. **`PowerSatisfactionDetail.nCalc` is per peer** (the peer's own calculation count — a joined client is
   behind by its join time). Every row "differs" until you strip ` nCalc=\d+`; the fingerprint field itself
   never folds it.
6. **The kicked client's report.** `cp.sh` cannot checkpoint a client that was kicked ~5 s after the first
   verdict, but the client writes its own report on the kick:
   `C:\Users\<u>\AppData\LocalLow\Never Games\finalfactory\DeterminismAudit\network-determinism-audit-<runId>-<leg>-client.log`.
   `Copy-Item` it to a plain path (spaces defeat scp quoting), scp it, and `fpcompare.py` it against the host's
   checkpoint report — it holds the same per-heartbeat Fingerprint records (and the diagnostic rows).

Also confirmed: a diagnostic leg must checkpoint on the FIRST `DesyncRecoveryAttempt` — the kick follows
within seconds ([[built-pair-structure-removal-and-early-diagnostic-checkpoint]]); and both peers must be
stopped BY PATH and both `.ff-local-automation.json` removed after every leg, or the next launch silently
joins a stale player (the g10d client was still alive when g10i was being armed).
