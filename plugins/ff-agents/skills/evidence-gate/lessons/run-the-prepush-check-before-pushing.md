---
name: run-the-prepush-check-before-pushing
description: "On ff-factory, run npm run prepush before every push and push only when it passes; a SKIPPED step is reported, not ignored."
date: 2026-10-10
---

# Run the pre-push check before you push (ff-factory)

**Rule.** In a Final-Factory/ff-factory checkout, run `npm run prepush` before every push, and push only when it
passes. It runs the typecheck, shellcheck on the VM scripts (`deploy/vm/test/lint.sh --shellcheck-only`), gitleaks on
`origin/main..HEAD` and the noreply identity check on `origin/main..HEAD`. A `!!!!!!!! <step>: SKIPPED` line means that
tool (shellcheck, gitleaks, or bash on Windows) is missing on the machine: say so in your report; CI still runs it.

**Why.** lothsahn, 2026-10-10, w924: "yes, have the workers do #1", on w922's measurement. From 2026-09-26 to 10-10,
ff-factory's lint, secret-scan and identity rules failed CI 77 times (shellcheck 14, gitleaks 11, every one a fake key
in a test or doc, identity 52) and held up 23 merged PRs. Each of them shows up in about 13 s locally (measured on
biscuit) instead of a CI round trip and a re-push.

**How to apply.** Before `git push` in ff-factory: `npm run prepush`. Fix what it names, commit, run it again. The
repo's own `CLAUDE.md` carries the same rule; `docs/ci.md` ("Before you push") says what each step runs. There is no
git hook on purpose: a sandbox is a worktree, and a hook would land in the hooks folder every worktree shares.
