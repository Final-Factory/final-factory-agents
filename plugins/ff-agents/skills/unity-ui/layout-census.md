# The layout census: every element on screen, before and after

A UI change is checked against the whole screen, not only the panel it touched (w733: the minimap's
side buttons drifted off it and a slide-out covered the hotbar while each PR checked its own panel;
#1272 turned the Blueprints window opaque navy). The census writes every visible UI element with
its screen rect, colour, alpha, sprite and drawing order to a JSON file. `ui_layout.py` (beside this
file) compares two of them: new overlaps between HUD blocks, drift of anchored clusters, and the
colour and alpha of every panel that changed against a classic reference panel.

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
  sb.Append(n++ == 0 ? "" : ",\n");
  sb.Append("{\"path\":\"" + esc(path(g.transform)) + "\",\"kind\":\"" + g.GetType().Name + "\",\"rect\":" + box(r) +
    ",\"visible\":" + box(v) + ",\"color\":\"#" + UnityEngine.ColorUtility.ToHtmlStringRGBA(g.color) + "\",\"alpha\":" +
    alpha.ToString("F3", System.Globalization.CultureInfo.InvariantCulture) + ",\"sprite\":\"" + esc(sprite) +
    "\",\"raycast\":" + (g.raycastTarget ? "true" : "false") + ",\"selectable\":" + (sel != null && sel.IsInteractable() ? "true" : "false") +
    ",\"maskOnly\":" + (maskOnly ? "true" : "false") + ",\"canvasOrder\":" + g.canvas.rootCanvas.sortingOrder + ",\"depth\":" + g.canvasRenderer.absoluteDepth +
    (text != null ? ",\"text\":\"" + esc(text) + "\"" : "") + "}");
}
sb.Append("\n]}\n");
System.IO.File.WriteAllText(OUT, sb.ToString());
return n + " elements at " + sw + "x" + sh + " -> " + OUT;
```

Compiled against Unity 6000.3.19f1's `UnityEngine.CoreModule`, `UnityEngine.UIModule` and the
project's `UnityEngine.UI.dll` (w733).

## Compare two

```sh
python "<this skill's base directory>/ui_layout.py" check --before before.json --after after.json \
    [--shot after.png --ref-shot before.png] [--ref "Inventory"] [--clusters clusters.json]
```

It prints the three lines the pull request carries (`Overlaps:`, `Alignment:`, `Style:`) and exits
1 when any fails:

- **Overlaps**: pairs of HUD blocks whose visible parts overlap (blocks are the elements' ancestors
  `--block-depth` levels under the canvas, 2 by default: `GamePanels/ActionBarParent`, `GamePanels/MinimapParent`, a window). A pair
  in `after` that was not in `before` is a new overlap and fails. A pair that was there before and is
  still there, between blocks the change moved, is kept, and fails too: you moved them, so the
  overlap is yours (7f75224fa moved the hotbar and the slide-out toggles and left the Blueprint
  slide-out over the hotbar). Overlaps inside one block (an icon on its button) are design and are
  not counted.
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
