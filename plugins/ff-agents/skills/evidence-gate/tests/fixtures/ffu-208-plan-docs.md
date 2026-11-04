Request: w3022 (FFU pack audit: re-check every other kept row for inactive objects and the beam VFX takeover), for ben.

Ben, 2026-11-03: "only bring over assets actually used in the game, theres a lot of stray assets that arent in the game at all"

Stacked on #206 (w3015's third pass); once #206 merges, this diff is only the w3022 commit.

`docs/pack-recreation.md` gets a "Fourth pass (w3022)" section. R.M1, R.T1, R.T2, R.T3, R.T4, R.V4, R.V5 and R.S2 (78 assets) were re-checked under all four rules at once: active object, declared field, not only `EntityScene`, not only the hidden Mining or Research laser mesh.

## Rows

- **R.T1 rescoped** 36 to 35: `Tex_skill_104_flipped` appears only on `CameraControlsPanel` in `main.unity`. The panel has been inactive since game commit `e59033de73` (2022), and nothing references it or turns it on. PR #136's icon for it replaces nothing.
- **R.T4 rescoped** 6 to 5: `TranslucentCrystal01_MetallicSmoothness` sits in `Texture2D_8C5C0069` on its 11 drawn beam materials. None of their shader graphs declares that slot, so Unity strips the texture. The texture looked present in the player only because its folder is a `Resources` folder. PR #149's `shards.png` replaces nothing.
- **R.M1, R.T2, R.T3, R.V4, R.V5, R.S2 kept**, with every asset reached by a live chain. R.T4's `Circle17`, `Point5`, `Trail22Rotated` and `vfx_FLORB_0067` are kept.
- **Baked but unread**: `SystemAssetContainer.MassDrivenItemImpactEntity` (`SystemAssetContainer.cs:77`) is read by nothing. Its `VfxMassDriverBurst` carries no row's asset.
- **A gap in the w3015 chains**: they skipped model importers' material remaps (`externalObjects` in a model's `.meta`). The new pass follows them; `Waves17` reaches the game only that way and stays used.

## Evidence

The chains were read statically from the game repo's YAML and `.meta` files at `538a910d2a`, plus a search of the shader graphs (SOURCED, with file:line in the doc). There was no `CollectDependencies` editor run, because all three Unity slots on lothdesktop were taken. Docs only; nothing a player sees changes.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

