---
name: git-bash-running-script-edits-and-slash-args
description: On the Windows FF machines (Git Bash) editing a bash script while a run of it is going breaks that run, and an argument that starts with "/" is rewritten into a Windows path
metadata:
  type: project
---

Two Git Bash traps that cost w1217 (beast, 2026-10-13) a settings restore and a wrong measurement:

1. **Never edit a bash script while a run of it is going.** Bash reads a script file as it runs it, not all at once.
   w1217 added two cases to its leg runner while a four-leg run was in its last leg; when the leg ended, bash read the
   shifted bytes ("syntax error near unexpected token `)'") and stopped before the script's last line, the
   `python scripts/game_data.py restore` of the machine's game settings, so the machine kept the test's settings until
   it was restored by hand. **How to apply:** run a copy per run (`cp run_legs.sh run_legs-b.sh && bash run_legs-b.sh ...`)
   and edit only the original; or put the restore in a `trap ... EXIT`.

2. **An argument that starts with "/" is a path to MSYS.** Git Bash rewrites it into a Windows path before the program
   sees it: a census path fragment `"/InventoryPanel"` passed to a Python script arrived as
   `C:/Program Files/Git/InventoryPanel`, matched nothing, and the script printed "-" for every census, which read as
   "the window is not on screen". **How to apply:** drop the leading slash (`PanelShowcase/InventoryPanel`), or run the
   command with `MSYS_NO_PATHCONV=1`; when a filter matches nothing, print the argument the program received before
   believing the result.

Related: [[bash-tool-collapses-double-backslash]], [[delegated-implementors-on-ff-sandboxes]].
