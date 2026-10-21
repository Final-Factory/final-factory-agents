---
name: shell-tee-pipestatus
description: "cmd | tee log || true" clobbers PIPESTATUS so the exit code is always 0 — an audit script that does this cannot detect its own command's failure
metadata:
  type: project
---

`some_command | tee "$log" || true` always evaluates to exit code 0: `||` applies to the whole
pipeline's exit status, and without `pipefail` that status is `tee`'s (which basically always
succeeds), not `some_command`'s. A script using this pattern to "log while tolerating failure"
instead silently swallows every failure of `some_command` — the caller sees success no matter
what happened. Confirmed as a real anti-pattern in this codebase's own audit tooling:
`scripts/audit/test_determinism_audit_lib.sh:492,512` names and tests for it directly.

**How to apply:** wrap the pipe in `set +e` / `set -e` (or `set -o pipefail` scoped to just that
line) instead of appending `|| true` to a `| tee` pipeline — capture the real command's exit
status explicitly (`PIPESTATUS[0]` in bash) before deciding whether to tolerate the failure.

A related trap: `producer | grep -q pattern` can make `grep` exit as soon as it sees a match.
On a large producer, that closes the pipe and the producer may report `SIGPIPE`, so `pipefail`
turns a successful search into a failed pipeline. When the producer's completion matters, consume
all lines (for example, `grep pattern >/dev/null`) instead of using `grep -q`.

**A pipe also hides a failed `git merge`** (w1530, 2026-10-21): `git merge --no-edit origin/master 2>&1 | tail -1 && git push ...` pushed the branch while the merge sat conflicted in `main.unity`, because the pipeline's status is `tail`'s. Never pipe `git merge` (or `git pull`) into `tail`/`head` before `&&`: run it unpiped, or with `set -o pipefail`, and check `git status --short | grep '^UU'` is empty before any push.
