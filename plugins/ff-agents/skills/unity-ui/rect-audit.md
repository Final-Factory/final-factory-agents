# The rect audit: what a player cannot see, from the live hierarchy

A quick check while you work, through the Unity MCP bridge's `execute_code` (pin your instance
first; the `editor-ops` skill). Enter play mode, set the Game view to the target size (1280x800 for
the Deck; a fixed resolution, not Free Aspect), open the screen you changed, then run the snippet
with `ROOT` set to its top object. It lists:

- **cut**: a graphic (an icon, a preview, a button, a text) partly or wholly hidden by a mask that
  cannot scroll to it, or off the screen;
- **grid**: a `GridLayoutGroup` showing fewer rows than it holds where nothing scrolls, or about one
  row at all ("scrunched to one row");
- **scroll**: a `ScrollRect` whose content is taller than its viewport but cannot scroll, or whose
  viewport is squeezed to a sliver of its content;
- **fill**: large flat fills (an `Image` over 15 % of the screen) with their colour and alpha, to
  check against the classic panels (a typed-in colour shows up here).

It is not the verdict: the editor is not the built player, and it cannot see flicker or style.
The verdict is the Deck tour with full content and `ui_check.py` (the skill, section 4 and 5).
The snippet follows the bridge's rules for `execute_code` (a method body, no `using`, fully
qualified names, `return` a string; `docs/UI-Architecture.md` §8).

