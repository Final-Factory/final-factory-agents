# The layout census: every element on screen, before and after

A UI change is checked against the whole screen, not only the panel it touched (w733: the minimap's
side buttons drifted off it and a slide-out covered the hotbar while each PR checked its own panel;
#1272 turned the Blueprints window opaque navy). The census writes every visible UI element with
its screen rect, colour, alpha, sprite and drawing order to a JSON file. `ui_layout.py` (beside this
file) compares two of them: new overlaps between HUD blocks, drift of anchored clusters, and the
colour and alpha of every panel that changed against a classic reference panel.

**Two kinds of element** (w742, Ben: "Put the slide out back just make it appear over the hot bar. The user can then
close it to show the hotbar again" and "the blueprint panel showing over objectives is fine since its a temporarily
opened panel"):

- **Always-on HUD**: the hotbar, the ability row, the minimap and its buttons, the slide-out toggles, the Objectives
  card, the top bar. These never overlap each other, and the anchored clusters never drift.
- **Opened panels**: a window or slide-out the player opens on purpose and can close (Blueprints, Inventory, Crafting,
  the structure panels, the slide-out flyouts, the Station panel, the hub). They may cover the HUD. They must draw on
  top, be fully visible and clickable with nothing under them catching the clicks, and closing them must give the HUD
  back.

`hud-clusters.json` `openedPanels.paths` is the list of what counts as an opened panel (path components, `*` globs).
Anything not on it is HUD. Add an entry only for something the player opens and closes; never to make a check pass.

## Take one

1. Play mode in the sandbox editor (pin it first; `editor-ops`), Game view at the target size
   (1280x800 for the Deck: a `FixedResolution` size picked by reflection, project-memory
   `editor-ui-screenshots-at-fixed-sizes-and-locales`), in a game (drive-game `recipes.md`).
2. **The whole HUD showing**: hotbar and ability row, minimap and its side buttons (`QuickButtons`,
   `QuckControls`, `OptionToggles`), every slide-out opened, the top bar, objectives, a selected
   building's panel and the Station strip, and the screen you changed open on top. Let 20 frames
   pass after the last change.
3. Run the snippet with `OUT` set to a file in your temp folder (`before.json` on the base commit,
   `after.json` on yours; the same save, size and open screens). Take a screenshot at the same
   moment (`ScreenCapture.CaptureScreenshot`) for `ui_layout.py --shot`.
4. **Close the panel you opened and take `closed.json`** (same snippet, same save): `--closed` checks that the HUD it
   covered is back where it was.

In a built player there is no `execute_code`: log the rects that matter with Deck-tour steps
`{"setup": "rect:<object name>"}` (one line each in the tour log), and `ui_layout.py` reads the
log's `rect:` lines for the cluster check. The overlap and panel checks need the census.

```csharp
// w733 layout census: every visible UI element on every screen-space canvas, written to OUT as JSON.
var OUT = @"C:\path\to\your\temp\after.json";
float sw = UnityEngine.Screen.width, sh = UnityEngine.Screen.height;
var corners = new UnityEngine.Vector3[4];
var screenRect = new UnityEngine.Rect(0, 0, sw, sh);
System.Func<UnityEngine.Transform, string> path = null;
path = t => t.parent == null ? t.name : path(t.parent) + "/" + t.name;
System.Func<UnityEngine.RectTransform, UnityEngine.Rect> onScreen = rt =>
{
  rt.GetWorldCorners(corners);
  var canvas = rt.GetComponentInParent<UnityEngine.Canvas>();
  UnityEngine.Camera cam = null;
  if (canvas != null && canvas.rootCanvas.renderMode != UnityEngine.RenderMode.ScreenSpaceOverlay) { cam = canvas.rootCanvas.worldCamera; }
  var a = UnityEngine.RectTransformUtility.WorldToScreenPoint(cam, corners[0]);
  var b = UnityEngine.RectTransformUtility.WorldToScreenPoint(cam, corners[2]);
  return UnityEngine.Rect.MinMaxRect(UnityEngine.Mathf.Min(a.x, b.x), UnityEngine.Mathf.Min(a.y, b.y),
    UnityEngine.Mathf.Max(a.x, b.x), UnityEngine.Mathf.Max(a.y, b.y));
};
System.Func<UnityEngine.Rect, UnityEngine.Rect, UnityEngine.Rect> clip = (r, by) => UnityEngine.Rect.MinMaxRect(
  UnityEngine.Mathf.Max(r.xMin, by.xMin), UnityEngine.Mathf.Max(r.yMin, by.yMin),
  UnityEngine.Mathf.Max(UnityEngine.Mathf.Max(r.xMin, by.xMin), UnityEngine.Mathf.Min(r.xMax, by.xMax)),
  UnityEngine.Mathf.Max(UnityEngine.Mathf.Max(r.yMin, by.yMin), UnityEngine.Mathf.Min(r.yMax, by.yMax)));
System.Func<UnityEngine.RectTransform, UnityEngine.Rect> visible = rt =>
{
  var v = clip(onScreen(rt), screenRect);
  for (var p = rt.parent; p != null; p = p.parent)
  {
    var m2 = p.GetComponent<UnityEngine.UI.RectMask2D>();
    var m = p.GetComponent<UnityEngine.UI.Mask>();
    if ((m2 != null && m2.isActiveAndEnabled) || (m != null && m.isActiveAndEnabled)) { v = clip(v, onScreen((UnityEngine.RectTransform)p)); }
  }
  return v;
};
System.Func<string, string> esc = s => s == null ? "" : s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", " ").Replace("\r", " ").Replace("\t", " ");
// Image y counts from the top: flip Unity's bottom-up screen y.
System.Func<UnityEngine.Rect, string> box = r => "[" + r.xMin.ToString("F1", System.Globalization.CultureInfo.InvariantCulture) + "," +
  (sh - r.yMax).ToString("F1", System.Globalization.CultureInfo.InvariantCulture) + "," +
  r.xMax.ToString("F1", System.Globalization.CultureInfo.InvariantCulture) + "," +
  (sh - r.yMin).ToString("F1", System.Globalization.CultureInfo.InvariantCulture) + "]";
var sb = new System.Text.StringBuilder();
sb.Append("{\"screen\":[" + sw + "," + sh + "],\"elements\":[\n");
var n = 0;
foreach (var g in UnityEngine.Object.FindObjectsByType<UnityEngine.UI.Graphic>(UnityEngine.FindObjectsSortMode.None))
{
  if (!g.isActiveAndEnabled || g.canvas == null || g.canvas.rootCanvas.renderMode == UnityEngine.RenderMode.WorldSpace) { continue; }
  // w761: a Graphic without a CanvasRenderer (the Technology window's "Connectors") throws in GetInheritedAlpha.
  if (g.GetComponent<UnityEngine.CanvasRenderer>() == null) { continue; }
  var alpha = g.color.a * g.canvasRenderer.GetInheritedAlpha();
  if (alpha < 0.02f || g.canvasRenderer.cull) { continue; }
  var r = onScreen(g.rectTransform);
  var v = visible(g.rectTransform);
  if (v.width * v.height < 4) { continue; }
  var sprite = "";
  var img = g as UnityEngine.UI.Image;
  if (img != null && img.sprite != null) { sprite = img.sprite.name; }
  var textProp = g.GetType().GetProperty("text");
  var text = textProp != null && textProp.PropertyType == typeof(string) ? (string)textProp.GetValue(g) : null;
  if (text != null && text.Length > 40) { text = text.Substring(0, 40); }
  // w1396: a sprite's own size and how it is drawn, for ui_layout.py shape (a Simple image drawn far off its sprite's aspect
  // is stretched: the w1386 On/Off switch, 225x150 drawn 485x23).
  var shapeInfo = "";
  if (img != null && img.sprite != null)
  {
    var ci2 = System.Globalization.CultureInfo.InvariantCulture;
    var sr = img.sprite.rect; var sb4 = img.sprite.border;
    shapeInfo = ",\"spriteSize\":[" + sr.width.ToString("F0", ci2) + "," + sr.height.ToString("F0", ci2) + "],\"spriteBorder\":[" +
      sb4.x.ToString("F0", ci2) + "," + sb4.y.ToString("F0", ci2) + "," + sb4.z.ToString("F0", ci2) + "," + sb4.w.ToString("F0", ci2) +
      "],\"imageType\":\"" + img.type + "\",\"preserveAspect\":" + (img.preserveAspect ? "true" : "false");
  }
  var sel = g.GetComponent<UnityEngine.UI.Selectable>();
  var mask = g.GetComponent<UnityEngine.UI.Mask>();
  var maskOnly = mask != null && mask.isActiveAndEnabled && !mask.showMaskGraphic;
  // w761: how each text lays out, for text_diff.py (a text that wraps or overflows after a font-size change).
  var fit = "";
  var tmp = g as TMPro.TMP_Text;
  if (tmp != null)
  {
    var ci = System.Globalization.CultureInfo.InvariantCulture;
    var rv = tmp.GetRenderedValues(true);
    fit = ",\"fontSize\":" + tmp.fontSize.ToString("F1", ci) + ",\"font\":\"" + esc(tmp.font != null ? tmp.font.name : "") +
      "\",\"lines\":" + tmp.textInfo.lineCount + ",\"overflowing\":" + (tmp.isTextOverflowing ? "true" : "false") +
      ",\"truncated\":" + (tmp.isTextTruncated ? "true" : "false") + ",\"renderedW\":" + rv.x.ToString("F1", ci) +
      ",\"rectW\":" + tmp.rectTransform.rect.width.ToString("F1", ci) + ",\"wrap\":\"" + tmp.textWrappingMode + "\"";
  }
  // w727: where the glyphs are actually drawn (a text that wraps or overflows reaches past its RectTransform box, under
  // whatever sits there); ui_layout.py covered-text reads it.
  if (tmp != null && tmp.textInfo.characterCount > 0)
  {
    var tb = tmp.textBounds;
    var ta = UnityEngine.RectTransformUtility.WorldToScreenPoint(null, tmp.transform.TransformPoint(tb.min));
    var tz = UnityEngine.RectTransformUtility.WorldToScreenPoint(null, tmp.transform.TransformPoint(tb.max));
    fit += ",\"textRect\":" + box(UnityEngine.Rect.MinMaxRect(UnityEngine.Mathf.Min(ta.x, tz.x), UnityEngine.Mathf.Min(ta.y, tz.y),
      UnityEngine.Mathf.Max(ta.x, tz.x), UnityEngine.Mathf.Max(ta.y, tz.y)));
  }
  sb.Append(n++ == 0 ? "" : ",\n");
  sb.Append("{\"path\":\"" + esc(path(g.transform)) + "\",\"kind\":\"" + g.GetType().Name + "\",\"rect\":" + box(r) +
    ",\"visible\":" + box(v) + ",\"color\":\"#" + UnityEngine.ColorUtility.ToHtmlStringRGBA(g.color) + "\",\"alpha\":" +
    alpha.ToString("F3", System.Globalization.CultureInfo.InvariantCulture) + ",\"sprite\":\"" + esc(sprite) +
    "\",\"raycast\":" + (g.raycastTarget ? "true" : "false") + ",\"selectable\":" + (sel != null && sel.IsInteractable() ? "true" : "false") +
    ",\"maskOnly\":" + (maskOnly ? "true" : "false") + ",\"canvasOrder\":" + g.canvas.rootCanvas.sortingOrder + ",\"depth\":" + g.canvasRenderer.absoluteDepth +
    (text != null ? ",\"text\":\"" + esc(text) + "\"" : "") + fit + shapeInfo + "}");
}
sb.Append("\n]}\n");
System.IO.File.WriteAllText(OUT, sb.ToString());
return n + " elements at " + sw + "x" + sh + " -> " + OUT;
```

Compiled against Unity 6000.3.19f1's `UnityEngine.CoreModule`, `UnityEngine.UIModule` and the
project's `UnityEngine.UI.dll` (w733), with TextMesh Pro for the text-fit fields (w761: `fontSize`, `font`,
`lines`, `overflowing`, `truncated`, `renderedW`, `rectW`, `wrap` on every TMP text, for `text_diff.py`; w727: `textRect`,
the drawn glyph bounds in screen pixels, for `ui_layout.py covered-text`; the snippet assumes a screen-space overlay canvas,
which is what the game uses, and the Deck tour's `setup:census:` step writes the same field). Without `textRect` the
covered-text check says "not measured".

w1396 adds `spriteSize`, `spriteBorder`, `imageType` and `preserveAspect` on every Image with a sprite, for
`ui_layout.py shape` (the Deck tour's censuses carry them, with `lines`, `fontSize` and `textRect`, from the game's w1396
change). A census without them still works with `shape --repo <game repo>`, which reads each sprite's size from its PNG
and `.meta`, skipping names that two differently shaped sprites share.

## Judged on its own: shape (w1396)

`ui_layout.py shape <census.json> [...] [--repo <game repo>]` judges each census alone, the way a player looks at it, and
prints the `Shape:` line with one line per finding:

- **STRETCHED**: an Image drawn 2x or more off its sprite's own aspect (Simple or Filled, not `preserveAspect`, no
  9-slice border). The w1386 On/Off switch, 225x150 drawn 485x23 in the Deck dock: 14.1x.
  The aspect is the element's own `rect`, not the part a mask lets show (`visible`): a list row cut in half by its
  scroll view is drawn at its shape (w1486: the Oracle shop's last row, 43x43 with 43x21 showing, read 6 STRETCHED on
  master and the branch alike before 1.29.43). A sliver under 6 px showing is not judged.
- **MOSTLY EMPTY**: a window or dialog (an `openedPanels` window or a `*Dialog*`/`*Modal*`/`*Popup*`, the element itself or
  one level under it) whose content covers under 40 % of it AND leaves one empty rectangle of 35 % or more. Text counts
  by its drawn glyphs (`textRect`, else an estimate), padded 4 px at 1080 lines. Coverage alone does not tell: on the
  w1386 tour at 1920x1080 the Cargo Hold, which looks fine, was 24 % covered with a 25 % hole; the Light Structure 30 %
  with 37 %. HUD blocks, hover cards, list rows and scroll viewports are not judged (their ragged rows read as empty).
- **WALL OF TEXT**: a text of 8 or more lines in a box under 40 % of the screen wide (needs `lines`).

Calibrated (MEASURED, w1396) on the 12 censuses in `tests/fixtures/` and the w1386 tour's 30: it flags the docked switch,
the Light Structure panel at 1920x1080 and 1280x800, the stacked circuit blocks of the w1386 bug, and the w1004 Utility
panel (not looked at); nothing else. The thresholds are a floor, not a verdict: a still the tool passes can still look
poor, and the `Eye:` line (evidence-gate `checklists/ui.md` item 27) is the check.

`execute_code` calls time out after about 30 s while the editor keeps running them. To take many censuses, register
the snippet once as a delegate (`System.AppDomain.CurrentDomain.SetData("census", (System.Func<string, string>)(OUT => { ... }))`)
and call it from later snippets (`GetData`); it lasts until the next domain reload (a script compile; entering play
mode keeps it in this project) (w761).

**Three editor-census traps (w1183, measured on beast, 2026-10-13).** (1) **Each side in a fresh play session, with the
same steps.** An after census taken in a session where windows had been dragged and the layout then reset
(`PanelLayout.ResetAll`) listed 3 window moves (Station Grid, Player Inventory, Station Core, up to 374 px); the same
code, censused in a fresh session of the same save with the same steps, gave 0. Loading the save again
(`Final Factory/Dev/Load Save`) is a fresh session; a domain reload (a compile) drops the registered delegates, so send
the snippet again. (2) **Classic before docked, every session.** `UI.Structured.StructuredLayout` keeps its docked hold
(`_holds`) across play sessions in the editor (domain reload is off on entering play mode): after a docked census, a
classic one stays docked even with `Forced = false` (measured `_holds` 2, `IsOn` true). Take 1920x1080 and 1280x800
classic first, docked last, or set `_holds` to 0 by reflection before the classic one. Read `Screen.width` inside the
census call and refuse a mismatch: one census in w1183 was written at 2534x1385 right after a size change. (3) **What
the editor adds that is not layout.** A hover tooltip following the real mouse over the Game view
(`Tooltips/Tooltip(Clone)`, which `pointer.moveto` does not clear), the "[X] to enter or exit structure" hint
(`GamePanels/MiddleInstructionText`) and the attack banner (`GamePanels/NotificationCenter`) come and go between sides
and show as 155 "under the HUD" or new window overlaps. When both sides carry them, drop those paths from both censuses
before `check` and `moves` (as the held-item icon below) and say so in the PR; never from one side only.

## Text that no longer fits (a font-size change)

A change to text sizes (the w727 Deck floor raised about 300 texts from 14 to 15/16 pt on every screen) is checked by
comparing every text's layout before and after, same save, same screens:

```sh
python "$FF_SKILLS/unity-ui/text_diff.py" before.json after.json      # one pair
python "$FF_SKILLS/unity-ui/text_diff.py" --dir <censuses> b- a-       # every b-<state>.json vs a-<state>.json
```

It lists texts with the same string whose line count grew, that overflow or are cut (ellipsis) only after, or that
are now wider than their box without wrapping. Look at each one at full size: w761 found "Component / s" and
"Intermediat / es" in the Mass Driver's filter, "Rename fold..." in Blueprints and a two-line "Game Version" in Mods
on desktop, all from the Deck floor. **Check the fit in the font the text shows at runtime**: a localized text is
drawn in `LocalizationHelper.ApplyFont`'s font (Khyay for every Latin locale), not the font its prefab names; the
filter labels were authored in Liberation Sans, where they fit, and wrapped in Khyay. A prefab test that lays out the
label in both fonts is the game repo's `RaisedLabelsFitTest`.

## What moved, and the pins (w826, w894)

**Hard rule: move only what the person asked to move.** Never move, re-anchor, restack or regroup an existing panel, HUD
element or hover panel unless the brief quotes the person asking for that exact element to move. Ben, four times in two
days: "you did more with the overall layout than i wanted"; "why is station info at the top left? i didnt tell you to move
that"; "it seems like you keep moving it to the top on the deck. I don't want that"; "put it back over the minimap, stop
moving panels around that I don't ask you to move around". Overlap, drift and colour checks do not see a move that leaves
nothing overlapping, so every move is listed, and the places he fixed are pinned:

```sh
python "$FF_SKILLS/unity-ui/ui_layout.py" moves --pair b-1920.json a-1920.json \
    --pair b-1280.json a-1280.json --pair b-docked.json a-docked.json [--move-px 4]
python "$FF_SKILLS/unity-ui/ui_layout.py" pins a-1920.json a-1280.json a-docked.json
```

- Take six censuses with the same save and the same steps: 1920x1080 at UI 0.9, 1280x800 at UI 0.8, and 1280x800 docked,
  each before and after, **with a station selected** so Station Info and the building hover card are up. In the editor,
  pick the Game view size by reflection, set `InterfaceSettingsController.UiScaleOverride` plus
  `UiScaler.Instance.UpdateUiScale(x)` (not `ApplyUiScale`, which writes the shared PlayerPrefs), and for the dock set
  `UI.Structured.StructuredLayout.Forced = true` and select the building again (`ffauto:ui.selecttile|x|z`). In a built
  player, a Deck-tour `shot` writes `<name>.layout.json`, the same census, at `-ffDeckTourSize` and `-ffDeckTourUiScale`,
  with `{"layout": "docked"}` for the dock (one layout per launch: checklist item 23).
- `moves` compares each element's rect (the RectTransform's, not the clipped part), groups what moved into the highest
  object whose every element moved by the same amount, and prints one line per HUD block (`GamePanels/X`) with its screen
  and layout (`docked` when `StructuredDock` or `StructuredStation` is on screen, else `undocked`), its outer rect before
  and after and the largest part that moved inside it. A block with nothing left on screen is listed as gone; a new block
  is named, not counted. It refuses a pair whose two censuses are of different layouts.
