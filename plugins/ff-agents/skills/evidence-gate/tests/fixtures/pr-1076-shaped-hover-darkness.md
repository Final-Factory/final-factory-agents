<!--
Fixture for test_pr_evidence.py (w438).

FinalFactory #1076, "Range circles are no longer filled dark on hover (w435)", merged 2026-10-05: its Evidence
section as written, plus the "## Used by" section w438 asks for: the output of the game repo's
`scripts/asset_usage.py --markdown` on #1076's changed shaders and material, run on its tree
(08f876919), with each basis filled from #1076's own Evidence. The real #1076 has no such section and
fails the w438 check; this is what it looks like when it passes.
-->


**TL;DR:** Hovering any building with a range (mass driver, power distributor, laser turret, defense platform, exploration center, construction tower...) filled its whole range circle with a 75% black square, so the view went dark. 0.50.0.77's w410 (#1068, the Alt-view icon backing) put that backing in the sprite shader every range ring, warning icon and inserter arrow shares. This gives the backing its own shader, used only by the Alt-view icons, and puts the shared one back exactly as it was before w410.

## Evidence

Kind: visual

| Claim | Basis | Where |
|---|---|---|
| Build 77 darkens the inside of the range ring of a hovered mass driver, power distributor and laser turret | MEASURED: built player of 090be2632 (shaders and materials identical to 0.50.0.77), mean luma of a UI-free world patch: nothing hovered 6.42 / 6.60 (1920x1080 / 1280x800), cargo hold 6.37 / 6.57, mass driver 2.32 / 2.41, power distributor 2.31 / 2.40, laser turret 4.18 / 4.25 | brightness.txt, before77_*.png |
| With the fix nothing hovered darkens | MEASURED: built player of the fix (a831bbbb0), same patch: nothing 6.42 / 6.61, mass driver 6.37 / 6.57, power distributor 6.36 / 6.55, laser turret 7.82 / 8.05 (its red ring adds light), cargo hold 6.37 / 6.58 | brightness.txt, after_*.png |
| The rings themselves look as they did before w410 | MEASURED: pre-w410 built player (488f7eb): mass driver 6.35, power distributor 6.36 against 6.38 unhovered; the fix's rings are drawn by the restored pre-w410 graph (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` empty) | prew410_1920x1080_massdriver.png, sheet_*_top-build77_bottom-fix.png |
| The exploration center's ring had the same dark fill, gone with the fix | MEASURED: powered scene, world patch Build 77 4.94, fix 8.38, unhovered 6.37 | before77_1920x1080_explorationcenter_powered.png, after_1920x1080_explorationcenter_powered.png |
| w410 is the cause | MEASURED: the darkening is absent in 488f7eb (before #1068) and present in 090be2632 (after); `AltIconBackingScopeTest` red on develop's assets (2 failures), green with the fix | brightness.txt; test job in the editor |
| Alt-view icons keep the w410 backing | SOURCED: `AltIconSprite.ShaderGraph` is byte-identical to w410's graph (`git diff f2c0729f8:Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph HEAD:Assets/Art/Shaders/AltIconSprite.ShaderGraph` empty); `AsteroWorldSpriteMat` (the icon template, AsteroWorldIcon.prefab) uses it; the player build compiled and included it with no shader errors (Editor.log "Compiling shader AltIconSprite", build report 19.8 kb) | this PR's diff, AltIconBackingScopeTest |

Intended look (Ben): "when you hover over a mass driver for example, the radius circle is darkened... remove that", and "everything you hover over that has a range does that darkening effect"
Built player: yes, Development Windows players of 090be2632 (Build 77 shaders), 488f7eb (pre-w410) and the fix, launched from the slot pool, at 1920x1080 and 1280x800
Clips: before77_1920x1080_hover.mp4 and after_1920x1080_hover.mp4 (23 s, constant 60 fps from the game's own frames; hovers start at 3.0 s cargo hold, 5.5 s mass driver, 8.0 s power distributor, 10.5 s laser turret, 13.1 s defense platform, 15.6 s exploration center, 18.1 s construction tower, 20.6 s nothing)
Looked: yes, the stills at both sizes and clip frames 150, 320, 340, 400, 470, 490, 640 and 1260 of both clips: in Build 77 the frames with a mass driver, power distributor or laser turret hovered are visibly darker inside the ring, in the fix they match the unhovered frames and the rings are unchanged
Review: no watch_video or blind model review; the change is a static fill, judged by the measured brightness and by looking at the frames

Tests: FFEditorTests 7634 run, 7618 passed, 0 failed, 16 skipped (already Ignored); CI Test in editmode on this PR
Save compatibility: none, no saved state is touched

Not verified: the Alt-view icon backing was not seen in a built player (the automation Alt press did not turn the icons on in this scene); the defense platform and construction tower showed no ring in either build, powered or not (their range is a setting), so their rings are covered by the shared material (`RangeRingsKeepTheSharedSpriteShader`), not by a capture. Unchecked side effect: the same backing also put dark squares behind warning icons, inserter arrows and logistics markers in Build 77; the fix removes it there too, but I captured no before/after of those.

## Used by

<!-- From scripts/asset_usage.py. Fill in every Basis. TARGET: the change is meant for it (shown under Evidence). MEASURED: a built-player before/after of that user (name the stills or clip). SOURCED: why it cannot look different (e.g. the shader is restored byte for byte). More than the intended target? Make a new shader/material/variant for the target instead (evidence-gate, lessons/check-who-uses-a-shared-asset.md). -->

asset-usage: `Assets/Art/Materials/AsteroWorldSpriteMat.mat` has 1 user (1 prefab); they are used by 2 scenes, 1 prefab

| User | Basis |
|---|---|
| `Assets/Prefabs/AsteroWorldIcon.prefab` | TARGET: the Alt-view icon template, the one thing w410's backing is for (Evidence above) |

asset-usage: `Assets/Art/Shaders/AltIconBacking.hlsl` has 1 user (1 material); through 1 shader graph; they are used by 1 prefab

| User | Basis |
|---|---|
| `Assets/Art/Materials/AsteroWorldSpriteMat.mat` | TARGET: the Alt-view icon template, the one thing w410's backing is for (Evidence above) |

asset-usage: `Assets/Art/Shaders/AltIconSprite.ShaderGraph` has 1 user (1 material); they are used by 1 prefab

| User | Basis |
|---|---|
| `Assets/Art/Materials/AsteroWorldSpriteMat.mat` | TARGET: the Alt-view icon template, the one thing w410's backing is for (Evidence above) |

asset-usage: `Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` has 24 users (24 materials); they are used by 50 prefabs

| User | Basis |
|---|---|
| `Assets/Art/Materials/InserterArrow.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Art/Materials/LogisticsEnd.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Art/Materials/LogisticsStart.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Art/Materials/MapMaterials/PlayerMapMaterial.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Art/Materials/MapMaterials/PlayerMapMaterialOutline.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Art/Materials/OracleSpriteMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Art/Materials/alertrangeIndicatorMaterial.mat` | MEASURED: built players of Build 77 and the fix, hover over mass driver, power distributor, laser turret: before77_*.png / after_*.png, before77_1920x1080_hover.mp4 / after_1920x1080_hover.mp4 |
| `Assets/Art/Materials/rangeIndicatorMaterial.mat` | MEASURED: built players of Build 77 and the fix, hover over mass driver, power distributor, laser turret: before77_*.png / after_*.png, before77_1920x1080_hover.mp4 / after_1920x1080_hover.mp4 |
| `Assets/Resources/Icons/IconMaterial/CbotSwapStructureIconMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/ConstructionBotAssignedDeletionMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/ConstructionBotAssignedMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/DeletionMarkerMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/FilterWarningMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/LowOreWarningMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/LowPowerIconMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/NoChargeIconMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/NoConnectionMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/NoFuelMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/NoPowerIconMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/NoResearchSelectedWarningMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/OverheatingWarningMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/StabilityIndicatorMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/SwapStructureIconMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
| `Assets/Resources/Icons/IconMaterial/UnderConstructionMat.mat` | SOURCED: the graph is restored byte for byte to its pre-w410 state (`git diff f2c0729f8^ -- Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph` is empty), so it draws as in 0.50.0.76 |