```csharp
// w718 rect audit. Play mode, Game view at the target size, the screen open. Set ROOT to its top object.
var ROOT = "UI Canvas";
var go = UnityEngine.GameObject.Find(ROOT);
if (go == null) { return "no active GameObject named " + ROOT; }
float sw = UnityEngine.Screen.width, sh = UnityEngine.Screen.height;
var screenRect = new UnityEngine.Rect(0, 0, sw, sh);
var corners = new UnityEngine.Vector3[4];
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
System.Func<UnityEngine.Rect, float> area = r => UnityEngine.Mathf.Max(0, r.width) * UnityEngine.Mathf.Max(0, r.height);
// The part of rt a player can see: inside the screen and every enabled mask above it.
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
// A scroll view above rt that can scroll to what is hidden.
System.Func<UnityEngine.Transform, bool> scrolls = t =>
{
  foreach (var sr in t.GetComponentsInParent<UnityEngine.UI.ScrollRect>())
  {
    if (sr.content == null) { continue; }
    var view = sr.viewport != null ? sr.viewport : (UnityEngine.RectTransform)sr.transform;
    if ((sr.vertical && sr.content.rect.height > view.rect.height + 1) || (sr.horizontal && sr.content.rect.width > view.rect.width + 1)) { return true; }
  }
  return false;
};
var lines = new System.Collections.Generic.List<string>();
lines.Add("screen " + sw + "x" + sh + ", root " + path(go.transform));

// cut: graphics hidden by a mask that cannot scroll to them, or off screen
var cut = 0;
foreach (var g in go.GetComponentsInChildren<UnityEngine.UI.Graphic>(false))
{
  if (!g.isActiveAndEnabled || g.color.a < 0.05f || g.canvasRenderer.GetInheritedAlpha() < 0.05f) { continue; }
  var r = onScreen(g.rectTransform);
  if (area(r) < 16) { continue; }
  var share = area(visible(g.rectTransform)) / area(r);
  if (share > 0.98f) { continue; }
  var offScreen = area(clip(r, screenRect)) / area(r) < 0.98f;
  if (!offScreen && scrolls(g.transform)) { continue; }
  cut++;
  if (cut <= 40)
  {
    lines.Add("cut: " + path(g.transform) + " (" + g.GetType().Name + ") shows " + UnityEngine.Mathf.RoundToInt(share * 100) + "%" +
      (offScreen ? ", off screen" : ", masked with nothing to scroll") + " at x " + r.xMin.ToString("F0") + ".." + r.xMax.ToString("F0") +
      " y " + r.yMin.ToString("F0") + ".." + r.yMax.ToString("F0"));
  }
}
if (cut > 40) { lines.Add("cut: " + (cut - 40) + " more"); }

// grid: rows held against rows a player sees
foreach (var grid in go.GetComponentsInChildren<UnityEngine.UI.GridLayoutGroup>(false))
{
  var rt = (UnityEngine.RectTransform)grid.transform;
  var n = 0;
  foreach (UnityEngine.Transform child in rt)
  {
    var le = child.GetComponent<UnityEngine.UI.LayoutElement>();
    if (child.gameObject.activeSelf && (le == null || !le.ignoreLayout)) { n++; }
  }
  if (n == 0) { continue; }
  int columns;
  if (grid.constraint == UnityEngine.UI.GridLayoutGroup.Constraint.FixedColumnCount) { columns = grid.constraintCount; }
  else if (grid.constraint == UnityEngine.UI.GridLayoutGroup.Constraint.FixedRowCount) { columns = UnityEngine.Mathf.CeilToInt(n / (float)grid.constraintCount); }
  else { columns = UnityEngine.Mathf.Max(1, UnityEngine.Mathf.FloorToInt((rt.rect.width - grid.padding.horizontal + grid.spacing.x) / (grid.cellSize.x + grid.spacing.x))); }
  var rows = UnityEngine.Mathf.CeilToInt(n / (float)columns);
  var canvas = rt.GetComponentInParent<UnityEngine.Canvas>().rootCanvas;
  var rowPx = (grid.cellSize.y + grid.spacing.y) * canvas.scaleFactor;
  var seen = UnityEngine.Mathf.FloorToInt((visible(rt).height + grid.spacing.y * canvas.scaleFactor) / rowPx);
  var canScroll = scrolls(rt);
  if (seen < rows && (!canScroll || seen <= 1))
  {
    lines.Add("grid: " + path(rt) + " holds " + n + " in " + rows + " rows of " + columns + ", about " + seen + " visible" +
      (canScroll ? " (it scrolls, but a row at a time is not a grid)" : ", nothing scrolls to the rest"));
  }
}

// scroll: content that cannot scroll, or a sliver of a viewport
foreach (var sr in go.GetComponentsInChildren<UnityEngine.UI.ScrollRect>(false))
{
  if (sr.content == null) { continue; }
  var view = sr.viewport != null ? sr.viewport : (UnityEngine.RectTransform)sr.transform;
  float ch = sr.content.rect.height, vh = view.rect.height;
  if (ch > vh + 1 && !sr.vertical) { lines.Add("scroll: " + path(sr.transform) + " content " + ch.ToString("F0") + " units in a " + vh.ToString("F0") + " viewport, vertical scrolling off"); }
  else if (ch > 0 && vh < 0.25f * ch && vh < 100) { lines.Add("scroll: " + path(sr.transform) + " shows " + vh.ToString("F0") + " of " + ch.ToString("F0") + " units (" + UnityEngine.Mathf.RoundToInt(100 * vh / ch) + "%)"); }
}

// fill: large flat fills and their colours, for the style check
foreach (var img in go.GetComponentsInChildren<UnityEngine.UI.Image>(false))
{
  if (!img.isActiveAndEnabled || img.color.a < 0.5f) { continue; }
  var share = area(visible(img.rectTransform)) / (sw * sh);
  if (share < 0.15f) { continue; }
  lines.Add("fill: " + path(img.transform) + " #" + UnityEngine.ColorUtility.ToHtmlStringRGBA(img.color) + " sprite " +
    (img.sprite != null ? img.sprite.name : "none") + ", " + UnityEngine.Mathf.RoundToInt(share * 100) + "% of the screen");
}
if (lines.Count == 1) { lines.Add("nothing cut, squeezed or flat"); }
return string.Join("\n", lines);
```

Reading it:

- A **cut** line inside a list that scrolls is skipped; one that is left is a real loss: an icon or
  preview a player cannot reach. Off-screen lines are always real at that screen size.
- A **grid** line is the "one row" failure. Give the grid's viewport the pane's height, or let
  the window scroll whole, rather than squeezing the list (`WindowFit` floors a list at
  `MinListHeight`, 80 units, which can be a single row of a recipe grid).
- A **fill** line names the colour drawn over most of the screen. Compare it with the classic
  panel's (`#RRGGBBAA`): w644's hub drew `Shade` at `#0A121CF5` where the classic windows are
  translucent teal-blue.

Written for w718 (2026-10-08). It compiles as a method body against Unity 6000.3.19f1's
`UnityEngine.CoreModule`, `UnityEngine.UIModule` and the project's `UnityEngine.UI.dll` (Roslyn
`csc`, no warnings), but it has not yet run in a live editor: the first agent to run it records
here on which screen it ran and what it found, and fixes anything the bridge rejects.
