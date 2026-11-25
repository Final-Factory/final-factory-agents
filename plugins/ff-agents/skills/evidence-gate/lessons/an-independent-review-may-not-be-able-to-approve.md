# An independent review cannot approve a PR its token's account opened

**Rule** (w5852, from w5851, 2026-11-25): before an independent or lockout review posts, compare
`gh api user -q .login` with `gh pr view <n> --json author -q .author.login`. If they match, GitHub
refuses `gh pr review --approve` ("Can not approve your own pull request"), so post the verdict with
`gh pr review <n> --comment --body-file <file>`, with `PASS` or `FAIL` in its first line, and say in the
body that it is a comment review, not an approval, because the token's account opened the PR. If they
differ, `--approve` (or `--request-changes`) works as before.

**Why:** w5851, the independent lockout review of ff-factory PR #1280, ran with the vault token of the
person the work is for, the same account that opened the PR. `--approve` failed, and the verdict went up as
a COMMENTED review headed "PASS"
(https://github.com/Final-Factory/ff-factory/pull/1280#pullrequestreview-6066532694). Workers' PRs and
reviews often share one account, so this is the normal case, not an edge.

**What counts as the independent review:** the reviewer is a different worker (session) from the
author. The account does not matter. An author's merge gate therefore accepts either a GitHub APPROVED
review or a `PASS` comment review from a different worker. A gate that demands APPROVED can never be met
here. Checked 2026-11-25: no skill, checklist or script in final-factory-agents, and none in ff-factory
(`rg "APPROVED|reviewDecision|--approve"`; `ff-pr` reads CI only), expects an APPROVED state, so nothing needed
changing.
