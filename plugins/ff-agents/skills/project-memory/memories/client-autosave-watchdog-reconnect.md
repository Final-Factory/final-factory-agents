---
name: client-autosave-watchdog-reconnect
description: "074 T101: every multiplayer CLIENT autosaved itself ~5 min in, paused (Time.timeScale 0), NRE'd in the player marshal, never resumed, LivenessWatchdog tripped and it self-reconnected -- both clients of a three-peer leg dropped once at the same minute; the 073 g13 client log has the same signature. Fixed ddca1007e: only the save-authority peer saves (SaveGameManager.IsSaveAuthorityPeer + entry guard, AutosaveController skips, ffauto game.save is host-only and clients answer 'host-only'). Tell: WatchdogTripped in a client log ~300 s after join, host untouched."
---

# Client autosave → pause → watchdog reconnect (074 T101, 2026-09-19)

**Signature.** On a three-peer built-player leg both clients dropped ONCE, ~5 minutes after joining,
each with `WatchdogTripped` in its own log and a self-reconnect; the host never noticed anything but
the rejoin. The 073 g13 client log carries the same lines — it was always there, read as flakiness.

**Mechanism.** `AutosaveController` fired on every peer. On a client the autosave paused the game
(`Time.timeScale 0`), the save's player marshal NRE'd (no host-side player state to marshal), the
pause never lifted, and `LivenessWatchdog` treated the frozen loop as a hang → disconnect + reconnect.

**Rule.** Saving is a host-authority action. `SaveGameManager.IsSaveAuthorityPeer` gates the entry,
`AutosaveController` skips non-authority peers, and `ffauto:game.save` on a client is rejected with
`host-only` (M3 at hb 6669 on leg t1b). Unit: `SaveAuthorityPolicyTest`. Proof: leg t1b, 7-minute
dwell, 0 `WatchdogTripped`, 7,244 compared / 0 mismatches.

**Saving is host-only by design, not just to dodge this crash** (Lothsahn, 2026-09-22): a save
has to stop the heartbeat, and only the host may stop it, so a client save desyncs whatever else
is fixed. Do not "re-enable client saves": c36adc2b9 did it on a misread of this entry (it only
described the crash) and e5cfa1664 reverted it the same night. The one valid client-side change
is UX: `SaveGamePanel` opens the modal "Saving game" bar before calling `SaveGame`, and a client
got stuck behind it, so the client branch of the guard now closes the bar and fires the callback.
