# uGUI rules and pitfalls

The rules Unity's layout system follows, and how each one has bitten Final Factory. Unity's own
manual pages for these components are the source for the rules: "Auto Layout", "Rect Transform",
"Canvas Scaler", "Scroll Rect", "Grid Layout Group", "Content Size Fitter", "Mask" and "RectMask2D".

## Canvas and scaling

- **`CanvasScaler.scaleFactor` turns layout units into pixels.** Final Factory's HUD canvases are
  driven by `UiScaler` (`Assets/Scripts/UI/UiScaler.cs`), not by the scaler's own mode: factor =
  `ScreenFactor(w, h) * uiScale`. `ScreenFactor` is the geometric mean of w/1920 and h/1080 at and
  above 1080p; below it the UI grows a little instead of shrinking (`SmallScreenGrowth` 0.2), so text
  stays 9.5 px tall at 1280x800 (Valve's rule is 9 px).
- **The Deck has much less room in layout units.** 1280x800 at 0.80 (the Deck default since w727):
  factor about 0.847, canvas about 1511x944 units; at 0.90: about 0.953, 1343x839 units. 1920x1080 at 0.90: about 2133x1200. Anything sized for desktop (a 700-unit
  window, a fixed grid height) takes a far bigger share of a Deck screen. Compute in units:
  `canvasRect.rect` of the root canvas, or `Screen.height / canvas.scaleFactor`.
- **16:10 is not 16:9.** Anchored layouts built at 16:9 get extra height and less width at 16:10;
  check both 1280x800 and 1920x1080, never only one.
- **Pixels, for the Deck rules.** Text height and glyph size in screen pixels are layout size times
  `scaleFactor`. The Deck tour's census measures them for you.

## RectTransform

- **Anchors decide what `sizeDelta` means.** With anchorMin == anchorMax, `sizeDelta` is the size.
  With stretched anchors it is the size MINUS the anchored area (a stretched child with sizeDelta 0
  is exactly its parent's size). Read `rect.width/height` for the real size; set `offsetMin` /
  `offsetMax` for stretched edges.
- **Pivot moves the rect for `anchoredPosition` and for growth.** A window with pivot y = 1 grows
  downwards when it gets taller; with pivot 0.5 it grows both ways and its top can leave the
  screen. Panels that must stay on screen pin their pivot to the side they hang from.
- **Screen rect.** `GetWorldCorners` then `RectTransformUtility.WorldToScreenPoint(cam, corner)`
  (cam null for a Screen Space Overlay canvas). Screen y counts from the BOTTOM; images count from
  the top. The Deck tour's `rect:` setup logs screen pixels (`ui_check.py --unity-y` flips them).
- **Sizes are stale until the layout pass.** After `SetActive(true)`, a text change or a child
  added, `rect` still holds the old size until Unity's layout rebuild late in the frame. Measure
  after `LayoutRebuilder.ForceRebuildLayoutImmediate(rect)` or on the next frame, never right after
  the change (the hub's `Grow` rebuilds once before it measures for this reason).

- **A layout rect is not what is drawn.** Measure the union of the drawn graphics, not a parent's
  rect: the minimap's layout rect reaches 6.5 units past its drawn frame, so #1264 spaced the quick
  buttons from it and the gap went from 6.48 to 22.75 units (w732, `specs/w732-hud-corner/HANDOFF.md`
  on `origin/sandbox/slot2-w732`). The tour's `HudLayout` measures drawn extents.
- **A layout fix that throws looks like no change.** #1264's first commit threw in a static
  initializer (`Debug.isDebugBuild`), so the fix never ran and its stills matched the before. Read the
  player log for exceptions before trusting an "after"; give the fix an off switch
  (`-ffNoHudCornerSpacing`) and show the measured difference against it.
- **A prefab-instance child placed by a `GridLayoutGroup`** ignores its own position: change the
  group's spacing and the parent rect.

## Layout groups, LayoutElement, ContentSizeFitter

- **A layout group owns its children's size and position** on the axes where `childControlWidth/
  Height` is on, and their position always. Setting a child's `sizeDelta` or `anchoredPosition` by
  hand is overwritten on the next layout pass. Change a `LayoutElement`'s `min/preferred/flexible`
  instead, or take the child out with `LayoutElement.ignoreLayout`.
- **Sizes come from min, preferred, flexible.** The group gives every child its min, then up to its
  preferred, then shares the rest by flexible. A child with preferred 0 and flexible 0 gets its min:
  often 0, so it vanishes. `childForceExpand` turns spare room into flexible size.
- **`ContentSizeFitter` belongs on an object whose parent has no layout group** (or on a layout
  root). Under a group it fights the group for the size (Unity warns "Parent has a type of layout
  group component"). For a child under a group, give the group control and set the child's
  `LayoutElement` instead.
- **The structured dock turns off every `ContentSizeFitter` under a window it docks** (`DockedWindow.ForceWidth`, inactive
  ones too, only those inside a `Selectable` spared), so a row child whose width came from a fitter keeps its prefab width,
  often 0. w792: the Ship Yard's `Requests` group (width 0 + fitter) stayed 0 wide when "Request Specific Units" was switched
  on after the dock, and the Max button drew over the Requested field on a real Deck (Build 92). Give a row child its width in
  the prefab or a `LayoutElement` the row group reads; never a fitter on a 0-wide child inside a docked window. The check:
  the Deck tour's `rowOverlaps` count (`DeckTourChecks.RowOverlaps`, drawn pieces of neighbours in one row) and a test that
  docks the real prefab with `StructuredDock.DockedWindow.ForceWidth` (game repo `ShipYardRowsTests`).
- **Fitters size one pass late.** A fitter's object is the right size only after a layout pass;
  chained fitters (a fitter whose size depends on another fitter's child) can take more than one
  frame to settle and jitter meanwhile.
- **One owner per size, or it flickers.** Two scripts (or a script and a group or a fitter) writing
  one RectTransform alternate each frame: the panel jumps, an icon blinks in and out. Find every
  writer before you add one (`WindowFit`, `ListGrow`, `KeepOnScreen`, `MaxHeightViewport`,
  `StructuredDock`, layout groups, fitters). Write only when the value really changes (a slack of a
  pixel, as `WindowFit.Slack`), never every frame: a write every frame also rebuilds the canvas every
  frame (w644 #1244 measured it).

- **One owner per alpha, too (w764).** A `CanvasGroup` hidden once by one script is shown again by a component that
  fades its own group in every frame (`ObjectivesPanel.LateUpdate` against `StructuredDock.Faded`: the card was back in
  half a second). Give the owner a hold (`ObjectivesPanel.HeldHidden`), or hide it every frame after it.
- **A hidden element must give back its room.** The classic layout kept a faded objectives card in the list of HUD the
  windows keep off, so a window sat 330 units down and was cut to three rows under a card nobody saw.
- **A box that is HUD only sometimes must not be HUD always (w764).** The classic layout kept off the station's info
  box as HUD that is never covered even when it was only a hover over a station with nothing selected; a 628-unit window
  has no clear place beside it, so the packer fell back to the place that covers least and the Inventory and Crafting
  windows swapped sides each time the pointer crossed a station. Decide what a piece is by what the player has done
  (a station selected), not by whether it is drawn.

- **A fixed size you change in a prefab is still the old size in the scene (w821).** `main.unity` holds an instance of
  most window prefabs, and the scene writes the sizes the layout last computed into it as overrides (`m_SizeDelta.x`
  under the instance's `m_Modifications`, keyed by the prefab's fileID). The production window's progress column was
  widened from 245.86 to 290 in the prefab; the scene kept 245.86, so the heading and bar ran 44 units into the Outputs
  column and the window did not grow, while the prefab-only unit test passed. Edit the override in the scene too (a
  text edit of the two `value:` lines is enough), and keep a test that reads the scene's overrides against the prefab
  (`ProductionPanelLabelsFitTest.TheSceneKeepsNoStaleSizeForTheHandSizedElements` is the pattern: map the prefab's
  rects to fileIDs with `AssetDatabase.TryGetGUIDAndLocalFileIdentifier`). Close the editor's scenes (or stop the
  editor) before you swap a scene file on disk: it stops on "scene modified externally".
- **A fixed-width label in a layout group wraps first in the longest language, and ellipsis overflow is a suspect
  when a Cyrillic heading blanks (w821).** Give the heading a `LayoutElement` `flexibleWidth` 1 and `NoWrap`, and keep every
  sibling that is not meant to grow (the power readout, whose icon holder has `childForceExpandWidth`) at
  `flexibleWidth` 0 with its own `LayoutElement`, or it takes half the spare width. Leave `overflowMode` at Overflow:
  with Ellipsis the Russian heading drew nothing and reported a garbage rect (the build that fixed it also fixed the
  scene width, so the cause is not isolated). Measure each language's text in its runtime font
  (`TMP_Text.preferredWidth`, per `LocalizationHelper.ApplyFont`) against the box, as `ProductionPanelLabelsFitTest`
  does for all 11 shipped languages.

## Grids

- **`GridLayoutGroup` never shrinks its cells.** Cells are `cellSize` exactly; the group's
  constraint (Flexible, Fixed Column Count, Fixed Row Count) decides columns. Its preferred height
  is rows times (cell + spacing) plus padding. If the parent gives it less, the rows below simply
  fall outside: in a masked viewport they are cut, which is "Crafting scrunched to one row".
- **Columns follow the width.** With Flexible, a narrower pane means more rows, so a desktop grid
  that fit in 3 rows needs 5 on a Deck. Size the viewport from the content (a fitter on the grid
  inside a scroll view) and let the scroll view scroll, rather than fixing a height.
- **Visible rows** = the visible height of the grid (its rect clipped by every mask above it and by
  the screen) over (cell height + spacing). The rect audit reports it.

## Scroll views and masks

- **A `ScrollRect` needs a viewport with a mask (`RectMask2D`) and a content anchored to the top**
  (anchor y 1, pivot y 1) that is TALLER than the viewport, with `vertical` on. Content no taller
  than the viewport does not scroll; content taller with `vertical` off is cut, silently.
- **A mask hides; nothing reports it.** `RectMask2D` culls anything outside its rect
  (`CanvasRenderer.cull`). Icons, previews and buttons cut by a mask raise no text-census flag. The
  rect audit checks every graphic against its masks.
- **Nested scroll views eat the drag.** An inner ScrollRect takes drag and wheel events even on the
  axis it does not scroll; the outer one stops scrolling over it.
- **A viewport squeezed to nothing.** A fit that shrinks a scroll view below one row (the
  `WindowFit.MinListHeight` 80 / `MinViewportHeight` 60 floors) leaves one row visible and the
  player sees "scrunched", not "scrolls". Prefer giving the window the height, then the list.

## Drawing order, popups, colours

- **Sibling order is drawing order** inside a canvas: the last child draws on top and gets the
  click. A screen raised to the top covers popups that must stay above it (w644 PT-1: the "tech
  unlocked" popup went under the hub, and B closed something unseen). Keep popups last
  (`StructuredHub.Order`), or give them a nested canvas with `overrideSorting`.
- **Changing sibling order every frame** rebuilds the canvas every frame and can make overlapping
  panels flicker in z. Move only what is out of place.
- **Translucent panels show the world.** The classic windows are translucent teal-blue over space;
  an opaque replacement looks like a different game. Copy the classic skin (sprite, type, colour),
  and compare stills side by side (`ui_check.py style`).
- **A see-through sprite.** A frame sprite with a transparent middle needs its fill from the
  original style, not a new colour.

## TextMeshPro

- **Overflow modes hide loss.** `Ellipsis` and `Truncate` cut text without an error; auto-size
  shrinks it below the 9 px rule. The census reports clipped text and capital height; a long
  localized string (German, Russian) is the usual trigger, so check one long-text locale.
- **The Deck text floor is 16, and it comes back.** `UiScaler.MinLegibleFontSize` is 16 (Liberation
  Sans; Khyay holds at 15); `TextLegibilityTest` fails any text under it. A merge of develop brings
  scene texts back under it (#1151, 79adbb3db, 0908270df): after every merge into a UI branch run
  `Tools/UI/Raise Text To The Deck Legibility Floor` (`TextLegibilityCensus.cs:172`) and the test.
  `ControllerGlyphSize.FloorFontSize` is `MinLegibleFontSize` (`ControllerGlyphSize.cs:39`), so
  raising the text floor resizes the controller glyphs (floor 20 px).
- **Don't shrink a row with `localScale`.** It takes its text under 16 and its glyphs under 20 px
  (three PRs: #1275, #1281, #1284). Size from the font's cap height instead (#1284); a minimum font
  size did not hold (it measured 8.1 px).
- **Ticking numbers need fixed-pitch digits and boxes** (`<mspace=…em>`, a fixed width; #1279,
  `StationInfoLayout.cs:72` in #1282, `TechProgressPanel.cs:169`), or the row jitters as the value changes.
- **Ellipsis with a taller fallback font blanks the text** (Chinese): give the box about 5 units
  above the line (02593e3c3).
- **Text size is known after a mesh update.** `ForceMeshUpdate()` before reading `textInfo`,
  `preferredHeight` or line counts on a text changed this frame.

## Long languages and fixed-width panels (w812, Ben's German screenshots)

- **A window drawn for English keeps its width in any language.** Its width is usually a stored
  `sizeDelta.x` of a child (a layout group with `ctl --` reads each child's `sizeDelta`, not its
  preferred size), so "Zerstören" stays in an 88-unit button. Measure the words and set the widths in
  code (`FitButtonToLabel`, `FleetPanelLayout`; game repo `docs/UI-Architecture.md` §3f), never below
  the English width. Check with a test that lays the real prefab out in all 11 languages with each
  language's words and font (`Tests.UI.LongLanguagePanelsTests`: strings from `LocaleTableFile`, no
  Localization assembly needed) and fails on a mid-word break, a text wider than its box and a drawn
  overlap. When a language only fits with a shorter word, change that row (`set_rows.py`) in the same PR.
- **Stretch-anchored, rotated icons break when a button grows.** Re-anchor them to the edge first.
- **Never save `main.unity` from the editor.** It rewrites ~2300 lines of layout-driven rects, and the
  editor crashes at the "scene changed on disk" prompt when you patch the file under it. Edit in the
  editor, `SaveScene(scene, path, saveAsCopy: true)` before and after, `diff -u`, `patch --fuzz=3` the
  repo scene with the editor stopped; call `PrefabUtility.RecordPrefabInstancePropertyModifications`
  for prefab-instance edits or they are missing from the diff.
- **A tour of a new game must wait out the intro narration** (`NEW_WORLD_WAIT=75` in
  `specs/w812-german-ui`): before it the hub (Y) and I-key windows do not open, and a census of a still
  with no panel in it passes. Look at each still for the panel before trusting a PASS. Run one language
  per game; a station left selected keeps the next language's window from opening.
- **Stop only the player pids your own run started.** Matching `finalfactory` in a command line also
  matches other sandboxes' players.

## Input and focus (Deck)

- **The Deck reaches what the tour reaches.** Steam Input buttons, the trackpad cursor and R2/L2
  clicks (`docs/SteamInput.md`). A mouse-only action (hover-only tooltips, drag without a click
  path, double-click) needs a Deck route.
- **A held button changes meaning with the layer** (`panel_open`): closing a panel with B dropped
  the layer while B was down and boarded a vehicle (w644 H-2, `SteamInputBridge`).
