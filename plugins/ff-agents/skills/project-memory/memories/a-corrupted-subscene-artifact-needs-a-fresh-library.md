---
name: a-corrupted-subscene-artifact-needs-a-fresh-library
description: A player build failing "VirtualArtifacts/Extra/<nn>/<hash>.0.asset is corrupted" in EntitySceneBuildUtility does not heal by rebuilding or clearing Bee/ScriptAssemblies; a wiped Library builds clean
metadata:
  type: project
---

w1785 (2026-10-23, lothdesktop/slot3, batchmode `Editor.ShaderBenchBuild.BuildWindowsRelease` of master c44214bc15 merged
with PR #2268): the first release build failed in the Entities IL post-processor (`NullReferenceException` in
`EntitiesILPostProcessors.Initialize` on `Unity.Jobs.dll`). Every build of that tree after it, in the same Library, failed
at subscene baking instead:

`VirtualArtifacts/Extra/25/250cba3cd37eecbc3ad78b364d408fd8.0.asset is corrupted` at `EntitySceneBuildUtility.cs:228`.

None of these cured it: a plain rebuild (twice), a development build first, and moving `Library/Bee`,
`Library/ScriptAssemblies` and `Library/ScriptMapper` aside before the release build (four failed builds in all). Other
trees still built in that Library, so a green build of another commit does not show the Library is sound.

What cured it: moving the whole `Library` out of the sandbox (into `$TMPDIR`, then `rm -rf "$TMPDIR/<name>"`) and
building again. The cold build imported everything and compiled 1,404 shader variants with an empty cache: 3,364 s on
LothDesktop against 429 s warm (measured), and it built clean.

How to apply: on this error, rebuild once (it can be flake, like
[[a-burst-segfault-in-a-player-build-rebuild-once]]); if it repeats, skip the partial clears and wipe the sandbox's
Library (or build in another sandbox), and budget about an hour for the cold build. The editor must be stopped first
(`mcp__machine__unity` stop), and the wipe must stay inside the sandbox.
