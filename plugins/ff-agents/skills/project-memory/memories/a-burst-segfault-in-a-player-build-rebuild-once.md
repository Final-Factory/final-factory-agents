---
name: a-burst-segfault-in-a-player-build-rebuild-once
description: A Mac player build that dies in the Burst compiler with a native segfault in mono passed on a plain rebuild of the same commit
metadata:
  type: project
---

w1386 (2026-10-18, m5/slot2, `scripts/nightly/build_player.sh` of 3c1cae88): the build ended `build-failed` with a native
segfault inside the Burst compiler under mono and left `mono_crash.<hash>.0.json` in the worktree root. The same commit,
built again with nothing changed, passed. Rebuild once before you read the code; move the crash dump out of the worktree
(it is untracked and blocks `switch_branch` and a clean-tree build). Seen once: if it repeats on one commit, it is not flake.
