---
name: feedback-built-players-run-from-the-slot-pool
description: Lothsahn 2026-09-29 — never launch a built player from a sandbox or builds/ path; start it through the player slot pool (player_slots.py launch, or FF_LAUNCH in bash), so no new exe path ever raises the Windows Firewall prompt on a lab machine; on a worker-root install each sandbox slotK has its own pair, slotK-0 and slotK-1 (w576)
metadata:
  type: feedback
---

**Rule (Lothsahn, 2026-09-29, w31):** every built player an agent or script starts runs from a
player slot, `<root>\slotK\player\finalfactory.exe` (`F:\ff-players` on BEAST, `~/nevergames/ff-players` on
Macs; LothDesktop is a worker-root install with per-sandbox pairs, below). Never run the exe where it was built.

```sh
python scripts/nightly/player_slots.py launch [--detach] <finalfactory.exe | its folder | .app | .app binary> -- <player args>
# bash script: source scripts/nightly/player_launch.sh, then
"${FF_LAUNCH[@]}" "$PLAYER" -- <player args> &
```

**Worker-root installs (lothsahn, 2026-10-07, w576; LothDesktop first):** no shared pool. Each sandbox slotK
(K = 1..N, N the machine's sandbox count) owns exactly two player folders, `<root>\players\slotK-0` (peer 0, the
host) and `slotK-1` (peer 1, the client), each with one inbound firewall rule; the installer's `--max-sandboxes N` makes
the sandboxes' count, the pairs and the rules together, and a re-run with a new N adds or removes pairs. The same
`launch` / `FF_LAUNCH` picks the pair from the sandbox it runs in (`FF_UNITY_HOLDER`, else the working folder; slot
config `layout: sandbox-pairs`, game repo PR #1165):
- one build: host and client share `slotK-0`, unless the client is started with `--peer 1` (or `FF_PLAYER_PEER=1`);
- two different builds (a cross-build desync check): one folder each, no flag needed;
- outside every sandbox (the nightly lab's scheduled task, which has no FF_* variables) it uses the nightly pair,
  `slotnightly-0` and `slotnightly-1` (lothsahn: "Let's use slotnightly-0 and slotnightly-1"); the sandbox is
  `FF_SANDBOX_ID`, else `FF_UNITY_HOLDER`, else the working folder;
- FF Factory's guard refuses a direct start from another sandbox's pair.

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
  slow-client scripts, `launch_windowed_pair.sh`, the cross-platform peer adapters, `ffnightly.py run`
  (game PR #770; nightly #758) and `poke.py up` (game PR #993) already go through it.
- **`ScenarioRun` alone does not lease** (w323, 2026-10-03). The lease lives in `ffnightly.py`'s `run`
  main (`PlayerSlots` before `ScenarioRun`). `poke.py up` built its own `ScenarioRun` with the raw
  `--player` path, so every `poke.py up --player <per-commit build>` (and agents' wrapper scripts
  around it) raised a prompt: four on lothdesktop in 40 minutes. Code that constructs `ScenarioRun` or
  `lab.Peer` and launches must lease first (`player_slots.acquire_or_fallback`; a short-lived
  launcher whose players outlive it gives each its own lease with `player_slots.share(lease, pid)`).
  A checkout from before #993 still has the old `poke.py`: rebase onto develop.
- **Finding what prompted** (Windows): `Get-WinEvent -LogName 'Microsoft-Windows-Windows Firewall
  With Advanced Security/Firewall'`. Event 2097 added by `svchost.exe` = a prompt appeared
  (`Application Path` names the exe); 2099 by `dllhost.exe` = someone answered it. Match that local
  time against the agents' Bash/PowerShell tool calls in `~/.claude/projects/D--work-ffsb-*/*.jsonl`
  (timestamps are UTC) to find the launcher. `Get-NetFirewallApplicationFilter` rules named
  `finalfactory` (not `Final Factory player slotK`) are each a past prompt.
- **A launch outside the slot root is refused** (w350, game PR #1015). A full or broken pool raises
  `SlotRequired` (`player_slots.py launch`/`FF_LAUNCH` exit 3) instead of running the build folder,
  and `lab.Peer.launch` refuses a local player outside the slot root, so `ffnightly run`, `poke up`
  and the audit, feel and bench scripts stop with the reason rather than at a prompt. Read
  `player_slots.py status` (who holds the slots) and wait or stop your own players; don't work
  around it. `FF_PLAYER_SLOTS=off` runs from anywhere, and is the default on GitHub Actions runners.
- **A branch cut before a launcher fix keeps the old launcher** (w350, 2026-10-03): lag-lead cut its
  branch 20 minutes before #993 merged and its `poke.py up` raised a prompt for its
  `.nightly-builds/<sha>-win` build. After a tooling fix lands, rebase before launching players, or
  run the script from an up-to-date checkout.
- A new Windows machine needs the rules once: `scripts\nightly\setup_player_slot_firewall.ps1` as
  admin (expect "OK: 32 allow rules").
