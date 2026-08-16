# The mod template breaks when the game ships new global-namespace types

**Lesson (2026-08-16).** The game's log-spam trace migration added a global-namespace
`public class Debug : UnityEngine.Debug` (`Assets/Scripts/FFCore/Logging/Debug.cs:53`,
shipped in FFCore.dll). In the mod template repo (`bryding/FinalFactoryModTemplate`),
the copied game DLLs used to be auto-referenced into every assembly — so that one type
produced ~260 `CS0576` ("conflicting with alias 'Debug'") errors inside Unity PACKAGE
code (visualscripting, netcode.gameobjects, shadergraph, burst editor, services.*) and
the template failed to compile for every new user.

**Fix shipped in the template (commit 7177d02):** the five DLLs' `.meta` files are now
tracked with `isExplicitlyReferenced: 1` (Auto Reference OFF), and `FFMod.asmdef` +
`FFMod.Editor.asmdef` list them in `precompiledReferences` instead. Unused
visualscripting package removed. Verified by a clean `-batchmode -quit` import
(exit 0, zero `error CS`).

**How to apply:**
- Game side: adding a public GLOBAL-namespace type to FFCore/FFComponents/FFSystems/
  FFTechnology/FFNetcode can break the mod template and every modder's project, even
  when the game itself compiles fine — names like `Debug`, `Logger`, `Random` that
  packages commonly alias are the dangerous ones. Prefer a namespace, or verify the
  template still imports cleanly after shipping.
- Template side: never delete/regenerate the tracked `Assets/FinalFactoryDlls/*.meta`
  files; a sixth shipped game DLL needs a matching Auto-Reference-off meta plus an
  entry in both asmdefs' `precompiledReferences`.
- Headless template check from any Mac with the game repo:
  point `finalfactory.properties` at a local build (e.g.
  `builds/windows/finalfactory_*_StandaloneWindows64`), run
  `./copy-finalfactory-dlls.sh`, then
  `Unity -batchmode -quit -projectPath <template> -logFile <log>`; exit 0 + zero
  `error CS` = green.
