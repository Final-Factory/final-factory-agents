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
  sb.Append(n++ == 0 ? "" : ",\n");
  sb.Append("{\"path\":\"" + esc(path(g.transform)) + "\",\"kind\":\"" + g.GetType().Name + "\",\"rect\":" + box(r) +
    ",\"visible\":" + box(v) + ",\"color\":\"#" + UnityEngine.ColorUtility.ToHtmlStringRGBA(g.color) + "\",\"alpha\":" +
    alpha.ToString("F3", System.Globalization.CultureInfo.InvariantCulture) + ",\"sprite\":\"" + esc(sprite) +
    "\",\"raycast\":" + (g.raycastTarget ? "true" : "false") + ",\"selectable\":" + (sel != null && sel.IsInteractable() ? "true" : "false") +
    ",\"maskOnly\":" + (maskOnly ? "true" : "false") + ",\"canvasOrder\":" + g.canvas.rootCanvas.sortingOrder + ",\"depth\":" + g.canvasRenderer.absoluteDepth +
    (text != null ? ",\"text\":\"" + esc(text) + "\"" : "") + fit + "}");
}
sb.Append("\n]}\n");
System.IO.File.WriteAllText(OUT, sb.ToString());
return n + " elements at " + sw + "x" + sh + " -> " + OUT;
```

Compiled against Unity 6000.3.19f1's `UnityEngine.CoreModule`, `UnityEngine.UIModule` and the
project's `UnityEngine.UI.dll` (w733), with TextMesh Pro for the text-fit fields (w761: `fontSize`, `font`,
`lines`, `overflowing`, `truncated`, `renderedW`, `rectW`, `wrap` on every TMP text, for `text_diff.py`).

`execute_code` calls time out after about 30 s while the editor keeps running them. To take many censuses, register
the snippet once as a delegate (`System.AppDomain.CurrentDomain.SetData("census", (System.Func<string, string>)(OUT => { ... }))`)
and call it from later snippets (`GetData`); it lasts until the next domain reload (a script compile; entering play
mode keeps it in this project) (w761).

## Text that no longer fits (a font-size change)

A change to text sizes (the w727 Deck floor raised about 300 texts from 14 to 15/16 pt on every screen) is checked by
comparing every text's layout before and after, same save, same screens:

```sh
python "<this skill's base directory>/text_diff.py" before.json after.json      # one pair
python "<this skill's base directory>/text_diff.py" --dir <censuses> b- a-       # every b-<state>.json vs a-<state>.json
```

It lists texts with the same string whose line count grew, that overflow or are cut (ellipsis) only after, or that
are now wider than their box without wrapping. Look at each one at full size: w761 found "Component / s" and
"Intermediat / es" in the Mass Driver's filter, "Rename fold..." in Blueprints and a two-line "Game Version" in Mods
on desktop, all from the Deck floor. **Check the fit in the font the text shows at runtime**: a localized text is
drawn in `LocalizationHelper.ApplyFont`'s font (Khyay for every Latin locale), not the font its prefab names; the
filter labels were authored in Liberation Sans, where they fit, and wrapped in Khyay. A prefab test that lays out the
label in both fonts is the game repo's `RaisedLabelsFitTest`.

## What moved (w826)

Ben, after two UI changes moved HUD pieces he had not asked about: "you did more with the overall layout than i wanted"
(the objectives card pushed under the Station strip) and "why is station info at the top left? i didnt tell you to move
that" (#1282). Overlap, drift and colour checks do not see a move that leaves nothing overlapping, so every move is listed:

```sh
python "<this skill's base directory>/ui_layout.py" moves --pair before-1920.json after-1920.json \
    --pair before-1280.json after-1280.json [--move-px 4]
```

- Take the four censuses with the same save and the same steps: 1920x1080 at UI 0.9, 1280x800 at UI 0.8. In the editor,
  pick the Game view size by reflection and set `InterfaceSettingsController.UiScaleOverride` plus
  `UiScaler.Instance.UpdateUiScale(x)`; that does not write the shared PlayerPrefs, which `ApplyUiScale` does. In a built
  player, a Deck-tour `shot` writes `<name>.layout.json`, the same census, at `-ffDeckTourSize` and `-ffDeckTourUiScale`.
- It compares each element's rect (the RectTransform's, not the clipped part), groups what moved into the highest
  object whose every element moved by the same amount, and prints one line per HUD block (`GamePanels/X`) with its
  outer rect before and after and the largest part that moved inside it. A block with nothing left on screen is listed
  as gone; a new block is named, not counted. Elements that share a path are paired in reading order.
- Each line ends `mark: ?`. Replace it with `asked (Ben): "his words"` or `not asked: justified: <why>`, or put the
  element back and take the after census again. `pr_evidence.py` fails an unmarked line, a `Moved:` line without both
  sizes, a Deck quote on a 1920x1080 line, and with `--brief` a quote that is not inside the brief's quotation marks.
- Measured in the editor (classic layout, a new game with the tutorial objectives, a station from w813's blueprint
  selected; `tests/fixtures/w826-1282-*.json`): between 4762a5bc3 and 102e46bed (#1282) it prints 7 lines, the Station
  Info box first (x -312, y -736 px at 1920x1080), then the strip's buttons and the hover card that grew with the text
  floor, and the Player Inventory 23 px lower at 1280x800. A census against itself prints 0.

## Compare two

```sh
python "<this skill's base directory>/ui_layout.py" check --before before.json --after after.json \
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
