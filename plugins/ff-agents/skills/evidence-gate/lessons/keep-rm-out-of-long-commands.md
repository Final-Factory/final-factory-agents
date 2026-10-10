---
name: keep-rm-out-of-long-commands
description: "A deletion chained into a long Bash command can stop the whole command on a permission prompt that nobody is watching. Run a delete as its own short command, or avoid it by writing to a fresh folder."
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
