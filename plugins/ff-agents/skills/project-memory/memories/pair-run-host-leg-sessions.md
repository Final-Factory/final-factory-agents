---
description: A pair run's host leg on a shared machine - a new port per session (an old client's reconnect engine rejoins a new host on the same port), what to do on a bench-lock revoke warning, and timestamping a host log that has none.
---

# Pair run, host leg: one port per session, bench revokes, and a timestamped host log

From w3331 (pair run for w3322's PR #3324, the client uplink watchdog; host leg on BEAST slot4, client on lothdesktop,
2026-11-07). Session B (the control run) had to run three times before one counted.

- **Give every session its own host port.** A client whose host you ended keeps its reconnect engine running
  (`ReconnectAttempt(1..4)`) and rejoins a NEW host you start on the same ip and port by itself: Host B ended at
  ~07:37:33Z, Host B2 came up on 7932 at 07:38:08Z, and the old client's reconnect was already in at 07:38:05Z
  (`ReconnectRestored attempts=3`), before the host leg had told anyone it listened. That client's log already held the
  drop, so it could not prove "no WatchdogTripped at all". Port 7931 for A, 7932 for B, 7933 for a rerun; and ask the
  client leg to end its old process before a rerun.
- **A shared bench ticket is revoked when an exclusive timed run waits** (`Documentation/Bench-Lock.md`, the turn
  limit): the 5-minute warning ("ends at 07:41Z") means the host player is paused or stopped mid-session, which a
  client sees as a heartbeat stall (`WatchdogTripped appliedAgeSeconds=...`). On the warning, end the host yourself,
  message the client legs that the session is void, and relaunch with `player_slots.py launch --bench-wait <s>` (it
  was granted again at once on BEAST, since the exclusive tickets were still waiting behind other shared holders).
- **A host player log has no timestamps** and the brief asks for them. Before launching the host, start a background
  `tail -n +1 -F <log> | while read ...; printf '%s %s\n' "$(date -u +%T)" ...` filtered on `[Netcode]`, `Client-`,
  `[Reconnect]`, `HangWatchdog`, `FlowControl`, `MP pacing` and `status`. Started after the player, the replayed lines
  all get the watcher's start time. In a bash `case` pattern write `*"[Netcode]"*`, not `*[Netcode]*` (a bracket
  expression that matches almost every line).
- **The host itself can stall on BEAST**: the w3331 host hung its main loop 27.7 s, 48.8 s and 13.5 s (and 11.9 s in
  the rerun) as a client joined, main thread in `NtCreateFile`/`NtClose` under `MonoIO`; hang reports under
  LocalLow `backtrace/<version>/crashes/<stamp>-hang`. Grep the host log for `[HangWatchdog] HANG` before blaming the
  change under test for a client-side trip, and say so to the client leg.
