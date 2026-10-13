---
name: agent-shell-eats-backslashes-in-inline-python
description: "A Bash-tool heredoc of inline Python loses backslashes: '\\n' and '\\\"' in the Python source arrive as real newlines and bare quotes, which broke C#, bash and JSON edits three times in w1227; write such text with the Write or Edit tool"
metadata:
  node_type: memory
  type: project
  modified: 2026-10-13T20:00:00Z
---

**Lesson (w1227, 2026-10-13, Windows sandbox, Git Bash through the agent's Bash tool).** A `python - <<'EOF'` that
edits a source file and contains `\n`, `\r`, `\"` or `\\` inside its string literals does not reach Python as written:
the tool collapses the backslash escapes first. Three edits in one session paid for it:
`Split('\r', '\n')` in a C# file became a char literal split over two lines (`error CS1010` after a 4-minute editor
compile), `return "\n" + ...` likewise, and a bash `... \<newline> -executeMethod` continuation joined into one line.

- Put any text with backslashes in a file with the **Write** tool or change it with **Edit**; use a heredoc Python only
  for text with none (check with `grep -n '\\\\' <your script>` before running it).
- After any scripted edit of a `.cs` or `.sh` file, `git diff` it and read the changed lines once; an editor compile
  costs minutes, a `git diff` costs a second.
- Same family: `git show origin/branch:path/with/slashes` through Git Bash needs `MSYS_NO_PATHCONV=1` or MSYS rewrites
  the `branch:path` argument as a Windows path ("ambiguous argument"). Files read as bytes keep their line endings: an
  edit script must detect CRLF vs LF (`'\r\n' in raw`) and write back the same, or the diff is the whole file.
- A new branch can only be pushed from a clone whose commits touch no `.github/workflows/*` file unless the token has the
  `workflow` scope ([[a-workflow-file-push-needs-the-workflow-scope]]); cut pull-request branches with a temporary index
  (`GIT_INDEX_FILE`, `git read-tree origin/master`, `git diff <commit>^ <commit> | git apply --cached --3way`,
  `git commit-tree`) so the worktree and its history stay untouched.
