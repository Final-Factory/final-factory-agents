---
name: built-pair-lab-traps-073
description: "Four built-player lab traps from the 073 Hazel legs (Mac host + BEAST Windows client over Tailscale): the agent-control `snapshot/nearby` asteroid poll is BLIND at r=8 (scans FFGrid.EntityMap claims; use r>=40 -- a void instrument reported a fork as absent for a whole leg); `cpcompare.py` hardcodes `--players 2` and calls a 3-player save `evidence-invalid` (fpcompare.py is player-count-agnostic); a BEAST poller started as `nohup … &` inside a one-shot ssh dies silently (run it in the ssh FOREGROUND of a locally backgrounded ssh); and a `|` anywhere in a plain `ssh beast 'bash.exe -c \"…\"'` line is eaten by cmd.exe (use beast_ps.sh or scp a script)."
---

# Built-pair lab traps (073, 2026-09-15)

Lab on M5: `/private/tmp/ff073-hazel-20260915/xplat/` (`run-f4.sh` RED shape, `run-g2.sh` GREEN shape,
`asttrans.py LOG [X Z]` prints every change of the polled asteroid set + ore0/last-present/first-absent).

1. **`snapshot/nearby?x=&z=&r=` needs `r>=40` for asteroids.** `PlaytestStateSnapshot.CaptureNearby`
   walks `FFGrid.EntityMap` tile claims in a square of radius r; at r=8 the host returned `[]` for an
   asteroid whose GridTile IS the centre tile, at r=40 it listed it. Leg f3's "first absent" numbers were
   meaningless. Prove the instrument goes positive (the placed asteroid shows up with `oreRemaining: 20`)
   before reading any negative -- the same rule as [[gate-probes-must-be-broader-than-their-system]].
2. **`cpcompare.py` hardcodes `--players 2`.** Hazel's save has 3 players → `evidence-invalid: player count
   is not expected 2`. Pass the save's count; `fpcompare.py HOST CLIENT EPOCH` (direct per-field compare) is
   the reliable check whenever the typed comparator flags the lifecycle.
3. **BEAST pollers must run in the ssh foreground.** `ssh beast '… -c "nohup poll.sh … > /dev/null 2>&1 &"'`
   produced NO log file for the whole f4 leg (worked once in f3 -- do not trust it). Working form
   (`run-g2.sh:21`): `ssh beast '"C:\Program Files\Git\bin\bash.exe" -c "poll.sh LOG 700"' > out 2>&1 &`
   -- the ssh session itself is backgrounded locally and stays open for the poll's lifetime. Same family as
   the "BEAST go-scripts must run in the ssh foreground" rule in [[fleet-harness-operational-2026-09-12]].
4. **No `|` in a plain ssh→cmd.exe line.** `ssh beast '"…bash.exe" -c "grep \"a\|b\" file"'` ran nothing:
   cmd.exe splits on the pipe before bash sees it. Route PowerShell through `beast_ps.sh '<script>'`
   (base64 -EncodedCommand) or scp a script and run it by path. Related quoting rules: [[three-peer-lane-recipe-and-traps]].

Also from these legs: BEAST's git cannot `fetch` GitHub non-interactively (no credential in that shell);
`scripts/fleet-sync.sh` ships a git BUNDLE over scp -- do the same by hand (`git update-ref` a temp
ref, `git bundle create`, scp, `git fetch <bundle> <ref>`, `git merge --ff-only`). Windows verification
build (`ff-worker/build-win-<sha>.sh`, Prepare pass + Build pass) takes ~13 min; a Mac Development
build scheduled from the live M5 editor via a one-shot `EditorApplication.update` callback took ~6 min
and produced a universal (x86_64 + arm64) app, so `arch -x86_64` Rosetta launches work.
