---
name: review-findings-need-parent-adjudication
description: "Two live cases where a high-effort code review was confidently wrong in ways that would have broken the build or the diagnosis: it called a REQUIRED scripting define stale residue to revert, and it read a file's directory name as its system group. Re-open every cited line before acting."
---

# A review finding is a candidate, not a verdict

The repo rule (`CLAUDE.md`) that the parent must re-open every cited line before accepting a
finding is not ceremony. Two findings from one `/code-review high` pass on 2026-09-20 (074 T116)
were stated with full confidence, with file:line citations, and were wrong — one of them
destructively so.

**1. It told me to revert a define that the build REQUIRES.** The finding rated
`ProjectSettings/ProjectSettings.asset` adding `FF_ENABLE_MULTIPLAYER_BUILD` to the Standalone
defines as high severity "residue from the mp_beta upload session … should be reverted before
commit", citing that the harness restores ProjectSettings by `git checkout` afterward. The
citation is real; the conclusion inverts it. `LocalMultiplayerVerificationBuild.BuildMultiplayerDev`
THROWS when the define is absent (`Assets/Editor/LocalMultiplayerVerificationBuild.cs:86-94`,
"Run the Prepare* pass first in a SEPARATE `Unity -batchmode` invocation"), because pass 1 sets
and persists it deliberately. Reverting it breaks every MP player build. The dirty
`ProjectSettings.asset` carrying it is the documented steady state of the built-pair lab
(see [built-pair-lab-traps-2026-09-18](built-pair-lab-traps-2026-09-18.md)). Correct action: keep
it OUT of the commit, do NOT revert it, and say so.

**2. It read a directory name as a system group.** The finding argued a timing window on the
grounds that `BlueprintPlacerJob` "runs in a **Controller** group on an arbitrary engine frame at
click time". The file lives under `Assets/Scripts/ControllerSystems/`, but its attribute is
`[UpdateInGroup(typeof(FFFixedPreTransformGroup))]` (`BlueprintPlacementSystem.cs:45`) — a FIXED,
heartbeat-only group. The conclusion (the mirror is eventual, not simultaneous) survived; the
mechanism did not, and the mechanism is what a reader would have acted on. **`ControllerSystems/`
is a directory, not a group** — always read the `UpdateInGroup` attribute.

The same pass also produced one genuinely valuable finding — a factual error in a comment I had
just written, claiming the apply-time conflict skip destroys entities in the returned list when
`BlueprintTool.cs:567-569` `continue`s before the `placed.Add` at `:587`. So the answer is not to
distrust reviews; it is that accepting a finding and acting on it are the same act, and both
require re-opening the cited lines. Findings that recommend REVERTING or DELETING state deserve
the most scrutiny, because acting on them is what loses work.
