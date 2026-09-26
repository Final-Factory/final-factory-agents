---
name: feedback-back-up-then-clear-bens-clone
description: Ben 2026-09-25, standing permission — on his own Macs (m5, m3, his main Final Factory clone) agents may stash/restore/reset/clean local changes to update the clone WITHOUT asking, as long as they first copy them to ~/nevergames/ff-local-backups/<time>/ and report what they moved; still never force-push, push to master/main, or stage/commit everything
metadata:
  type: feedback
---

**Rule (Ben, 2026-09-25, standing permission):** "you always have my permission to do that, Claude has
done that 1000 times this year. Stop asking for basic shit like that."

On Ben's own machines (m5, m3: his MAIN Final Factory clone, e.g. `~/nevergames/FinalFactory`), an
agent that needs to update the clone (pull, rebase, switch branch) MAY set aside or discard local
changes, **without asking Ben**:

- `git stash` (and pop/drop), `git restore <paths>`, `git checkout -- <paths>` / `git checkout .`
- `git reset` of files, or `git reset --hard`
- `git clean` of untracked files
- a forced (`-f`) or dirty-tree branch switch

**Condition: back up FIRST, then report.** Before any of those, copy everything they could lose to a
fresh timestamped folder OUTSIDE the repo, beside the clone: `~/nevergames/ff-local-backups/<YYYYMMDD-HHMMSS>/`.
From the clone:

```sh
b=~/nevergames/ff-local-backups/$(date +%Y%m%d-%H%M%S); mkdir -p "$b"
git diff > "$b/unstaged.patch"; git diff --cached > "$b/staged.patch"
git ls-files -z -m -o --exclude-standard | rsync -a --from0 --files-from=- ./ "$b/files/"
git stash list > "$b/stash-list.txt"
```

Then do the update, and say in your report exactly what you moved (files, patches, stash entries) and
the backup path, so Ben can restore anything.

**Still forbidden** (unchanged): force pushes; pushes to the game repo's master/main; staging or
committing everything (`git add -A` / `add .` / `commit -a`: stage and commit only your own files,
by path). Ben's uncommitted work must never end up in an agent's commit.

**Why:** asking Ben each time for a routine clone update was pure friction; he has approved it
countless times. The backup is what makes it safe: nothing is lost, only moved aside.

**How to apply:** do it, don't ask. The FF Factory machine guard (`checkOwnCheckout` in the ff-factory
repo, `server/guard.ts`, 49bd8c6+) enforces the backup: it refuses those commands until a backup folder
from the last 2 hours exists under `ff-local-backups/` beside the clone, and its refusal prints the
recipe above. On BEAST, work goes through ffsb sandboxes instead ([[feedback-beast-work-goes-through-a-sandbox]]);
restarting Unity on Ben's machines is covered by [[feedback-restart-unity-on-your-own-authority]].
