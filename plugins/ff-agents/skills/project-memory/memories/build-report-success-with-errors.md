---
name: build-report-success-with-errors
description: Unity can report Succeeded with nonzero build errors; require a zero-error report and explicit compiler checks before accepting a native artifact.
---

On 2026-09-09, the Mac 0.50.0.11 miner candidate build returned normally and its
`BuildReport.summary.result` was `Succeeded`, but `totalErrors` was **1**. The preprocessing
step contained Burst BC1054 resolving `MinerBotPhysicalState` through `LocalPlayerMotionSystem`.
The completion marker also said `SUCCEEDED`. Neither signal established a clean build.
Evidence was preserved under `/private/tmp/ff-miner-physical-011/rejected-mac-attempt-1/` on M5.

Feature 074 T9 repeated this on Windows: `-batchmode -nographics` returned rc 0 and reported
`Succeeded`, while `LastBuild.buildreport` contained `totalErrors: 8` (RootHandler/scene NREs and
`RenderTexture.Create` failures). Reject that artifact. Rebuilding the same source (`d108b2bd6`) to a
fresh owned output with `-batchmode -force-d3d11` (without `-nographics`) reported `Succeeded`,
zero errors, and 113 warnings. This records the observed build outcomes, not a universal cause claim.

A successful log is insufficient. The serialized Windows `Library/LastBuild.buildreport` may be
copied to a Mac with `scp` and inspected read-only in Unity through
`UnityEditorInternal.InternalEditorUtility.LoadSerializedFileAndForget`, cast to `BuildReport`; inspect
the summary and every step/message with `Error` or `Exception` severity before accepting the artifact.

Require `Succeeded` **and zero total errors**, inspect C#/Burst diagnostics, and preserve the
rejected artifact and log. If diagnostics indicate the documented stale Burst resolver problem,
follow [the existing recovery ritual](stale-burst-after-merge.md): stop only the positively
identified project editor, preserve its JIT cache, restart, re-pin, await fresh compilation and
Burst completion, rerun tests with Burst enabled, then rebuild. Do not disable Burst or ignore
the error to obtain a passing verdict. A clean rebuilt artifact remains necessary before the
matching cross-machine live gameplay test.

## Zero errors can still omit baked SubScene files

Feature074 t11 on2026-09-20 built source54824f8df to a fresh Mac output. The report said
Succeeded/errors0, but StreamingAssets/EntityScenes contained only scene_info.bin. Boot logged
that `8acec14bc12bf1342a62a3972c315f45.entityheader` could not be opened and remained at
Starting game. That GUID is `Assets/Scenes/main/EntitySubScene.unity.meta:2`; the main scene
autoloads it (`Assets/Scenes/main.unity:175704`). `StartController` defers startup without
the baked EntityPrefabContainer (`Assets/Scripts/Behaviours/StartController.cs:271-274`).

The same source rebuilt with `BuildOptions.Development | BuildOptions.CleanBuildCache`
to another fresh owned output succeeded/errors0 and included both the `.entityheader`
and `.0.entities` files. The replacement booted, joined Windows and native ARM64 M3, and
passed the three-peer baseline. This is an observed recovery, not proof of the cache root cause.
Preserve the rejected build/log; do not copy scene data from an older player. Before accepting
a player, verify the required main SubScene files exist under its StreamingAssets/EntityScenes
and perform a real startup check. A zero-error BuildReport alone is insufficient.

Witness: M5 `/private/tmp/ff073-hazel-20260915/xplat/t11-artifacts/`, rejected
`player-t11-54824f8`, accepted `player-t11b-54824f8`; build manifest and rejected startup log
are preserved there.
