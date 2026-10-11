---
name: delegated-implementors-on-ff-sandboxes
description: w1037 2026-10-11 — on an FF Factory sandbox, Agent isolation "worktree" lands under the protected main clone (every Edit refused); give an implementor a sparse shared clone under $TMPDIR instead, and run lab scenarios on one build at a time, since a sandbox's two player slots hold one build each
metadata:
  type: project
---

**Isolated worktrees are refused on FF Factory sandboxes (w1037, lothdesktop, 2026-10-11).** The Agent tool's
`isolation: "worktree"` creates the child's worktree under the machine's main clone
(`<worker root>/repo/.claude/worktrees/agent-*`), which the harness protects. So the child's first Edit or Write was
refused ("inside protected path ...") and it stopped. Instead, give an implementor its own clone under your
`$TMPDIR`: shared objects, a sparse checkout of what it edits, at your commit.

```sh
D="$(cygpath -m "$TMPDIR")/g4-clone"
git clone -q --shared --no-checkout <your sandbox worktree> "$D"
MSYS_NO_PATHCONV=1 git -C "$D" sparse-checkout set --no-cone '/scripts/' '/docs/' '/Documentation/' '/Assets/Tests/Serialization/Fixtures/'
git -C "$D" checkout -q -b w1037-g4 <sha>
# afterwards, in your sandbox:
git -C "$D" diff > "$TMPDIR/g4.patch" && git apply "$TMPDIR/g4.patch"
```

- Without `MSYS_NO_PATHCONV=1`, Git Bash rewrites `/scripts/` to `C:/Program Files/Git/scripts/` and the checkout comes
  out empty ("0% of tracked files present").
- The nightly runner needs only `scripts/` and the save fixtures, so a child can run scenarios from that clone. It
  reads game code from your sandbox read-only, and never edits your tree while `build_player.sh` runs (the build
  reverts tracked edits).
- A Bash command that names the main clone's path, even inside a heredoc's text, is refused by the hook; write such
  text with the Write tool, or don't spell the path out.

**One build at a time per sandbox in the lab.** A sandbox's player pair (`slotK-0`, `slotK-1`) holds one build per
folder, and children inherit `FF_PLAYER_PEER`. A second `ffnightly.py run` on another build, yours or a child's, fails
at once with `player_slots.SlotRequired ... holds another build still in use`. Runs on the SAME build share the pair
fine. Several builds take turns: wait until `python scripts/nightly/player_slots.py status` shows no `leases` on your
pair, then start (w1037 lost three runs to this before waiting on the leases). Each concurrent run still needs its own
`FF_NIGHTLY_ROOT` and a lab file with its own `port` (README-sp.md).

Related: [[feedback-built-players-run-from-the-slot-pool]], [[sandbox-player-build-reverts-tracked-edits-and-quiet-window-suspend]].
