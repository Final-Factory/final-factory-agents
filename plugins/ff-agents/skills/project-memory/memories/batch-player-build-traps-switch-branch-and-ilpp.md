# Batch player builds: never switch branches under one, and retry an ILPP crash or a silent hang

**Seen:** w1773, 2026-10-22/23, biscuit (Linux), slot3. Linux development players built with
`unity-slot run -- Unity -batchmode -executeMethod Editor.LocalMultiplayerVerificationBuild.BuildLinuxMultiplayerDev`.

1. **A branch switch under a pending build builds the other branch.** A background build was queued
   behind the machine's Unity slots. I called `mcp__machine__switch_branch` meanwhile, and the build compiled
   whatever the worktree held when Unity read it. A player labelled "after" carried the other branch's
   code, so its stills proved nothing. That happened twice. **Do instead:** never switch while a build
   of the sandbox is queued or running; stop it first (`TaskStop`). For a before player, keep your
   branch and put the base's versions of the changed files in place:
   `git checkout HEAD~1 -- Assets Documentation` (or `<base> --`). Check first with
   `git diff --name-status <base> HEAD` that no file was added or removed. Build, then restore with
   `git checkout HEAD -- Assets Documentation`. Pass the pathspec as directories: a file name with a
   space, such as `LocalizationMasterTable Shared Data.asset`, breaks an unquoted `$(git diff --name-only)`.
2. **The first build after merging ~600 master commits failed** with
   `Unity.Entities.CodeGen.EntitiesILPostProcessors: ILPostProcessor has thrown an exception: System.NullReferenceException ... at EntitiesILPostProcessors.Initialize`
   and `executeMethod ... threw exception`. The log had 0 `error CS`, and the same commit had just passed
   a batch EditMode run of 271 tests. The next build of the same project **hung**. Its log stopped at
   `Unloading 206 Unused Serialized files` for 20 minutes, with the editor at 2.5 % CPU and its
   `Unity.ILPP.Runner` alive. I stopped the task, which ends the unity-slot run and its Unity. Both
   builds then went through on the first retry, the after player included (0 `error CS`). So an ILPP NRE
   with no `error CS`, or a silent log with idle CPU after about 8 minutes, is a retry, not a code problem.
   Watch the log's mtime in the wait loop:
   `[ $(( $(date +%s) - $(stat -c %Y unity.log) )) -gt 480 ]`.
