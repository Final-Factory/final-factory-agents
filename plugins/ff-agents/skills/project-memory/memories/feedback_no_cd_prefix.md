---
name: feedback-no-cd-prefix
description: "Don't prefix Bash commands with `cd` into the working directory — it triggers approval prompts"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b051a5c7-74e4-4c81-a087-97d3a15d513f
---

Do not prefix Bash/PowerShell commands with `cd "D:/work/FinalFactory"` (or any `cd`/`Set-Location` into the current working directory). The tool's working directory is already the project root, and on Windows a `cd` into an absolute path triggers a permission approval prompt every time. Use relative or absolute paths directly instead.

**Why:** The `cd` is redundant and each one forces the user to approve a command. Removing it eliminates needless approvals.

**How to apply:** Write the actual command on its own (e.g. `git status --short`, not `cd "D:/work/FinalFactory"; git status --short`). For paths, pass them directly to the command. Only `cd` when genuinely moving into a *subdirectory* the command can't address via path. Related: [[feedback-test-command]].
