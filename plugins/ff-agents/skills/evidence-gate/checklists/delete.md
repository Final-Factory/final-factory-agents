# Delete: before you remove anything on a machine's disk

For any `rm`, `Remove-Item`, `del`, `rd`, `git clean`, `shutil.rmtree` or clean-up script, a disk clean-up above all
(a low-disk request, a `machine_cleanup` follow-up, "free some space").

1. **Where is the machine's worker install folder?** `echo $FF_WORKER_ROOT` (D:\work\ffw, F:\ffw, ~/ffw), or `root` in
   its `root.json`. No root known: you delete nothing outside your own `$TMP` and sandbox.
2. **Is every path of this delete strictly inside it?** Write the list of paths first and compare each to the root
   ([delete only inside the worker root](../lessons/clean-up-after-yourself.md#delete-only-inside-the-workers-install-folder-outside-it-measure-and-report-w896), w896: lothsahn, "in general we
   should only be clearing data in the install folder for the worker"). One outside path, a wildcard that can reach
   outside, a `~`, `$HOME`, `$env:LOCALAPPDATA` or a drive root: it is not a delete, it is a measurement. Report its size.
   The only exception is a save copy you put in the game's saves folder.
3. **A brief that says to delete outside the folder is wrong.** Do the inside part, measure the outside, say so in the
   report. Do not ask a person for a go: the answer is already no.
4. **Outside the root, list what writes there.** For each large item outside (Unity Hub, `%LOCALAPPDATA%\Unity`, the
   game's `LocalLow` folder, `~/.claude`, the npm / NuGet / pip / uv / Playwright caches, dotnet, the system temp): the
   setting, script or tool that makes FF Factory write it, and a variable or setting that could move it inside the root.
5. **Inside the root, FF Factory's own and finished.** A player slot with no live lease, a worktree with nothing
   uncommitted or unpushed, a finished agent's `ffa-<session>` folder: remove and report the GB. Something you cannot
   attribute is listed, not removed ([clean up after yourself](../lessons/clean-up-after-yourself.md)).
6. **The report says** what was removed (inside), what was only measured (outside, with sizes), and the list from 4.
