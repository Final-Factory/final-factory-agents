---
name: build-report-success-with-errors
description: Unity can report Succeeded with nonzero build errors; require a zero-error report and explicit compiler checks before accepting a native artifact.
---

On 2026-09-09, the Mac 0.50.0.11 miner candidate build returned normally and its
`BuildReport.summary.result` was `Succeeded`, but `totalErrors` was **1**. The preprocessing
step contained Burst BC1054 resolving `MinerBotPhysicalState` through `LocalPlayerMotionSystem`.
The completion marker also said `SUCCEEDED`. Neither signal established a clean build.
Evidence was preserved under `/private/tmp/ff-miner-physical-011/rejected-mac-attempt-1/` on M5.

Require `Succeeded` **and zero total errors**, inspect C#/Burst diagnostics, and preserve the
rejected artifact and log. If diagnostics indicate the documented stale Burst resolver problem,
follow [the existing recovery ritual](stale-burst-after-merge.md): stop only the positively
identified project editor, preserve its JIT cache, restart, re-pin, await fresh compilation and
Burst completion, rerun tests with Burst enabled, then rebuild. Do not disable Burst or ignore
the error to obtain a passing verdict. A clean rebuilt artifact remains necessary before the
matching cross-machine live gameplay test.
