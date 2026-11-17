---
name: a-failed-call-changes-its-form-before-it-runs-again
description: "When a tool call fails, read the error, name its cause, and change the call before you run it again; a second identical call is only for a transient you can name. Known traps are in project-memory agent-shell-traps-by-machine and editor-ops 'A Unity call failed'. From w4501's 8-hour transcript analysis (lothsahn, 2026-11-17)."
date: 2026-11-17
---

# A failed call changes its form before it runs again

**Rule.** When a tool call fails, read the error before the next call, say to yourself what caused it, and change the
call: quote the glob, write the inline script to a file, look the type's namespace up, wait for the bridge. Run the same
call again unchanged only for a transient you can name (a domain reload's sub-second drop, a portal link that dropped),
and then after the wait that clears it. Before you write a form that failed for someone else, look in the two places
the known traps are kept: project-memory
[agent-shell-traps-by-machine](../../project-memory/memories/agent-shell-traps-by-machine.md) (the shell) and
editor-ops, "A Unity call failed" (the editor).

**Why.** lothsahn, 2026-11-17 (w4495, w4501): "Analyze all the tool calls in the last 8 hours and look for failures.
Group the failures and look at how you can fix the skills to prevent future failures". w4501 read every agent's
transcript for 00:00 to 08:00 UTC (measured, report on w4501):

- about 49 unintended Bash exits: 21 inline-Python tracebacks, 9 shell syntax and quoting errors, 6 missing modules or
  tools, 3 `gh pr edit` failures. Every one is a trap already written in a skill or memory that the agent had not opened;
- about 36 Unity calls sent before the bridge was up, after a start, a compile or a reload, 1 to 3 failed calls each
  before the agent waited;
- about 13 `execute_code` snippets that failed to compile on a short type name. One session (w4481, two-peer checks)
  failed four times in nine minutes, one missing namespace at a time;
- the same `grep --include=*.cs` refused by zsh twice in one session (w4521), and one `rm -rf` of a `$VAR` path denied
  four times in a row (w4494) until the paths were written out.

Each failed call re-reads the whole context (about 345k tokens a call, measured in the worker prompt), so a repeated
failure costs as much as a useful step.

**How to apply.**

1. On a failure, the next call is a different call: the fix for the error you read, or a read that tells you the cause
   (the editor log, `jq 'keys'` on the JSON, the type's `namespace` line).
2. After a start, a compile or a reload, wait for readiness in one `until` loop before the next Unity call (editor-ops,
   "A Unity call failed"). On a `refresh_unity` 60 s timeout, poll; do not call it again.
3. A trap you hit twice, or one not in the two notes above, goes into them before DONE (checklist
   [done](../checklists/done.md) item 11).
