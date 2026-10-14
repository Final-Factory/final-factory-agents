---
name: an-ab-leg-starts-from-a-quiet-machine-of-your-own
description: "A perf A/B leg starts only when nothing of yours is still running: TaskStop on a wrapper does not end the loop scripts or the player it started, your own find or grep burns CPU mid-run, and a doc-rewriting script on Windows must set its newlines. List the processes, kill script and player, then measure."
date: 2026-10-14
---

# An A/B leg starts from a quiet machine of your own

**Rule.** Before an interleaved A/B leg (the perf doc's Method), and again before you trust its numbers, nothing of
yours may still be running.

1. **`TaskStop` on a background `bash` wrapper does not stop what it started.** The loop script
   (`probe_ab_win_switches.sh`) and its `finalfactory.exe` keep running. Worker 28ebd585 (w1258) found two "stopped" loops
   still running 40 minutes later, which made its whole frame A/B unusable; the next worker on BEAST hit it again. Before the
   next leg: `Get-CimInstance Win32_Process` filtered on the script's name, and `Stop-Process` on the script and the player.
2. **Your own searches count.** A `find /` started a few minutes earlier ran three cores at 100% inside the first A/B run.
   Run `ff-leftovers list` first (it names what your session still has running), and read the run's `contention.txt` for the
   other sessions' processes: the loop's quiet gate waits for their players and builds, not for their `find`s.
3. **A script that rewrites a doc on Windows reads and writes explicit newlines.** A worktree with `core.autocrlf` checks the
   perf doc out with CRLF, so `open(p).read()` anchors such as `'## Ranked weak points\n'` do not match. Read with the default
   (universal newlines) and write with `newline=chr(10)`, so the blob stays LF and the diff stays small.

**Why:** w1258, 2026-10-13/14: a Deck-paced A/B contaminated by loops `TaskStop` had "stopped", a first run with my own `find`
in it, and a doc patch script that failed on CRLF.

**How to apply:** the check before every leg is one command pair: `ff-leftovers list` and the process listing for the script.
