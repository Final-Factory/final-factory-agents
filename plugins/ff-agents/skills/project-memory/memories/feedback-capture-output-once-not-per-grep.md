---
name: feedback-capture-output-once-not-per-grep
description: "Never re-run a slow command to see a different slice of its output — redirect it once to a scratch file in the working directory, grep that file, then delete it"
metadata:
  type: feedback
---

When a command's output is long enough to need filtering — a test suite, a build, an audit
script, a batchmode run — run it ONCE with `> ffwork-<task>.txt 2>&1` and then grep, tail and
re-read that file as many ways as needed. Never pipe the live run through `grep`/`head` and then
run the whole thing again to see the part the filter threw away.

**Why:** Lothsahn caught me running `ffbox/test_ffwatch.py` ten times in a single task on
2026-09-02. Two runs were real, one per change. The other eight existed only to view different
slices of identical output: the `✗` lines, then one test's checks, then the check the `-A9`
window cut off, then the summary line. Twice the suite ran twice inside one command, the second
run purely to recover the tail the first one's grep had discarded. It burns wall-clock, and on a
shared box it burns the CPU other sessions are waiting on.

**How to apply:** put the scratch file in the WORKING DIRECTORY you were given, under a name
unique to this task, and `rm` it as soon as you are done reading it. Several agents run on these
machines as the SAME user, so a fixed shared path like `/tmp/out.txt` is not yours — another
session truncates it under you, or you read their run and report on it as your own (same hazard
as the shared state in [[machine-global-state-multi-session]], and the reason the ffbox box has
sibling checkouts `-2`/`-3` in use at once). Deleting it is not tidiness: a session that ends in
`git add -A` will commit whatever is lying around, so check `git status --short` before staging.
And read the verdict out of the FILE, not from `$?` after a pipeline — `cmd | grep x | head`
reports `head`'s status, so `echo $?` says 0 however the command actually ended
([[shell-tee-pipestatus]] is the same trap with `tee`).