- Each line ends `mark: ?`. Replace it with `asked (Ben): "his words"`, from inside the brief's quotation marks and
  naming that element on that screen, or put the element back and take the after census again. `pr_evidence.py`
  (with `--brief`, or `Brief (Ben): "..."` lines in the PR) fails anything else: "not asked: justified", a quote not in
  the brief, a Deck quote on a desktop line, a pinned element whose quote does not name it (unless it only got
  taller or shorter in place, left, right and anchored edges kept: w1824), one line for several elements, and a missing
  screen or layout.
- `pins` checks [hud-pins.json](hud-pins.json) in every census, against no baseline: Station Info's bottom edge 0 to 6 %
  of the height above the ability row and over it (or, where the dock hides the row, in the bottom 30 % of the screen
  and the middle half of its width); the hover card the same over the minimap (or bottom right); the Player Inventory's
  left edge at least 2 % of the width from the screen's edge. A pin whose element is not on screen is "not shown" and
  fails too: take the census with it up. A pin changes only when Ben asks, in a harness PR with his words.
  With the `inventory-rail` toggle on (w2651, the census's `"features"`), the classic layout checks the rail's own
  places instead: the rail a column on the right under the top bar, the hover card and Crafting just left of it,
  Crafting clear of Station Info; a pin whose `when` does not hold is "not applied" there, and passes.
  **Docked, all three up at once: dock a Cargo Hold and move the pointer off every structure** (`ffauto:pointer.moveto`
  to an empty tile), as `specs/w895-info-panels/make_tour.py` does: it has an inventory (the Player Inventory is up), and
  its window and card are short. With nothing hovered, both panels describe the selection (`PanelSubject.Choose`). The
  nightly `UI-w1052-deck-layout` docked stills never show all three (w1119, 2026-10-12, seven tries): docking a Mass Driver
  or Atomic Printer hides the card under the dock window (`HoverCardFit.HideWhereCovered`, w895), Station Info and the card
  always describe one subject, and the pointer on an unpowered structure lands on its low-power warning icon (a tooltip,
  no card). The Cargo Hold census passed: 0 broken, 0 not shown.
- Measured in the editor, a new game with the tutorial objectives and a station from w813's blueprint selected:
  between 4762a5bc3 and 102e46bed (#1282) `moves` prints 7 lines, Station Info first (x -312, y -736 px at 1920x1080;
  `tests/fixtures/w826-1282-*.json`). On develop 9798f308c (`tests/fixtures/w894-develop-*.json`) `pins` breaks Station
  Info (bottom edge at 264 of 800 px) and the hover card (right edge at 358 of 1280 px) at 1280x800 docked, where w772's
  dock cluster stacks them top left, and keeps all three pins at 1920x1080 and 1280x800 undocked.

## A UI change that moves no HUD element still needs the census (w884)

`pr_evidence.py` fails a UI PR without `Moved:`, `Pinned:`, `Overlaps:`, `Alignment:` and a clip line, and the checklist says
"no way out": a PR that only changes the title screen's New Game panel and a tutorial chain was held for it. Do not look for
an `n/a`; take it once, early, with the tour that already exists: `specs/w895-info-panels/make_tour.py` (a new game with a Cargo
Hold, a Defense Platform, an Assembler and a Command Core put down, each selected, the census written beside each still).
Build the master tip and your branch with `scripts/nightly/build_player.sh` (`git branch -f x origin/master` then
`switch_branch`, the build is cached by commit; about 15 minutes each on lothdesktop-class hardware), run the tour three times per
build (`--layout classic` at 1920x1080 scale 0.9 and 1280x800 scale 0.8, `--layout docked` at 1280x800), then `ui_layout.py moves`,
`pins` and `check` on the `cargo-hold.layout.json` pairs. Measured (w884, 2026-10-10): 0 moves, 3 pins kept, 0 new overlaps, 0 px
drift, 3 tour runs of about 100 s per build. The `Clips:` line must name a video file and say where the event is in seconds.
Merge origin/master first: a landed PR (w921) changed the same panels while the builds ran, and the HUD pairs stayed valid because it
touched no HUD.

## A HUD piece the requester asked to draw over an opened panel (w835)

`ui_layout.py check` knows one layering: an opened panel over the HUD. A request for the opposite on purpose
(lothsahn, w835: with the Technology window open in the tutorial, the objectives card "on top of the technology
menu") makes it print `UNDER` for every element of the card and `NOT RESTORED` for the same elements. Both are the
request, and `pr_evidence.py` has no way out of `Opened panels:` (a count over 0 fails). What to do, measured in w835:

- `--before` is the census of the HUD **at rest** (menu closed) on the base build, never the base build's own
  open-menu census (that one makes the whole HUD under the panel show as "not restored"); `--after` is yours with
  the menu open; `--closed` is yours after closing it.
- Take that HUD piece's rows out of the open census (a copy, paths containing its block name) and run `check` again:
  the `Opened panels:` line then counts what else is under, blocked, cut off or not restored. Say in the line what you
  set aside and why, quote the request, and give the piece's own proof: `moves` between your closed census and the
  base's at-rest census prints 0.
- A pre-existing `cut off` (the Technology scroll bar handle, 6 px wide, past the top at 1920x1080) is also in the
  base build's census: say so in the line.
- Tour: `-ffSoloObjectives HandHoldy` shows the tutorial card; to see a taller later card, add
  `{"waitFor": "text:Skip", "timeout": 120}, {"click": "text:Skip"}` per step (w835 `make_tour.py --skips 6`).

## A small UI change, before and after, in two built players (w809)

The census snippet above is for the editor. For a change to one panel (w809: a Status row in the Laser Turret's window and
new rows on an item's hover card) two development players take it without `execute_code`, and the Deck tour writes
`<shot>.layout.json` for every `shot` step:

1. **The base build is a throwaway commit of the same tree.** `build_player.sh` wants HEAD at a clean 40-hex sha. Build your tip first,
   then `git checkout origin/master -- <the UI files you changed>` (scripts, the scene), commit it locally with a TEMP subject, build that,
   then `git reset --hard <your pushed tip>` (the commit was never pushed). The base build then differs from yours by exactly the UI
   change, with no second checkout to import.
2. **The same tour on both**, one after the other (the agent port is fixed), at `-ffDeckTourSize 1920x1080 -ffDeckTourUiScale 0.9` and
   `1280x800` at `0.8`: HUD at rest, each `flyout:<name>`, the hover card, your panel open and closed, and the *old* panel that shares
   code with yours (a Laser Turret for a Railgun) open and closed in both builds. Give `-ffDeckTour` and `-ffDeckTourOut` **absolute**
   paths (a relative one resolves against the player's own folder and the tour reads no steps: "could not find file").
3. **Tour traps.** The item hotbar did not show in a Deck tour (the Deck's default is the radial hotbar, `HotbarStyleSetting.Default`): add `{"setup": "hotbarstyle:bar"}` before hovering a slot, then
   `{"point": "name:ItemSlot (1) in name:BuildItems"}` (slot 1 is `ItemSlot`, slot 2 `ItemSlot (1)`; in w809's tour `hotbar.set|1|Railgun` landed in
   `ItemSlot (1)`, the first slot held a default item: read the shot). Close a docked structure panel with `{"click": "text:Close"}`; `ui.selecttile`
   on an empty tile fails. A step that fails ends the tour, so give the base build its own step list where it has no such panel.
4. **The held-item icon** (`UI Canvas/IconImage(Clone)`, the item in the player's hand) follows the tour's pointer and is in one census and not the
   other: drop it from every `.layout.json` before `check` or `moves` (it is not layout). `ui_check.py flicker` reads the `record` step's frames
   (upside down: crop in flipped coordinates).
5. **Then** `check --before <base rest> --after <your panel open> --closed <yours after Close> --touched <panel> --ref MiniInventory
   --shot <after png> --ref-shot <after png> --ref-census <after census>` (the reference window must be open in that census) and `moves --pair`
   over rest and the hover card at both sizes. A `moves` pair of the hover card lists the card as moved when its content grew: mark it.

`hud-clusters.json` must list the window as an opened panel or `check` takes it for always-on HUD and fails the *base* build the same way
(w809: the Laser Turret's window is `GamePanels/LaserTurretPanel`, which `*EntityPanel` does not match: 1 pair, 7 under the HUD, HUD
not restored at 1920x1080 before the path was added). If your census fails on the base build too, the list is the first thing to read. At
1280x800 any docked structure panel hides the quick buttons, option toggles and hotbars in both builds, and `check` prints them as "gone".

## Content added behind a research: the before is the base build in the same state (w1465)

A change that only adds content (a ship's row in the Fleet list, its tile in a crafting tab, its row on a Technology
Unlocked card) is compared with **the base build's player in the same game state**: the same tour with the same research
learned, minus the new content's own steps (its `spawn.ships`). A before taken in your own build before the unlocking
research differs by everything that research brings on master too. Measured on w1465 (2026-10-20, lothdesktop): with a
same-build before (Knights learned) against the after (Repair Packs learned, two Wardens), the fresh ui-critic marked two
findings new, the Repair Pack tile alone on the Combat tab's first row and the doubled Repair Packs card text, and `moves`
compared the Repair Packs card with the Knights card. Master b9cf5392's player on the same tour showed both findings, and
master against the branch gave 0 moves in Crafting and 0 HUD moves at all three layouts; what was left was the Fleet list
and the card growing by the new row from the same top-left. Build the base with `git branch -f <name> origin/master`,
`switch_branch`, `build_player.sh` (about 15 min), and switch back before you edit.

## Compare two

```sh
python "$FF_SKILLS/unity-ui/ui_layout.py" check --before before.json --after after.json \
    [--closed closed.json] [--shot after.png --ref-shot before.png] [--ref "Inventory"] [--clusters clusters.json]
```

It prints the lines the pull request carries (`Overlaps:`, `Opened panels:`, `Alignment:`, `Style:`) and exits
1 when any fails:

- **Overlaps**: pairs of always-on HUD blocks whose visible parts overlap (blocks are the elements' ancestors
  `--block-depth` levels under the canvas, 2 by default: `GamePanels/ActionBarParent`, `GamePanels/MinimapParent`).
  A pair in `after` that was not in `before` is a new overlap and fails. A pair that was there before and is still
  there, between blocks the change moved, is kept, and fails too: you moved them, so the overlap is yours (7f75224fa
  moved the hotbar and the slide-out toggles and left the Blueprint slide-out over the hotbar). Overlaps inside one block
  (an icon on its button) are design and are not counted. Elements of an opened panel are not counted at all: the line
  ends `N opened-panel pair(s) over the HUD, not counted here`.
- **Opened panels**: for each opened panel that covers HUD, the `Opened panels:` line says how many pairs and then
  fails, with no way out, when the panel is
  - **under** a HUD element it covers (the census's `canvasOrder`, then `depth`, say which is drawn later; w732's first
    version drew the slide-out under the hotbar's key glyphs);
  - **not clickable**: a HUD element that takes clicks (`raycast`) under the panel with no raycasting element of the
    panel above it covering the overlap (90 %), so a click would reach the hotbar;
  - **cut off** by the screen edge (an element 2 px or more past it that no mask clips);
  - **not restored**: with `--closed closed.json`, a census taken after closing the panel again, every HUD element the
    panel covered must be there and within 2 px of where it was. Without `--closed` the line says `not checked`, and
    `pr_evidence.py` does not accept that for a PR with opened-panel pairs.

  The census only sees what draws (alpha 0.02 and up). An invisible full-screen raycast catcher under a panel is
  invisible to it: with a panel open over the hotbar, also run the event-system probe (`DeckTour` `hud` block in PR
  #1287 counted 66 of 66 click points reaching the panel).
- **Alignment**: each cluster in `clusters.json` (default: [hud-clusters.json](hud-clusters.json),
  the bottom-right HUD) measures every member's edges against its anchor and the gaps between
  members. A change of more than 2 px between before and after fails. A member missing on one side
  is reported.
- **Style**: every panel (an `Image` over 2 % of the screen) that is new or whose colour, alpha or
  sprite changed is compared with the reference panel (`--ref`, a path fragment; default the
  classic Inventory window): flat fill against frame art, colour delta E, alpha. Delta E over 10, or
  an alpha off by more than 0.2 (an opaque panel where the game's are translucent), fails. With
  `--shot` the colours are sampled from the screenshots inside each panel's rect, which is what
  the player sees.
