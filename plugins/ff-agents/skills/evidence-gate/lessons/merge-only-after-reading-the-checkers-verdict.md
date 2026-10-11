---
name: merge-only-after-reading-the-checkers-verdict
description: "Never merge in the same shell command as pr_evidence.py: run the checker, read its first line, and merge only on PASS from the released version. A FAIL that says a newer ff-agents is released is not a pass: update the plugin and run it again."
date: 2026-10-11
---

# Merge only after reading the checker's verdict

**Rule.** `pr_evidence.py` and `gh pr merge` are two commands in two tool calls. Run the checker, read its
first line, and merge only when it says `PASS` and names the released ff-agents version. A shell
line or script that runs both (`;`, a newline, `&&` with the checker's output piped away) merges on a FAIL.

**Why (w978, 2026-10-11).** The PR was green on CI and the checker had passed days earlier. At merge time I ran
`python pr_evidence.py ...; gh pr merge ...` as one command. The checker printed
`evidence-gate: FAIL ... this pr_evidence.py is ff-agents 1.26.24, but 1.26.27 is released: its rules are older than the team's`
and the merge ran anyway. The newer checker then asked for a `Window overlaps:` line (w981), which the PR lacked: the
orchestrator had asked for that exact overlap check before the merge. The line was added to the merged PR afterwards.

**How to apply.**
1. Update first when the plugin is behind (`claude plugin marketplace update final-factory-agents`, then update
   ff-agents), or run the newest copy under `~/.claude/plugins/marketplaces/final-factory-agents/`.
2. Run the checker alone, with `--brief`. A FAIL for a missing line is fixed in the PR body, then run again.
3. Merge in its own call, after you have read `PASS`.
