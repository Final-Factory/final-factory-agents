# A play-mode material edit lands on disk with `m_ObjectHideFlags: 32`

**Seen three times:**
- `a6dc3b6d24` (w1066): "drop a play-mode hide flag the Works materials picked up".
- `71c536399e` (w1323): "put back two unrelated materials a play-mode session re-saved".
- w1393 (2026-10-16, beast/slot4): a latency spike. `git status` caught it before any commit.

## What happens

- **The edit.** w1393's spike set `CometCatcherMaterial._EmissionAG` in editor play mode, through `execute_code`
  (`Material.SetColor` on the asset). Nothing called `SaveAssets`.
- **The write.** Stopping the editor gracefully (`mcp__machine__unity` action `stop`) wrote the material to disk.
  The `.mat` came back with the test colour, and `m_ObjectHideFlags` went from 0 to 32.
- **Where the flag comes from.** In play mode the game sets `hideFlags |= DontUnloadUnusedAsset` on every
  RenderMeshArray material and mesh (`Assets/Scripts/Behaviours/StartController.cs:764-777`,
  `PreventRenderAssetUnloading`). Any save writes that flag into the asset.
- **Any save does it.** About 24 editor scripts call `AssetDatabase.SaveAssets`, and so does a graceful editor
  quit. So "it stays in memory until SaveAssets" is not a safe assumption.

The diff, kept as the test case for the planned game-repo hygiene check (w1393 plan, step 3):

```
-  m_ObjectHideFlags: 0
+  m_ObjectHideFlags: 32
-    - _EmissionAG: {r: 63.999992, g: 0, b: 33.598476, a: 1}
+    - _EmissionAG: {r: 64, g: 22, b: 0, a: 1}
```

## Rule

1. **Check git before and after stopping the editor.** After any play-mode asset experiment (`SetColor`,
   `SetFloat`, `manage_material`, importer settings), run `git status --short` before you stop the editor and
   again after it.
2. **Revert what you did not mean to change** with `git checkout -- <path>`.
3. **Never commit a `.mat` whose diff adds `m_ObjectHideFlags: 32`.**
4. **To keep a tuned value,** write the property line into the `.mat` text yourself, or use `SetDirty` +
   `SaveAssets` in edit mode and then remove the flag. Check that the diff holds only your lines.
