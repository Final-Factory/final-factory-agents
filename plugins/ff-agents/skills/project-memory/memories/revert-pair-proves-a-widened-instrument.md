---
name: revert-pair-proves-a-widened-instrument
description: "A widened determinism-audit surface is proven only when it goes POSITIVE on the exact fork it was widened for -- build a pair from a scratch commit that carries the widening WITH THE FIX REVERTED, rerun the RED-shape leg, and expect the surface named as the first mismatching field on the fork heartbeat (073 h1: `asteroids` at hb 1198, host detector verdict, recovery). Recipe: make the scratch commit through a temporary GIT_INDEX_FILE so the live editor's tree is untouched, verify it is the exact inverse of the fix by diff, ship it to BEAST as a git bundle through PowerShell (a plain ssh->cmd.exe line eats `&&` as well as `|`), then switch the live editor's tree to the scratch branch only for the Mac build and back."
---

# Prove a widened instrument positive with a revert pair (073, 2026-09-16)

**The rule.** A widened fingerprint surface has two proofs: a unit test showing the hash moves, and a
LIVE positive on the fork it was widened for. The second needs the fork to still exist, so build the
pair from `<tip> + revert(<fix>)`: the instrument is new, the bug is back, and the leg that used to
stay green must now go RED on the widened field. (h1: `asteroids` + `combined` the ONLY mismatching
fields at hb 1198-1201; `RuntimeDesyncDetectorSystem` verdict `surfaces: asteroids` at hb 1200;
`DesyncRecoverySucceeded` epoch 2 hb 28; epoch 2 clean over 5,231 hb. Details:
`specs/073-hazel-playtest-mp-fixes/plan.md`, 2026-09-16 01:40 UTC header.)

**Recipe (M5 + BEAST).**
1. Scratch commit WITHOUT touching the live editor's working tree:
   `GIT_INDEX_FILE=<scratch>/h.index git read-tree <tip>`; `git update-index --cacheinfo 100644,$(git
   rev-parse <fix>^:<path>),<path>` for each file the fix changed; `git update-index --force-remove`
   the fix's added test + .meta; `git write-tree`; `git commit-tree <tree> -p <tip>`; `git branch
   scratch/<name> <sha>`. Verify: `diff <(git diff <fix> <fix>^ | grep -v ^index) <(git diff <tip>
   <sha> | grep -v ^index)` must be empty. Name the branch `scratch/…` and never merge it.
2. Ship to BEAST: `git bundle create x.bundle refs/heads/scratch/<name> ^<beast HEAD>`; scp; on BEAST
   through `beast_ps.sh` (PowerShell, `-EncodedCommand`): `git fetch <bundle> ref:ref; git checkout
   scratch/<name>`. A plain `ssh … bash.exe -c "a && b"` line loses the `&&` to cmd.exe exactly like
   `|` ([[built-pair-lab-traps-073]]).
3. Windows build: copy `ff-worker/build-win-<sha>.sh` (Prepare pass + Build pass, ~8 min on a warm
   Library), launch it as a detached local `nohup ssh … &` and monitor `build-status.txt`; accept only
   `build rc=0` AND 0 `error CS` AND 0 Burst errors in `build.log`.
4. Mac build: `git checkout scratch/<name>` in the live checkout, `refresh_unity scope=all mode=force`
   (a deleted `.cs` needs the asset rescan -- [[git-deleted-cs-under-live-editor-cs2001]]), prove the
   editor is on the scratch tree by reflection (the fix's test type must be ABSENT), then schedule
   `BuildPipeline.BuildPlayer` from a one-shot `EditorApplication.update` callback with a marker file
   (~5 min, universal binary). Afterwards `git checkout develop`, refresh `scope=all`, and prove the
   type is PRESENT again before any other editor work.
5. Leg: same shape as the GREEN leg (actions -> throttle LAST -> checkpoint after). Read
   `fpcompare.py` per epoch and the host's `desyncReports/*.txt` (`divergedSurfaces=`); the typed
   `cpcompare.py` says `evidence-invalid` on a window that holds the recovery record
   ([[verdict-script-rejects-eviction-records]]) -- that is expected, not a failed leg.
