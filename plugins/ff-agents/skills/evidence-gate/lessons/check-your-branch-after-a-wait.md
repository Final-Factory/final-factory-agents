---
name: check-your-branch-after-a-wait
description: "After any long wait (wake_me, waiting on a person, a background build) a sandbox can have been switched to another worker's branch. Run `git branch --show-current` before the first git command that writes, and `switch_branch` back; never merge or commit first."
date: 2026-10-10
---

# Check your branch after a wait

**Rule.** Your sandbox's worktree is shared across requests: while you wait, FF Factory can give it to
another worker, who leaves it on their branch. After any wait of more than a few minutes (a `wake_me`, a
declared person wait, a long build), the first command that writes to git (a merge, a commit, a push, a
reset) is preceded by `git branch --show-current`. It must be your branch (`sandbox/<slot>-wNNN`). If it is
not, do not write: `mcp__machine__switch_branch` back to your branch (the editor must be stopped).

**Why.** 2026-10-10 (w807): after a night of waiting on Ben's approval, `git merge origin/develop` ran on
`ffbox-f/w817-supply-bots-cache-drift`, another worker's branch, because slot2 had been moved there at
19:04. The reflog showed it (`checkout: moving from sandbox/slot2-w807 to ffbox-f/w817-...`), and the
merge was reset to the branch's own tip (`fd7ae757d`) before anything was pushed. What gave it away was
that `Assets/Scripts/UI/HotbarRadial/` did not exist.

**How to apply.**

- First write after a wait: `git branch --show-current` (and `git reflog -5` if it is not yours).
- A merge you made on the wrong branch and never pushed is undone with `git reset --hard <the tip before
  your merge>` after `git status` shows a clean tree and the editor is stopped; check the reflog for what
  that tip was. Never undo anything pushed.
- The worker whose branch it was is not told by the reset: say in your report that you touched it and that
  it is back where it was.
