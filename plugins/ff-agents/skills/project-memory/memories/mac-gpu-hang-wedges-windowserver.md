---
name: mac-gpu-hang-wedges-windowserver
description: "A Metal GPU hang in a built Mac player can leave the frozen game stuck exiting with the GPU wedged; the WindowServer macOS restarts never comes up, the next player cannot open a window, and it can end in a kernel panic. Check the Mac's screen health before every next GPU run; an agent cannot restart a FileVault Mac."
metadata:
  type: project
---

# A Mac GPU hang can wedge WindowServer (w1987, 2026-10-25)

Seen on the m3 (M3 Pro) while bisecting the Just Play bench's Metal hang with `-ffBenchCut`:

- **The frozen player can't exit.** After the GPU hang, the player was killed, but it stayed in `ps` with STAT `?E` and RSS 0. No signal ends it. It holds the GPU.
- **WindowServer doesn't come back.** macOS's userspace watchdog restarts WindowServer (`WindowServer-*.ips`, `*userspace_watchdog_timeout.spin` in `/Library/Logs/DiagnosticReports`). The new one used 0.05 s CPU in 25 minutes and never finished starting.
- **Every later GUI process fails.** A launched player stops at 58 MB, and its log says `Failed to look up the port for "com.apple.windowserver.active" (1102)`. The same happens to a job bootstrapped into `gui/<uid>`. `screencapture -x` prints "could not create image from display" or hangs.
- **It can end in a kernel panic.** A later hang ran from a fresh boot took WindowServer down twice and then panicked the kernel: `userspace watchdog timeout: no successful checkins from WindowServer (2 induced crashes) in 120 seconds`.
- **An agent can't restart the m3.** `sudo` needs a password, `fdesetup isactive` is true, and `autoLoginUser` is unset. The FF Factory daemon runs as the user. A restart therefore needs the person at the machine with their FileVault password. Ask for that once, with this evidence.

## Before every next GPU run on a Mac
1. `pgrep -lx WindowServer`, and check with `ps -o time` that it has CPU time and was not started seconds ago.
2. `ps -axo pid,stat,comm | grep -i finalfactory`: no player may be left, above all one in state E.
3. Ask WindowServer for its window count, under a 10 s bound; it must answer a number:
   `perl -e 'alarm 10; exec @ARGV' osascript -l JavaScript -e 'ObjC.import("CoreGraphics"); ObjC.castRefToObject($.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly, 0)).count'`
   (m3, 2026-11-14: 45, in 2 s; untried on a wedged WindowServer, which is expected to hang or fail it, as it did
   `screencapture`). It reads no pixels and needs no screen-recording permission; a one-pixel
   `screencapture -R` failed there without that permission ("could not create image from rect"). Not a whole-desktop
   `screencapture -x`: it shows the person's other windows, and the worker privacy guard refuses it ("captures the
   whole desktop"; ff-factory docs/privacy.md).

If any check fails, run nothing. The Mac needs a restart by its owner, and a run in that state proves nothing.

## Other lessons from the same runs
- Don't put the word "shutdown" in a Bash command, even a `log show` predicate: a hook refuses it as a restart.
- Use `/usr/bin/log`, since zsh has a `log` builtin.
- macOS has no `timeout` command; use `perl -e 'alarm N; exec @ARGV'`.
