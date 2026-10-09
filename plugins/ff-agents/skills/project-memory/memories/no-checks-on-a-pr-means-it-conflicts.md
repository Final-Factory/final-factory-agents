---
name: no-checks-on-a-pr-means-it-conflicts
description: "A pull request that shows \"no checks reported\" minutes after it opened usually conflicts with its base: GitHub starts no pull_request workflow while it cannot make the merge commit. Check mergeable, merge the base in, push, and the checks start."
---

# No checks on a PR means it conflicts

**Trap.** `gh pr checks <n>` answers "no checks reported on the '<branch>' branch" and stays that way: GitHub runs a
`pull_request` workflow on the PR's test merge commit, and makes none while the PR conflicts with its base. Nothing
says so on the checks tab.

**Seen.** 2026-10-09 (w741): ff-factory #242 had no runs while two other PRs of that repo ran CI;
`gh pr view 242 --json mergeable,mergeStateStatus` read `CONFLICTING DIRTY` (main had moved: a CHANGELOG
"Unreleased" entry on both sides). After `git merge origin/main`, the conflict resolved and a push, all eight checks started.

**How to apply.** When a PR has no checks a few minutes after a push, ask
`gh pr view <n> -R <repo> --json mergeable,mergeStateStatus` first. `CONFLICTING`: merge the base into the branch
(never rebase a pushed branch, never force-push), keep both sides of an append-only file such as CHANGELOG, re-run the
tests, push. `UNKNOWN` right after a push is GitHub still computing; ask again.
