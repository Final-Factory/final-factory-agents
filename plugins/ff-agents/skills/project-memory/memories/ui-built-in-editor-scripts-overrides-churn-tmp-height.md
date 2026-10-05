---
name: ui-built-in-editor-scripts-overrides-churn-tmp-height
description: Building UGUI panels and scene edits through execute_code (w449, 2026-10-05) - prefab-instance edits need RecordPrefabInstancePropertyModifications or they vanish on save; saving main.unity or the localization tables re-serializes unrelated objects/rows, so rebuild the file as base + only the intended blocks; a TMP with Ellipsis/Truncate shows nothing when its rect is shorter than one line
---

# Building UI with editor scripts: overrides, churn, TMP height

w449 (the mobile station overview) built three prefabs and rebuilt a Factory Information tab in
`main.unity` from `execute_code`. Three traps cost a rebuild each.

**Edits to a prefab instance's existing children are lost unless recorded.** Setting
`tmp.text = "..."` on the placeholder of an `FFInputField` instance, or a tab label inside an
instance, looked right, saved with `EditorSceneManager.SaveScene`, and came back as the old text on
the next play. Write such properties through `SerializedObject` (`FindProperty("m_text")`,
`ApplyModifiedProperties`) and then `PrefabUtility.RecordPrefabInstancePropertyModifications(component)`.
New GameObjects and new components added under an instance were saved without this. Check the
scene file for the override (`value: <your text>`) before trusting it. To switch off a component on
an instance (a `Mask`), set `m_Enabled` the same way rather than destroying it.

**Saving re-serializes far more than you changed. Keep only your blocks.** A save of `main.unity`
after small edits rewrote ~90 unrelated objects (layout-driven `m_AnchorMin`/`m_AnchoredPosition`
overrides on other panels' prefab instances: `value: 1` -> `0`), and adding 27 strings through
`LocalizationEditorSettings` re-wrapped or re-quoted hundreds of unrelated `m_Localized` rows. Both
are byte churn with no meaning, and they invite merge conflicts. Rebuild each file as the base
(`git show HEAD:<file>`) plus only the intended blocks: for the scene split on
`^--- !u!<class> &<fileID>`, take your changed objects from the saved file and insert added objects
in fileID order (the file is sorted by fileID); for the tables split on `^  - m_Id: <id>` and append
your new ids after the last entry. Verify by diffing object ids (no removals) and decoding a few
rows. Close the editor before replacing a scene it has open, or it raises the "modified
externally" modal.

**Merging develop into a branch that appended table rows conflicts at the end of every table**
(both sides append there). Resolve each table as develop's file plus the branch's added `m_Id`
blocks (relative to the merge base), not by keeping both sides of git's hunk, which can leave
develop's entry without its `m_Metadata` lines. Check there are no duplicate ids afterwards.

**A TextMeshPro with `overflowMode` Ellipsis or Truncate draws nothing when its rect is shorter
than one line.** Status and route lines at 16 pt in 22-unit `LayoutElement` boxes rendered blank in
the built player while `tmp.text` held the right string (Khyay's line is about 1.67 x the size:
~27 units at 16 pt; the locale fonts can be taller). Don't pin TMP heights: drop the
`LayoutElement` preferred height and let the layout group use the text's preferred height, then size
the fixed container (a grid cell) with room to spare. Measure lines with
`tmp.GetPreferredValues(text, 10000, 100)`. The same trap hides a count under an icon.

Also seen: the game font (Khyay) has no `▸`/`▶`/`→` (they come from a fallback, or as a box);
`»`, `›` and `•` are in it (`font.HasCharacter(c, false, false)`).

Related: [[ui-screenshot-worst-case-before-done]], [[no-external-edits-to-open-unity-scenes]],
[[textlocalization-duplicate-gotcha]].
