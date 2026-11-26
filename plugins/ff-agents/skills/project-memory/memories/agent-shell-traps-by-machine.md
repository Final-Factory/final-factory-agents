# Shell traps by machine: what failed in the agents' Bash tool, and the form that works

w4501 (2026-11-17, lothsahn's tool-call failure analysis) read every agent's transcript for 00:00 to 08:00 UTC: 107
Bash calls exited non-zero, about 49 of them unintended (measured; the split from truncated snippets is a judgement).
Nearly all of those are one of the traps below, each already written down somewhere a failing agent had not opened.

| Trap | Where | Failed form (sample) | Works |
|---|---|---|---|
| Inline `python3 -c` / heredoc Python (21 tracebacks or syntax errors) | every machine | nested quotes in `python -c`; `d['items']` on JSON of another shape (KeyError, w4207); `im.crop` outside the image | write the script with the Write tool to `$TMPDIR/<name>.py` and run it; print a tool's JSON keys (`jq 'keys'`) before indexing; clamp crop boxes to the image size. Backslashes: [agent-shell-eats-backslashes-in-inline-python](agent-shell-eats-backslashes-in-inline-python.md) |
| zsh globs | macOS (m3, m5): the Bash tool is zsh | `grep -rn x --include=*.cs` → `(eval):1: no matches found: --include=*.cs` (w4521 ran it twice; w4501 itself once) | quote it: `--include='*.cs'`, or `rg -g '*.cs'` |
| zsh word splitting and modifiers | macOS | `set -- $leg` does not split; `$REF:A` is a path modifier | [built-pair-lab-traps-2026-09-18](built-pair-lab-traps-2026-09-18.md); put loops in a bash script in `$TMPDIR` |
| Multi-line `bash -c` / `eval` quoting (4) | Git Bash and Linux | `unexpected EOF while looking for matching ''`; `syntax error near unexpected token '('` | a script file in `$TMPDIR` (the worker prompt's "Shell steps" rule) |
| BSD sed | macOS | `sed -i 's/a/b/' f` or a GNU-only flag → `illegal option` | `sed -i '' ...`, or Edit, or a Python script file |
| Missing Python modules and tools (6) | biscuit (Linux): no ffmpeg, no Pillow; m5 and lothdesktop: no Pillow in the system python; Windows Git Bash: no `pwsh` on PATH | `ModuleNotFoundError: PIL` / `imageio_ffmpeg`; `ffmpeg: command not found`; `which: no pwsh` | `uv run -q --no-project --with pillow --with imageio-ffmpeg python3 <script>` (ffmpeg from `imageio_ffmpeg.get_ffmpeg_exe()`); on Windows call `powershell.exe` |
| `gh pr edit --body-file` (3; again in w5728) | FinalFactory, ffu | exits 1 on the Projects (classic) GraphQL deprecation | `gh api -X PATCH repos/<o>/<r>/pulls/<n> -F body=@<file>`: [gh-pr-edit-fails-on-projects-classic](gh-pr-edit-fails-on-projects-classic.md) |
| A relative output path to a script that `cd`s into the repo (w5728) | every machine | `cd <repo> && python3 scripts/x.py --out results.json` wrote into the repo's folder or nowhere you looked | pass an absolute path (`"$TMPDIR/results.json"`) |
| `pkill -f <pattern>` with the pattern in its own command line (w5728, exit 144) | Linux, macOS | the Bash tool's own shell matches the pattern and is killed (also `pgrep -f` waits that never end: unity-ui, ffu-build-test) | `pgrep -f '[p]attern'` (bracket a letter) and kill the pids it lists, minus `$$`; or end it by a pid file |
| A bare `sleep N; ...` (7) | every machine | Claude Code refuses it: `Blocked: sleep 90 followed by: ...` | one `until <done>; do sleep 20; done` call, or `run_in_background` |
| `rm -rf "$TMPDIR/$X"` or a glob (4 in one session) | every machine | asks a person, so the call is denied | every path written out: [clean-up-after-yourself](../../evidence-gate/lessons/clean-up-after-yourself.md) |

The rule under all of them: when a call fails, read the error and change the form; a second identical call is only for a
transient you can name (a bridge reload). The Unity-side messages and their next steps are in editor-ops, "A Unity call
failed".
