---
name: new-cs-during-editor-boot-left-out-of-compile
description: A .cs written while the sandbox editor is still booting gets its .meta but can stay out of its assembly's compile list; refresh_unity and RequestScriptCompilation (even CleanBuildCache) compile nothing new and run_tests reports 0 tests; an AssetDatabase.MoveAsset round trip adds it
metadata:
  type: feedback
---

w1316 (beast/slot2, 2026-10-14). `Assets/Scripts/PlayModeTests/SaveThumbnailRoundTripTest.cs` was written about
20 s after `mcp__machine__unity start`, while the editor was compiling at boot. Unity imported it (the `.meta`
appeared, `AssetDatabase.LoadAssetAtPath<MonoScript>` found it, `GetAssemblyNameFromScriptPath` said
`FFPlayModeTests.dll`), yet `CompilationPipeline.GetAssemblies(AssembliesType.Editor)` for `FFPlayModeTests` listed
22 of the folder's 23 files. Every `refresh_unity mode=force compile=request`, a `RequestScriptCompilation`, and even
`RequestScriptCompilation(CleanBuildCache)` left `Library/ScriptAssemblies/FFPlayModeTests.dll` at its boot mtime, and
`run_tests` with the class name ran **0 tests, Passed** (twice, then with `group_names`).

**Fix:** `AssetDatabase.MoveAsset(path, tempPath)` and back, then `AssetDatabase.Refresh()` and
`CompilationPipeline.RequestScriptCompilation()`: the DLL was rebuilt a minute later and the test ran.

**Check, every time a new file must be in a run:** `System.Type.GetType("<Namespace.Class>, <Assembly>") != null`, or
the assembly's `sourceFiles` contains the path, or the DLL in `Library/ScriptAssemblies` is newer than the file. A run
of "0 tests, Passed" is never a pass ([[verify-compile-dll-string-check]]).
