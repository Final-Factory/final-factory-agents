---
name: hang-watchdog-reports
description: "A frozen built player writes and uploads its own hang report (all threads' stacks, kind hang on FFBox) since w1780; look for it before gdb. Crash, desync and bug reports carry the previous session's log since w1777. A hand-sent intake report id must be a D-format GUID."
---

# Hang reports and the previous session's log (w1780, w1777; 2026-10-23)

**A frozen game reports itself.** Since game PR #2259 (w1780) every built player runs a hang
watchdog. When the main loop stops for 10 s (120 s while a load or a save holds a lease), a
background thread captures every thread's native and managed stack from inside the process and
writes `<backtrace>/<version>/crashes/<time>-hang/`:
- `threads.txt`: every thread's stack and its CPU time over 1 s;
- `hang.json`, `context.txt`, `Player.log` and `Player-prev.log`;
- `hang.dmp` on Windows.

It uploads the report as FFBox kind `hang` (coarse signature `hang:<x.y.z>`), and FFBox
diagnoses it like a crash. On Linux it reads `/proc/self/task` and `process_vm_readv` on itself,
so Yama's `ptrace_scope` does not stop it.

Before reaching for gdb or ptrace on a frozen game, look for that report on the player's machine
or on FFBox (`list_ffbox_files` kind `hang`). In w1775, `ptrace_scope` blocked gdb, and gdb then
attached to Steam's reaper instead of the game.

To test it, run a development player with `-ffDebugHang <after>:<hold>[:spin]`. Turn the
watchdog off with `-ffNoHangWatchdog`. How it works and what failed:
`Documentation/Hang-Watchdog.md` in the game repo.

**Read the previous session's log.** Since w1777 (PR #2242), three reports carry the previous
launch's log:
- a crash report: `Player-prev.log`;
- a desync report: `<report>.player-prev.log`;
- the in-game bug report: `Player-prev.log`, sent to Discord.

The session that froze or crashed is often the previous one: the player relaunched and then
reported.

**Sending a test report by hand** through `FFIntakeClient.Send`: make the report id with
`Guid.NewGuid().ToString("D")`, as `ReportUploadQueue` does. An `"N"` id is refused with
`400 bad_report_id` (measured, w1780). Put a `test_upload` detail in it saying what it is, so
FFBox's diagnosis does not take it for a player's report.
