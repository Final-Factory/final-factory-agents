# Batch player builds: never switch branches under one; an ILPP NRE on Unity.Jobs.dll is fixed, and a silent hang is a retry

**Seen:** w1773, 2026-10-22/23, biscuit (Linux), slot3. Linux development players built with
`unity-slot run -- Unity -batchmode -executeMethod Editor.LocalMultiplayerVerificationBuild.BuildLinuxMultiplayerDev`.

1. **A branch switch under a pending build builds the other branch.** A background build was queued
   behind the machine's Unity slots. I called `mcp__machine__switch_branch` meanwhile, and the build compiled
   whatever the worktree held when Unity read it. A player labelled "after" carried the other branch's
   code, so its stills proved nothing. That happened twice. **Do instead:** never switch while a build
   of the sandbox is queued or running; stop it first (`TaskStop`). On Windows, check it went: on lothlaptop
   (w1952/w1915, 2026-10-23) `TaskStop` of a background Bash ended the shell but left its children running twice: a
   `unity-slot run` Unity that finished the build, and a bench leg's bash and `bench_queue.py hold`, which kept the
   bench lock (`ff-leftovers list` did not list them). Find them by command line
   (`Get-CimInstance Win32_Process | ? CommandLine -match '<out dir>'`) and end the non-Unity ones by pid; a Unity
   batch goes through `mcp__machine__unity` `clear_batch`. For a before player, keep your
   branch and put the base's versions of the changed files in place:
   `git checkout HEAD~1 -- Assets Documentation` (or `<base> --`). Check first with
   `git diff --name-status <base> HEAD` that no file was added or removed. Build, then restore with
   `git checkout HEAD -- Assets Documentation`. Pass the pathspec as directories: a file name with a
   space, such as `LocalizationMasterTable Shared Data.asset`, breaks an unquoted `$(git diff --name-only)`.
2. **The first build after merging ~600 master commits failed** with
   `Unity.Entities.CodeGen.EntitiesILPostProcessors: ILPostProcessor has thrown an exception: System.NullReferenceException ... at EntitiesILPostProcessors.Initialize`
   on `Unity.Jobs.dll`. **That one is fixed at its cause** (w1952, FinalFactory PR #2355, merged 2026-10-23): Bee ran
   Entities' post-processor on `Unity.Jobs` (the deprecated, empty `com.unity.jobs` package) while `Unity.Entities` was
   still compiling, with no edge between the two. Measured on lothlaptop: master failed 5 of 7 release builds, the
   fix 0 of 9. A retry, a development build first or clearing `Library/Bee` only changed the odds, so don't use them
   for it. On a branch older than #2355, merge `origin/master` in. If it comes back on a newer tree, read
   `Documentation/Player-Build-ILPP-Race.md` ("If it comes back") in the game repo.
3. **A silent hang is a retry.** The next build of the same project hung. Its log stopped at
   `Unloading 206 Unused Serialized files` for 20 minutes, with the editor at 2.5 % CPU and its
   `Unity.ILPP.Runner` alive. I stopped the task (on Linux that ended the unity-slot run and its Unity), and the build went
   through on the first retry (0 `error CS`). So a silent log with idle CPU after about 8 minutes is a retry, not a code
   problem. Watch the log's mtime in the wait loop:
   `[ $(( $(date +%s) - $(stat -c %Y unity.log) )) -gt 480 ]`.
4. **`Editor.BuildCommand2.BuildWindows` cannot be an `-executeMethod`** (w1475, BEAST slot1, 2026-10-23, master
   8fe8bfc2ab): the batch run ended at once with `executeMethod method Editor.BuildCommand2.BuildWindows has 1 arguments.
   Only methods with 0 arguments are supported`, because `BuildCommand2.cs` also has a private
   `BuildWindows(FFVersion)` (`BuildCommand2.cs:607` beside the public one at `:795`; `BuildLinux` was renamed for the
   same reason by w1169). For a release (non-Development) Windows player in batch, use
   `-executeMethod Editor.ShaderBenchBuild.BuildWindowsRelease -ffBenchBuildOutput "<dir>/finalfactory.exe"`. In a
   running editor, `unity-bridge.py eval_file` with a snippet that calls `BuildCommand2.RebuildAddressablesForCurrentPlatform`
   and `GetDefaultPlayerOptions` by reflection, sets `locationPathName` and `BuildOptions.None`, and calls
   `BuildPipeline.BuildPlayer`, built one in 4 min.
