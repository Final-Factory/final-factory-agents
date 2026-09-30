---
name: feedback-built-players-run-from-the-slot-pool
description: Lothsahn 2026-09-29 — never launch a built player from a sandbox or builds/ path; start it through the player slot pool (player_slots.py launch, or FF_LAUNCH in bash), so no new exe path ever raises the Windows Firewall prompt on a lab machine
metadata:
  type: feedback
---

**Rule (Lothsahn, 2026-09-29, w31):** every built player an agent or script starts runs from a
player slot, `<root>\slotK\player\finalfactory.exe` (`D:\work\ff-players` on lothdesktop,
`F:\ff-players` on BEAST, `~/nevergames/ff-players` on Macs). Never run the exe where it was built.

```sh
python scripts/nightly/player_slots.py launch [--detach] <finalfactory.exe | its folder | .app | .app binary> -- <player args>
# bash script: source scripts/nightly/player_launch.sh, then
"${FF_LAUNCH[@]}" "$PLAYER" -- <player args> &
```

**Why:** Windows Firewall keys its allow rules on the exact exe path. A player started from a new
folder (w17's `D:\work\ffsb\bug-1553894544\builds\pilot`, 2026-09-29) raises the "allow
finalfactory.exe on public and private networks?" dialog on the desktop, and an unattended run stalls
behind it; a dismissed dialog leaves Block rules that win. `setup_player_slot_firewall.ps1` allows the
eight slot paths once per machine (32 rules), so a slot never prompts.

**How to apply:**
- `launch` leases a slot, hard-links the build in (a copy across volumes) and runs it there. The lease
  is held as the player's pid and lapses when it exits. The host and clients of one build share a
  slot. A slot is labelled with `--sha`, else the build's `build-manifest.json` commit, else its folder,
  and reused only when that label AND the build's content fingerprint match (managed DLLs, Burst,
  GameAssembly and small files hashed; never the exe, which is Unity's stub and the same in every
  build). So a rebuild under the same `--sha` or into the same folder always gets a fresh copy (game
  PR #829, w91; before it, such a rebuild could silently run the slot's old build). A `--sha` that
  contradicts the build's `build-manifest.json` logs a WARNING; cite the `build` fingerprint the
  launch prints as what actually ran.
- Mac/Linux: the launcher `exec`s the player (same pid). Windows: it waits, returns the player's exit
  code, and killing it (`kill $!`, `Stop-Process`, `timeout`) ends the player through a job object.
  `--detach` prints `{"pid","player","slot","build"}` and returns at once.
- A player found by its command line (`peer.py`, `agent_chain.py`) is marked by its `-logFile` or
  label now: its exe path is the slot, not the build.
- The audit (`run_build_multiplayer_audit.sh` and its wrappers), feel, bench, join-policy and
  slow-client scripts, `launch_windowed_pair.sh`, the cross-platform peer adapters and `ffnightly.py`
  already go through it (game PR #770; nightly #758).
- Full pool or `FF_PLAYER_SLOTS=off`: the path itself runs, with a log line. The pool is off by
  default on GitHub Actions runners. `player_slots.py status` shows the pool.
- A new Windows machine needs the rules once: `scripts\nightly\setup_player_slot_firewall.ps1` as
  admin (expect "OK: 32 allow rules").
