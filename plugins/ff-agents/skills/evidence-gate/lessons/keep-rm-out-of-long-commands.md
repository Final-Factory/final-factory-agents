---
name: keep-rm-out-of-long-commands
description: "A deletion chained into a long Bash command can stop the whole command on a permission prompt that nobody is watching. In bypass mode only Claude Code's dangerous-rm check asks (an rm of $VAR with a glob or brace list, or a critical path); functions, loops, several lines, copies into LocalLow and script runs never do (measured, w1097). Give each run a fresh folder, put multi-step test logic in a script file in $TMPDIR, back up the game's settings and saves with scripts/game_data.py."
date: 2026-10-02
---

# Keep rm out of long commands

**Rule.** Never chain `rm` into a command that then does real work or waits. Delete in a short
command of its own, or don't delete: write to a new, uniquely named folder and overwrite files
in place.

**Why.** Late September and early October 2026, in FF Factory sandboxes. Claude Code can ask for
permission on a destructive shell command (a delete with a wildcard, `-rf`, a path outside the
working folder), and the whole compound command waits with it. Nobody watches a worker's
terminal, so it waits until a person happens to open the sandbox panel. Ben's orchestrator
reported several workers stuck this way for 15 to 90 minutes. The "waiting for permission"
notices in the orchestrators' transcripts show the shape each time, a clean-up glued to the real
work:

- `cd ... && cp ... && rm -f clips/*; ... python take.py ...` (w63, clip recording)
- `L=.../look && rm -f $L/*.jpg && ... python strip.py ...` (w194, frame strips)
- `... && rm -f $N/*.txt && for pair in ...` (w165, proof numbers)
- a wait loop that ended in `[ -f $D/done.txt ] && rm -f $D/*.txt && ...`
- `du -sh ...; rm -rf slot-5/Builds/w157-fix ...` (w157, build clean-up)

**How to apply.**

- Make the output folder new each run (`out/run-$(date +%H%M%S)`), so there is nothing to clear.
- Let tools overwrite: `ffmpeg -y`, a file opened for writing. That needs no delete.
- When a delete is needed, run it alone and first. If it prompts, you learn in seconds, and
  nothing else is held up behind it.
- Scratch in your temp folder needs no clean-up for the run to continue; the harness removes it
  after the session (w913: workers do not clean up). A delete under `$TMPDIR` that is needed mid-task gets no prompt.
- If a command has not returned and you cannot tell why, a prompt is one of the likelier causes.
  Say in your report that you may be waiting on one.

**What asks, measured (w1097, 2026-10-12).** lothsahn: "I just got prompted to accept a bash prompt in w1079. Why did it
do that, and how do we allow it to do what it just needed to do without a complex bash prompt?" w1079's worker had sent one
multi-line command: a `rm -rf` of its last run's folders in `$TMPDIR`, a shell function with a `cp` retry loop restoring
the game's `settings.json`, its test-leg script, a grep of the result. Claude Code 2.1.284 was driven through a stand-in
Messages API with the exact commands (FF Factory `docs/self-recovery.md`, "Routine test steps without a prompt"): in
bypass mode, where workers run, a function, a loop, several lines, `&&`, a pipe, a heredoc, `$(...)`, a `cp` into
`LocalLow`, `bash "$TMPDIR/leg.sh"` and `python scripts/game_data.py ...` never ask. Only its dangerous-rm check does:
`rm -rf $TMPDIR/{a,b}`, `rm -f $TMPDIR/*.log` (a `$VAR` with a glob or a brace list), `rm -rf /x` or `C:/x` (a critical
path). Plain `rm -rf "$TMPDIR/f1920"` does not. FF Factory now answers such a prompt itself when every delete in the
command is written out under `$TMPDIR` (after the portal deploy that carries w1097), but the routes below never ask at all:

- Give each run a new folder: `mktemp -d "$TMPDIR/leg-XXXX"`, or `$TMPDIR/leg-1920-2`. Nothing to delete.
- Put multi-step test logic in a script file in `$TMPDIR`, written with the Write tool, and run `bash "$TMPDIR/leg.sh" 1920`.
- Back up and restore the game's settings and saves with the game repo's `python scripts/game_data.py`
  (`snapshot`, `restore`, `run --name <leg> -- <command>`, `get <key> --name <leg> --after`), not a `cp` loop into
  `LocalLow`. It writes only `UserData/settings/settings.json`, `LocalSettings/settings.json` and the saves you name.
- The w913 rule above already said "do not clean up"; w1079's worker did not count a rerun's output folders as clean-up.
  They are: never delete a folder to use it again.

