---
name: bash-tool-collapses-double-backslash
description: On the Windows FF Sandbox machines the Bash tool turns `\\` into `\` before bash runs, even inside a quoted heredoc, so code with escapes written through Bash arrives changed
metadata:
  type: project
---

The agent's Bash tool on the Windows sandbox machines (Git Bash; measured on beast, 2026-10-10, w864) collapses
every `\\` in the command text to a single `\` before bash sees it. That includes the body of a quoted heredoc
(`<<'EOF'`), which bash itself would leave alone:

```
cat <<'EOF' | od -c
a\\b
EOF
# prints: a \ b   (one backslash, not two)
```

So a Python or TypeScript edit script fed through a heredoc loses one level of escaping. In w864 it happened four
times: `"\\n".join(...)` became a real line break in ffnightly.py (a syntax error found only when the script ran),
`.join('\\n')` did the same in two .ts files, a sed backreference `\\1` became the byte 0x01, and a Windows path's
`\\f` in a doc became a form feed. A Bash command that only *names* a protected path in old text is refused too, so
editing through Bash also hits the path guard.

**How to apply:** write any content or edit script that holds a backslash with the Write tool (into your temp
folder), then run that file with Bash. Never pass it through a heredoc or a `-c` string. Afterwards, check the edited
files for control bytes (`grep -c $'\x01\|\x0c' <files>`) and parse or compile them (`python -c "import ast; ..."`,
`tsc`, `bash -n`) before trusting the edit.
