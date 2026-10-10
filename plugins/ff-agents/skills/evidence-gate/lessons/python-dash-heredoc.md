---
name: python-dash-heredoc
description: "Never feed a script to `python -` through a heredoc inside eval or bash -c: if the heredoc is lost, Python opens its interactive console and loops on an error, writing a task .output file without limit (99.6 GB on LothDesktop). Run a file, and look at your own task output sizes before DONE."
date: 2026-10-10
---

# `python -` through `eval` can fill a disk

**Rule.** Do not run `python - <<'E' ... E` inside `eval '...'`, `bash -c "..."` or any wrapper that
re-parses the command. Write the script to a file in your temp folder and run `python file.py`
(or `python -c '...'` for one line). Before you report a request done, look for a runaway task
output of your own session: `find "$TEMP/claude" -name '*.output' -size +1G`; a hit means a
process is still writing it, so find and end that process, then delete the file.

**Why.** 2026-10-10 (w876, w899): a worker's Bash command checked the ffdiscord config with
`eval 'python - <<E ... E'`. The heredoc was lost in the eval, so `python -` read the console,
started its interactive REPL (`_pyrepl`) and looped on `OSError: [WinError 123]`, writing the
traceback to the Claude task `.output` file for a day. The file reached 99.6 GB and D: fell from
104 GB to 60 GB free; deleting the file freed nothing until the process (PID 23756, 69,000 CPU
seconds) was ended. The daemon's clean-up now removes such a file and ends its writer when the
session has stopped (ff-factory w899); this lesson is the guard at the source.

**How to apply.** One script per file; no heredoc through `eval`. A Bash call that ends in a
Python traceback repeating is a loop: stop the process before anything else.
