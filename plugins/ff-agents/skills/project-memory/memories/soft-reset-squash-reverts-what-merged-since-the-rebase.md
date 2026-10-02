---
description: Squashing with `git reset --soft origin/develop` after develop moved makes one commit that also REVERTS everything merged since your rebase. Reset to the base you rebased on, then rebase; read `git show --stat` before pushing.
---

# A soft-reset squash reverts whatever merged since your rebase (w170, 2026-10-01)

**What happened.** The branch was rebased on develop at `aa413cf06`. Minutes later, with #888 merged
meanwhile and the ref already fetched, `git reset --soft origin/develop && git commit` produced a
"squashed" commit whose parent was the NEW develop and whose tree was the OLD base plus the change. Its
diff reverted all of #888 (localization tables, three ops). It was pushed to a fresh branch before the
stat was read; it never reached a PR.

**Rule.** Squash against the commit the branch is actually based on, then rebase:

```sh
git reset --soft "$(git merge-base HEAD origin/develop)" && git commit -F msg
git fetch origin && git rebase origin/develop
git show --stat HEAD     # only your files, or stop
```

**Recovery without force-push.** `git reset --soft <true base>`, commit, rebase, and push to a NEW
branch name. Sandboxes cannot delete remote branches, so say which leftover branch must be deleted.
Related: [[sandbox-branch-after-rebase-without-force]].
