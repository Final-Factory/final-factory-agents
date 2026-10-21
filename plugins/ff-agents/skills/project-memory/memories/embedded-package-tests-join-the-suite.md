# An embedded package's tests join the project's suite; a registry package's never do

**Learned:** 2026-10-21, w1675 (FinalFactory PR #2129), biscuit.

#2006 (w1578) copied `com.unity.entities.graphics` into `Packages/` to patch one job, test folders included
(`Unity.Entities.Graphics.Tests/`, `Unity.Entities.Graphics.PerformanceTests/`). Unity compiles and runs an embedded
package's test assemblies as the project's own, so 62 upstream cases joined the master batch's whole EditMode suite
(14,621 → 14,684 cases). After them, the test framework's `PerformUndoTask` (`Undo.RevertAllDownToGroup`, synchronous
on the main thread) spun the editor for hours (main thread in state R at about 92% CPU, measured). The smoke PlayMode
test that `MergeGateTestRunner` starts next in the same editor never ran. The pull request gate missed it: it runs only
the classes a change touches. Reproduced with only those 6 classes and then the smoke, in a `unity-slot run` batch
editor: stuck at `DisplayProgressbar: Undo` until a timeout ended it 21 minutes later.

**How to apply:**
- When you embed a package, delete its test folders and the folders' `.meta` files, write that in the package's
  `FINALFACTORY-PATCHES.md`, and add a guard test that fails if they come back
  (`EntitiesGraphicsPatchGuardTest.TheEmbeddedCopyCarriesNoTestsOfItsOwn`).
- An editor stuck after an EditMode run with `DisplayProgressbar: Undo` as its last line, and `Unloading <tens of
  thousands> unused Assets` just before it, is the test framework reverting the undo stack. Look for tests that
  build many GameObjects or bake them, run by exact class name before the smoke, to find the cause.
- To run `.github/scripts/master-batch.py` in a sandbox: it ends with `git checkout --force <tip>`, so HEAD is left
  detached (reattach with `switch_branch`). The editor writes `Assets/InitTestScene*.unity` and `mono_crash.*.blob`
  files into the worktree (move them to `$TMPDIR`) and rewrites a few `.mat` files (`git checkout --` them). On a
  Linux PC with a real GPU, give the editor wrapper `-force-glcore` with `LIBGL_ALWAYS_SOFTWARE=1`, matching CI's
  llvmpipe: biscuit's Vulkan driver (`libvulkan_radeon.so`) crashed when the smoke's player camera started.
- Related: [[a-ci-timeout-shows-as-cancelled]].
