---
name: enterworktree-cuts-from-master-not-develop
description: Claude Code's EnterWorktree branches from origin/master by default, but Final Factory integrates on develop — a fresh worktree is missing every in-flight spec's files
metadata:
  type: project
---

Claude Code's `EnterWorktree` (`worktree.baseRef=fresh`, the default) branches from
`origin/<default branch>` = `origin/MASTER` for this repo, but Final Factory integrates on
`develop` — a fresh worktree lacks every in-flight spec's files (the 055 ability-op tests
did not exist there on 2026-09-02) and a commit made on it would rebase onto master.

**How to apply:** first command in any new worktree: `git reset --hard origin/develop` (or
the exact develop tip you mean), then verify with `git log -1`. Also: the worktree has no
`Library/`, so compile verification happens in the main checkout's editor after a
fast-forward merge of the worktree branch into develop; the worktree sandbox refuses
heredoc/python edit scripts — use the Edit tool there.
