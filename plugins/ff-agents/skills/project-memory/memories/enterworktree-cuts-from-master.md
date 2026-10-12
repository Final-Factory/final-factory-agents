---
name: enterworktree-cuts-from-master
description: Claude Code's EnterWorktree branches from origin/master by default, which since w1137 (2026-10-12, develop retired) is the right base; before it, Final Factory integrated on develop and a fresh worktree lacked every in-flight spec's files
metadata:
  type: project
---

Claude Code's `EnterWorktree` (`worktree.baseRef=fresh`, the default) branches from
`origin/<default branch>` = `origin/MASTER` for this repo. **Since w1137 (2026-10-12) master is the one
trunk and develop is retired, so that default is right: no reset needed.** (History: until then Final
Factory integrated on `develop`, so a fresh worktree lacked every in-flight spec's files, the 055
ability-op tests did not exist there on 2026-09-02, and the first command was `git reset --hard
origin/develop`. A worktree or sandbox branch cut from the old develop merges `origin/master` in
instead: merge, never rebase a pushed branch.)

**How to apply:** `git fetch origin`, then `git log -1 origin/master` to know the tip you start from. The
worktree has no `Library/`, so compile verification happens in the main checkout's editor after a
fast-forward merge of the worktree branch into master (through a pull request: master takes no direct
push); the worktree sandbox refuses heredoc/python edit scripts, so use the Edit tool there.
