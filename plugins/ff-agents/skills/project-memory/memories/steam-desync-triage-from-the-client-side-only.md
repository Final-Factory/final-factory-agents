---
name: steam-desync-triage-from-the-client-side-only
description: "How to triage a live Steam desync with ONLY the kicked client's machine (Ben 2026-09-12: never use Loth's machine): what Player.log carries, how to date both peers' builds (depot DLL byte-diff; system type names inside the transfer save; what the join gate does and does not cover), securing the transfer save, and the reproduction rule — the HOST's own player must be under fire; idle/freshly-loaded hosts never fork; same-platform pairs forked too."
---

# Triage a Steam desync from the client side only (2026-09-12, 069)

**Ben's rule.** "We aren't using Loth's machine to diagnose this stuff, you have to do it on your own."
Everything below needs only the kicked client's Mac plus our fleet.

**What the client's `~/Library/Logs/Never Games/finalfactory/Player.log` gives you** (rolls to
`Player-prev.log` on relaunch — copy both immediately): `[DesyncDetector] … diverged from the host at
heartbeat N (surfaces: …; host=… peer=…)` — N is always a multiple of 8 (the detector samples every 8
hb, so "hb 8" means "already different right after the load"); `[Reconnect] DisconnectClassified …
Desync:RecoveryFailed|re-diverged after a completed recovery` = the kick; `===== LOAD PROFILE:
tempSaveGame… =====` per recovery load with an `Entities: N` line (the host's live world size at
each transfer save); `Hit max attempts on … world object generation` lines per load = the client's
world-gen REPLAY (identical every load and identical on a Windows build → the client is
self-consistent; the divergence is against the host's LIVE state). Secure the transfer save
`…/Saves/tempSaveGame<id>.zip` at once — it is overwritten on every join/recovery.

**Dating the two builds without the other machine.** (a) The Steam depot's Managed DLLs
(`…/steamapps/common/FinalFactory/finalfactory.app/Contents/Resources/Data/Managed`) vs a local build:
byte-diff per DLL — ~72 differing bytes = same source (MVID/timestamp), megabytes = different code;
probe UTF-8 type/method names added by candidate commits (e.g. `BlueprintPreviewGroupHygieneSystem`,
`ResolveRotation`, `EntityGridPersistenceSystem`) to bracket the commit. `appmanifest_<appid>.acf`
holds `buildid`/`lastupdated`. (b) The HOST's build is dated by the transfer save: system payloads
in `SaveState2.dat` are keyed by full type name (`SaveGameManager.ResolveBinarySystem(string)`), so
`grep -a FFSystems.Map.EntityGridPersistenceSystem` proves the host was ≥ the commit that added it.
`MetaSaveState2.dat` carries the version string and the host's mod list. (c) The join gate
(`NetworkedGameManager.cs:920,971`, `PeerCompatibilityToken`) compares protocol, op-family,
surface-set and content hashes ONLY — a system-body change passes it.

**Reproduction rule.** Loading the host's transfer save on our own host and joining a client
(load∘serialize on both sides) is symmetric and never reproduced it (r7: 4095+1469 hb clean). Forcing
resyncs on a host with 15 min of idle live time did not either. What did: the host's OWN player flying
into camp defenses (`spawn.ships|Bat|2`, `movement.goto|<camp>`); the fork came 130–3000 hb later and
re-forked at hb 8 after every recovery. Windows/Mac AND Mac/Mac pairs forked → not codegen. Per-machine
identity decides which saved player a host controls (M5 = Ben's, BEAST and M3 = Loth's) — pick the host
machine by the player you need. The fix: [[player-presentation-transform-forks-combat]]. Instruments:
[[diagnostic-profile-config-recipe]].
