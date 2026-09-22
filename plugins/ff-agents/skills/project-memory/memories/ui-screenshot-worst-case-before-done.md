---
name: ui-screenshot-worst-case-before-done
description: Ben's standing rule — screenshot every player-visible UI you add or change at its worst case and fix layout faults before calling it done; the layout traps found in the 2026-09-22 pass.
---

# Screenshot UI at its worst case before calling it done

Ben, 2026-09-22: agent-built dialogs had shipped broken ("the button is not tall enough,
stuff is smashed"). Any player-visible UI an agent adds or changes — dialog, panel, HUD
indicator, settings page, or a new caller that feeds an existing dialog longer text — must be
screenshot in the editor (drive-game "Screenshots — THE canonical recipe") before it is done.
Fix what the screenshot shows; don't just report it.

Render the WORST case, not the demo case:
- the longest real text the code can produce (full detail strings, hex, file paths) and the
  longest locale;
- single-button / notice mode as well as two-button mode;
- one line per peer/agent with three peers;
- every HUD element that can be visible at the same time, together.

Check numbers as well as pixels: `TMP_Text.isTextOverflowing`, `preferredHeight` vs
`rect.height`, and each row's `rect.size` after `Canvas.ForceUpdateCanvases()`.

Traps found in that pass (fixed in game commit `b2578c090`):
- **A row's height can come from a sibling that may be hidden.** `ConfirmationModalParent`'s
  Buttons row took its 32 px from the Cancel button; OK-only notices (Desync Detected) got a
  20 px button. Give rows an explicit `LayoutElement` min/preferred height.
- **`VerticalLayoutGroup.childControlHeight = false` leaves a TMP text at its authored height**
  while its text overflows under the siblings below (the Connection Failed panel's 18 px
  message). Let the group control heights and pin fixed-height children with `LayoutElement`s.
- **Fixed-size text boxes over the world** (400×40 sync indicator, 420×28 agent chip) wrap
  and overflow. Use a `ContentSizeFitter` (plus a panel background when it floats over the
  world) and no-wrap for one-liners.
- **TMP's default LiberationSans SDF** marks UI that was never styled. The game font is
  Khyay-Regular SDF (Glow/OUTLINE variants); copy font + material from a neighbouring text.
- **A 717 px `manage_camera` capture mangles small text** into what looks like upside-down
  glyphs. Before "fixing" it, confirm with `screenshot_super_size: 2` plus a `sips -c` crop.
  In this pass, the Privacy tab label that looked flipped was fine.

Edit prefabs and scenes through the editor API (`PrefabUtility.LoadPrefabContents` → edit →
`SaveAsPrefabAsset`; `EditorSceneManager.SaveScene` in edit mode), never with text edits on an
open asset ([[no-external-edits-to-open-unity-scenes]]). Expect TMP's field-format upgrade lines
in the diff; they are harmless.
