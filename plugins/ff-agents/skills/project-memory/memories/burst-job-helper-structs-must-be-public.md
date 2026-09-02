---
name: burst-job-helper-structs-must-be-public
description: A struct held as a field of (or returned by a method on) a public job struct must itself be public, or the assembly fails CS0052/CS0050 "inconsistent accessibility"
metadata:
  type: project
---

A helper struct held as a FIELD of a `public` job struct — or returned by a public method on
one — must itself be `public`, or the assembly fails to compile with `CS0052`/`CS0050`
"inconsistent accessibility". If that error is still on disk when the editor next boots, it
boots straight into the unclickable native Safe Mode dialog (see the editor-ops skill's BOOT
Safe Mode recovery section).

Both R37g helpers hit this: `EntityWorldPose` (a field of `LinearMotionJob`, a public struct)
and `KnnChunkPoseHandles`/`KnnChunkPoses` (a field/return type in
`LegacyVisionShimSystem.AssignLegacyVisionJob<T>`, public). **Default new job-helper structs to
`public`** — the assembly is internal to the game anyway, and mod ABI concerns only apply to
global-namespace types (`Documentation/Mod-ABI-Surface.md`).

Sibling: [[fixed-group-reads-of-localtoworld-are-frame-count-bugs]] (the R37g fix these helpers
belong to).
