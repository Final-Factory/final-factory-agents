---
name: sandbox-branch-after-rebase-without-force
description: After rebasing a sandbox branch onto develop, its remote copy can no longer fast-forward and force-push is forbidden; push a tree-equal merge made with git commit-tree to the branch ref instead. Also, git add <dir> in a shared sandbox sweeps in other agents' untracked files.
---

# Keep a sandbox branch pushable after a rebase, without force

The sandbox rule is: rebase onto `origin/develop`, `git push origin HEAD:develop`, and also push
your own branch. Once the branch was pushed before the rebase, the second push is rejected as
non-fast-forward, and force-pushing is forbidden everywhere.

Keep the remote branch fast-forward with a merge whose tree is exactly your rebased HEAD, built
without touching your local branch:

```sh
M=$(git commit-tree 'HEAD^{tree}' -p HEAD -p origin/<branch> -m "Keep <branch> fast-forward over its pre-rebase history")
git diff --quiet HEAD "$M" && git push origin "$M:refs/heads/<branch>"
```

Develop still gets the linear rebased commits from `git push origin HEAD:develop`. Every later branch
push needs a fresh merge the same way, because your local branch never contains `$M`. Used for every
branch push after the rebases in 087 (2026-09-28).

Proofs and docs that cite commit hashes cite the pre-rebase ones, and most of those were never pushed.
Map them to the rebased hashes by subject (`git log --format='%h %s' <old-base>..ORIG_HEAD` against the
new range) before landing.

## `git add <dir>` sweeps other agents' files

A sandbox worktree can hold other agents' untracked work. `git add specs` in 087 staged a whole
`specs/u7-plasma-bolt-spawn/` proofs folder and a 074 screenshot. Stage explicit paths, and read
`git show --stat HEAD` before every push. An unpushed commit can be undone with
`git reset --soft HEAD~1` and `git restore --staged <foreign paths>`, which leaves the files untracked.

Related: [[feedback-beast-work-goes-through-a-sandbox]].
