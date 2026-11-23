# A red leg that swaps files in the sandbox can be saved as a commit that undoes the fix

**The rule.** Run a red leg (the new test on the code before the fix) so the sandbox never holds master's files while you
are away: put the swap and the restore in one script with `trap 'cp "$OUT"/*.fix ...' EXIT`, or better, give the test
master's behaviour without touching the fix files. When you take over a branch, or `ff-pr push` says non-fast-forward,
read `git log HEAD..origin/<branch>` and `git diff --stat HEAD...origin/<branch>` before you merge anything in.

**Why** (w5177, 2026-11-23). The first worker's batch job swapped `GridEnergySettlementSystem.cs` and
`StationGridCalculationSystem.cs` to master's version for its red leg. FF Factory moved the request to another machine
while that job ran, and saved the sandbox's uncommitted work as `a83fae7219` "FF Factory: saved the uncommitted work
left in lothdesktop/slot5 (w2358)": master's two files, which would have undone the fix. The next worker's push was
refused as non-fast-forward; an ordinary merge of the remote would have shipped PR #4206 without its fix while its tests
still compiled.

**How to apply.** A remote commit that only reverts your fix files is dropped with `git merge -s ours
origin/<branch>` and a message naming it (never a force-push, never a rebase), then `grep` the fix files for the change
and `git diff --stat <your last verified commit> HEAD` (empty) before you push.
