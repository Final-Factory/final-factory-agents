---
name: nightly-e2e-windows-lab-lessons-2026-09-29
description: "What moving the 075 nightly e2e lab to a Windows PC (lothdesktop) taught, 2026-09-29: a Unity Library copied from another clone has a stale script-to-class map (URP build NRE, missing scripts, FMOD settings dropped from the player) until every MonoScript is force-reimported (an FF Factory sandbox's first Library too: FMOD Setup Wizard at every start, no banks in the player); a bash script that git-switches its own checkout splices old and new text unless its body is one function; -nographics EditMode runs fail four GPU-bound fast-suite tests; a lab PC's own mods folder is shared with the players."
metadata:
  type: project
---

Source: spec 075 on lothdesktop (Windows 11, Intel Arc B580), `scripts/nightly/`, PRs #714 and #720, handoff in
`specs/075-nightly-e2e-regression/plan.md`. Companion to [[nightly-e2e-lab-lessons-2026-09-28]] (the M3 runs).

**A copied Library needs a forced MonoScript reimport.** A Library robocopied from another clone of the game
(same Unity version, same branch) loads, compiles and runs tests, yet `MonoScript.GetClass()` is null for scripts
under `Assets` while their assembly is loaded and `Type.GetType` finds the type. A plain `ImportAsset` of the
folder does not fix it within that session. Symptoms:

- a batchmode player build logs `UniversalRenderPipelineAsset_Renderer is missing RendererFeatures` and dies in
  URP's `ShaderBuildPreprocessor` with a `RenderingLayerUtils.RequireRenderingLayers` NullReferenceException
  (the FFRendering features `StarfieldFeature` and `OpaqueTextureGlobalFeature` deserialize as null);
- prefabs log `The referenced script is missing`;
- once the renderer scripts alone are fixed, the build succeeds but the player logs `[FMOD] Cannot find
  integration settings` and `[FMOD] Initialization failed`, with no banks in `StreamingAssets`, because FMOD's
  `Settings` ScriptableObject had the same problem.

Fix: one batchmode `-executeMethod` that force-reimports every MonoScript under `Assets`
(`AssetDatabase.FindAssets("t:MonoScript", new[] { "Assets" })`, `ImportAsset(path, ForceUpdate)` inside
`StartAssetEditing`/`StopAssetEditing`). It takes effect from the next domain load: 3602 scripts, a few minutes.
`scripts/nightly/install_schedule.sh` does this after it copies a Library.

**An FF Factory sandbox's first Library has the same stale map** (w604, lothdesktop slot6, 2026-10-07): 55 scripts
deriving from `MonoBehaviour`/`ScriptableObject`/`ScriptableRendererFeature` had no class (the FFRendering features,
FMOD's `Platform*` classes, Graphy, Quantum Console). Extra symptoms there: the editor log says `No script asset for
PlatformDefault` (and the other FMOD platforms), every editor start rewrites
`Assets/Plugins/FMOD/Resources/FMODStudioSettings.asset` without its ~770 lines of platform objects and the "FMOD
Setup Wizard" window comes back, and a bench player built in that state never leaves the title load (FMOD init
fails, `FpsPanel.Update` NullReferenceException every frame, Graphy "wasn't initialized"). Check before the first
build of a fresh sandbox: count MonoScripts with `GetClass() == null` whose file names a Unity-object type, then
force-reimport them in one `StartAssetEditing` batch, `git checkout` the FMOD settings asset, restart the editor,
and confirm 0 `No script asset for Platform`, 0 `missing RendererFeatures`, and `Master.bank` in the build's
`StreamingAssets`. Found by rediscovering it: grep project-memory for the symptom before debugging a build.

**A script that updates its own checkout must be parsed before it runs.** `nightly.sh` runs
`git switch --detach origin/develop` on the clone it lives in. Bash reads a plain script as it executes, so it
carried on at the old byte offset in the new file and ran spliced text: the old M3 lines (`df -g`, then
`build_player.sh … mac`) started a Mac build on Windows. Wrap the body in `main() { … }`, then
`main "$@"; exit $?`. Any unattended script that pulls or switches its own repo needs the same.

**Headless EditMode runs fail four GPU-bound tests.** With `-batchmode -nographics`, the fast suite fails
`MapViewProjectionTest.TheMapFramesTheSameWorldAsTheOldBlownUpPanel` (the 3840x2160 1.5f and 2.0f cases:
`RenderTexture.Create failed … maxRenderTextureSize(4096)`), `HoverFieldWarmUpTest` and
`DysonConstructionLoadKnnWitnessTest`. With graphics (`-batchmode` without `-nographics`) they pass. On
lothdesktop that run was 5679 total, 5664 passed, 0 failed, 15 ignored. Do not read these four as regressions
in a headless run.

**Built players share the machine's mods folder.** A player reads `persistentDataPath/mods`
(`ModLoader.ModPath`); the override environment variable there is editor-only. lothdesktop holds an old TowBot,
refused by the version guard with `ModLoadException: Mod is built for an incompatible game version` and
`Failed to load mod … due to error:`. The runner allow-lists that refusal and makes a scenario `env` when any
mod actually loads (ModLoader's `Loading Mod <id>` line, not `Loading Mod Info for <id>`). A log oracle built on
`Failed to load` must exclude `Failed to load mod`.

**Windows process details.** A `-batchmode` player has no window, so a plain `taskkill /PID` is refused at
once; stop it with `/T /F` by pid, never by image name. `schtasks /tr` turns inner single quotes into double
quotes. A runner started from an agent's background shell can survive a daemon restart and keep its players
running: find them by `-ffAutomationLabel` before relaunching.
