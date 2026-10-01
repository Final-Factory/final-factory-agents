---
description: Once a branch is pushed, bring develop in with a merge; a rebase needs a force-push, which is forbidden. Two shell traps from the same session.
---

# After the branch is pushed, merge develop in; do not rebase

From w161 (2026-10-01). The sandbox rule is "fetch, rebase, push", and force-pushing is forbidden everywhere.
Those collide the moment a feature branch has been pushed: rebasing it again onto a newer `origin/develop`
rewrites the pushed commits and the push is rejected as non-fast-forward.

- Rebase freely BEFORE the first push of the branch. After it, `git merge origin/develop` and push.
- If you already rebased: `git reset --hard ORIG_HEAD` (check `git reflog` first) restores the pushed history,
  then merge.
- A merged PR that added an `ffauto` command conflicts in `CommandTiersTest`'s golden and in the generated
  `docs/ffauto-command-reference.md`. Take develop's version of both, run `python
  scripts/generate-ffauto-reference.py`, recompile, read `CommandCatalogHash.Compute()` / `ComputeHex()` in the
  editor, and write the new golden with a dated comment line.

Two shell traps on Windows Git Bash in the agent's Bash tool:

- A heredoc whose body contains an apostrophe fails with `unexpected EOF while looking for matching` even
  with a quoted delimiter. Write the script with the Write tool and run the file.
- `echo x >> .git/info/exclude` in a worktree fails (`.git` is a file) and a fallback to
  `git rev-parse --git-path info/exclude` writes the SHARED base repo's exclude. Remove the line when done.
