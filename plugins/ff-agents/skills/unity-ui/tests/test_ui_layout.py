"""Offline tests for ui_layout.py (w733, w742) on drawn censuses. Standard library only (Pillow for the on-screen colour test).

    python3 -m unittest discover -s plugins/ff-agents/skills/unity-ui/tests -p 'test_*.py' -v
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ui_layout as ul  # noqa: E402

GP = "InGameScene/UI Canvas/GamePanels"
OPENED = ul.opened_patterns(json.loads(ul.DEFAULT_CLUSTERS.read_text(encoding="utf-8")))


def el(path, rect, kind="Image", color="#FFFFFFFF", alpha=1.0, sprite="background-main", **extra):
    extra.setdefault("raycast", not extra.get("maskOnly", False))
    extra.setdefault("visible", rect)
    return dict(path=f"{GP}/{path}", kind=kind, rect=rect, color=color, alpha=alpha, sprite=sprite, **extra)


def hud(quick_x0=946, slideout=False, blueprint_backdrop=False, blueprint_window=False, window_rect=None,
        quick_on_hotbar=False, slideout_depth=None, slideout_raycast=True, inventory=True):
    """The bottom-right HUD and the Objectives card at 1280x800, as the w733 census of develop measured it, roughly.
    Drawing order is the list order, and a panel the player opens (hud-clusters.json openedPanels) draws above the HUD."""
    elements = [
        el("MinimapParent/Background", [996, 520, 1268, 792], alpha=0.71),
        el("QuickButtons/ProductionStats/Icon", [quick_x0, 700, quick_x0 + 26, 740], selectable=True),
        el("QuickButtons/Help/Icon", [quick_x0, 745, quick_x0 + 26, 785], selectable=True),
        el("QuckControls/OptionToggles/BlueprintOptions", [866, 650, 904, 690], selectable=True),
        el("ActionBarParent/Hotbars/BuildBar/ItemSlot (7)/Background", [735, 688, 770, 723]),
        el("ActionBarParent/Hotbars/BuildBar/ItemSlot (8)/Background", [795, 688, 830, 723]),
        el("ObjectivesPanel/Card", [10, 100, 420, 260], alpha=0.71),
        el("ObjectivesPanel/ScrollviewParent/ScrollView/Viewport", [10, 100, 420, 260], sprite="UIMask", maskOnly=True),
        el("CraftQueuePanels/Viewport", [0, 100, 600, 700], sprite="UIMask", maskOnly=True),
    ]
    if inventory:
        elements.append(el("InvAndCraft/InventoryPanel", [208, 6, 778, 610]))
    if quick_on_hotbar:
        elements.append(el("QuickButtons/Extra/Icon", [735, 688, 770, 723], selectable=True))
    if slideout:
        elements.append(el("QuckControls/OptionsPanels/BpControls/Controls", [696, 652, 858, 692],
                           raycast=slideout_raycast, **({"depth": slideout_depth} if slideout_depth is not None else {})))
    if blueprint_window or window_rect:
        rect = window_rect or [392, 68, 850, 444]
        shown = [max(rect[0], 0), max(rect[1], 0), min(rect[2], 1280), min(rect[3], 800)]
        elements.append(el("BlueprintPanelChild/Window", rect, visible=shown))
    if blueprint_backdrop:
        elements.append(el("BlueprintPanelChild/SolidBackdrop", [392, 68, 850, 444], color="#0D1724FA", alpha=0.98, sprite=""))
    for i, e in enumerate(elements):
        e.setdefault("depth", i + (1000 if ul.opened_prefix(e["path"], OPENED) else 0))
        e.setdefault("canvasOrder", 0)
    return {"screen": [1280, 800], "elements": elements}


class OverlapTest(unittest.TestCase):
    def test_blocks_are_two_levels_under_the_canvas(self):
        self.assertEqual(ul.block_of(f"{GP}/QuickButtons/Help/Icon", 2), f"{GP}/QuickButtons")

    def test_a_closed_hud_has_no_overlap_and_masks_do_not_count(self):
        self.assertEqual(ul.overlaps(hud(), opened=OPENED), {})

    def test_the_inventory_over_the_objectives_card_is_an_overlap_only_until_it_is_classified_as_opened(self):
        self.assertIn((f"{GP}/InvAndCraft", f"{GP}/ObjectivesPanel"), ul.overlaps(hud()))

    def test_the_full_screen_technology_panel_is_an_opened_panel_not_hud(self):
        # w752: the shipped list lacked it, so ui_layout.py counted the Technology screen as always-on HUD (4 kept
        # overlaps with the minimap, the hotbar and the quick buttons, and "HUD restored on close: no" because the panel
        # itself was gone after closing).
        census = hud()
        census["elements"].append(el("TechnologySelectionPanel/MainPanel", [0, 56, 1280, 800]))
        self.assertTrue(ul.opened_prefix(f"{GP}/TechnologySelectionPanel/MainPanel", OPENED))
        self.assertEqual(ul.overlaps(census, opened=OPENED), {})

    def test_the_blueprint_slide_out_over_the_hotbar_is_found(self):
        pairs = ul.overlaps(hud(slideout=True))
        self.assertIn((f"{GP}/ActionBarParent", f"{GP}/QuckControls"), pairs)


class Cmd:
    """Runs `ui_layout.py check` on drawn censuses and returns (exit code, printed output)."""

    @staticmethod
    def run(before, after, closed=None, extra=(), spec=None):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            args = ["check"]
            for name, census in (("before", before), ("after", after), ("closed", closed)):
                if census is None:
                    continue
                path = Path(tmp) / f"{name}.json"
                path.write_text(json.dumps(census), encoding="utf-8")
                args += [f"--{name}", str(path)]
            if spec is not None:
                path = Path(tmp) / "clusters.json"
                path.write_text(json.dumps(spec), encoding="utf-8")
                args += ["--clusters", str(path)]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ul.main(args + list(extra))
            return code, out.getvalue()


def the_line(out, name):
    return next(l for l in out.splitlines() if l.startswith(name + ":"))


class KeptOverlapTest(unittest.TestCase):
    def test_an_overlap_left_between_blocks_the_change_moved_is_kept(self):
        # Always-on HUD: the quick buttons stand on the hotbar before and after, and the change moved the hotbar.
        before = hud(quick_on_hotbar=True)
        after = hud(quick_on_hotbar=True)
        for e in after["elements"]:
            if "ActionBarParent" in e["path"]:
                e["rect"] = e["visible"] = [e["rect"][0] - 10, e["rect"][1], e["rect"][2] - 10, e["rect"][3]]
        moved = ul.moved_blocks(before, after)
        self.assertIn(f"{GP}/ActionBarParent", moved)
        self.assertNotIn(f"{GP}/MinimapParent", moved)
        code, out = Cmd.run(before, after)
        self.assertEqual(code, 1)
        self.assertIn("KEPT: ", out)

    def test_an_old_overlap_the_change_did_not_touch_is_not_kept(self):
        self.assertEqual(ul.moved_blocks(hud(quick_on_hotbar=True), hud(quick_on_hotbar=True)), set())
        code, out = Cmd.run(hud(quick_on_hotbar=True), hud(quick_on_hotbar=True))
        self.assertIn("0 new, 0 kept", out)


class BackdropTest(unittest.TestCase):
    """w959: the map view fills the screen under the HUD; the Map Controls lie on it by design."""

    def census(self, controls_x):
        return {"screen": [1280, 800], "elements": [
            dict(el("Map/Image", [0, 0, 1280, 800], alpha=1.0), depth=0, canvasOrder=0),
            dict(el("MapControls/Controls/AddMarker", [controls_x, 10, controls_x + 135, 40], selectable=True), depth=5,
                 canvasOrder=0),
        ]}

    def test_a_control_lying_on_the_map_is_not_an_overlap_with_it(self):
        before, after = self.census(500), self.census(650)
        spec = json.loads(ul.DEFAULT_CLUSTERS.read_text(encoding="utf-8"))
        self.assertEqual(ul.overlaps(after, 2, opened=OPENED, backdrops=ul.backdrop_patterns(spec)), {})
        code, out = Cmd.run(before, after)
        self.assertIn("0 new, 0 kept", out)

    def test_without_the_classification_it_still_fails(self):
        self.assertTrue(ul.overlaps(self.census(650), 2, opened=OPENED))

    def test_the_shipped_spec_lists_the_map_and_not_the_map_controls(self):
        patterns = ul.backdrop_patterns(json.loads(ul.DEFAULT_CLUSTERS.read_text(encoding="utf-8")))
        self.assertTrue(ul.opened_prefix(f"{GP}/Map/Image", patterns))
        self.assertIsNone(ul.opened_prefix(f"{GP}/MapControls/Controls/AddMarker", patterns))
        self.assertIsNone(ul.opened_prefix(f"{GP}/MinimapParent/MapImage", patterns))


class MenuBackdropTest(unittest.TestCase):
    """w1413: the Esc and title menu's Mask and LeftScrim fill the screen behind its panels; a change inside the Load
    panel's detail column read '2 kept between blocks the change moved' against them, though the menu never moved."""

    MENU = "PersistentObjects/Canvas/MainMenuPanel(Clone)"

    def census(self, name_y):
        m = self.MENU
        return {"screen": [1920, 1080], "elements": [
            dict(path=f"{m}/MenuParent/Mask", kind="Image", rect=[0, 0, 1920, 1080], visible=[0, 0, 1920, 1080],
                 color="#000000B0", alpha=0.7, sprite="", raycast=True, depth=0, canvasOrder=0),
            dict(path=f"{m}/MenuParent/LeftScrim", kind="Image", rect=[0, 0, 700, 1080], visible=[0, 0, 700, 1080],
                 color="#000000B0", alpha=0.7, sprite="", raycast=True, depth=1, canvasOrder=0),
            dict(path=f"{m}/MenuParent/PanelsParent/SaveLoadPanel/Content/Right/Name/Value", kind="Text",
                 rect=[1131, name_y, 1339, name_y + 86], visible=[1131, name_y, 1339, name_y + 86], color="#FFFFFFFF",
                 alpha=1.0, sprite="", raycast=False, depth=6, canvasOrder=0),
            dict(path=f"{m}/MenuParent/PanelsParent/SaveLoadPanel/Background", kind="Image", rect=[528, 272, 1378, 864],
                 visible=[528, 272, 1378, 864], color="#16324AF0", alpha=0.94, sprite="background-main", raycast=True,
                 depth=5, canvasOrder=0),
            dict(path=f"{m}/VersionPanel/VersionString", kind="Text", rect=[1676, 1018, 1876, 1040],
                 visible=[1676, 1018, 1876, 1040], color="#FFFFFFFF", alpha=1.0, sprite="", raycast=False, depth=2,
                 canvasOrder=0),
        ]}

    def test_the_load_panel_and_the_version_lying_on_the_menu_backdrop_are_not_overlaps(self):
        code, out = Cmd.run(self.census(487), self.census(455))
        self.assertIn("0 new, 0 kept", the_line(out, "Overlaps"))

    def test_the_shipped_spec_lists_the_menu_backdrop_and_not_its_panels(self):
        patterns = ul.backdrop_patterns(json.loads(ul.DEFAULT_CLUSTERS.read_text(encoding="utf-8")))
        self.assertTrue(ul.opened_prefix(f"{self.MENU}/MenuParent/Mask", patterns))
        self.assertTrue(ul.opened_prefix(f"{self.MENU}/MenuParent/LeftScrim", patterns))
        self.assertIsNone(ul.opened_prefix(f"{self.MENU}/MenuParent/PanelsParent/SaveLoadPanel/Background", patterns))

    def test_without_the_classification_it_still_counts_them(self):
        self.assertTrue(ul.overlaps(self.census(455), 2, opened=OPENED))


class OpenedPanelTest(unittest.TestCase):
    """w742 (Ben): a panel the player opens on purpose and can close may draw over the HUD; it must sit on top, take
    its clicks, stay on screen and give the HUD back when closed. Always-on HUD overlaps still fail."""

    def test_the_shipped_spec_classifies_the_panels_and_not_the_hud(self):
        patterns = ul.opened_patterns(json.loads(ul.DEFAULT_CLUSTERS.read_text(encoding="utf-8")))
        for path in (f"{GP}/QuckControls/OptionsPanels/BpControls/Controls", f"{GP}/InvAndCraft/InventoryPanel",
                     f"{GP}/BlueprintPanelChild/SolidBackdrop", f"{GP}/LightEntityPanel(Clone)/Window",
                     f"{GP}/StructuredStation/Background"):
            self.assertTrue(ul.opened_prefix(path, patterns), path)
        for path in (f"{GP}/QuckControls/OptionToggles/BlueprintOptions", f"{GP}/ActionBarParent/Hotbars/BuildBar",
                     f"{GP}/ObjectivesPanel/Card", f"{GP}/MinimapParent/Background", "InGameScene/UI Canvas/TopInfoPanel/Bar"):
            self.assertIsNone(ul.opened_prefix(path, patterns), path)

    def test_a_slide_out_over_the_hotbar_passes_when_it_is_on_top_clickable_and_closes_clean(self):
        # w732 / PR #1287: the pair that was a hard-coded exemption is now the general rule.
        code, out = Cmd.run(hud(), hud(slideout=True), closed=hud())
        self.assertEqual(code, 0, out)
        self.assertIn("0 new, 0 kept", the_line(out, "Overlaps"))
        # the open Inventory over the Objectives card is the other pair
        self.assertIn("2 opened-panel pair(s) over the HUD", the_line(out, "Overlaps"))
        self.assertIn("0 under the HUD, 0 not clickable, 0 cut off by the screen edge, HUD restored on close: yes",
                      the_line(out, "Opened panels"))
        self.assertIn("OPENED OVER HUD: ", out)

    def test_the_old_exemption_is_gone_from_the_spec(self):
        self.assertNotIn("byDesign", json.loads(ul.DEFAULT_CLUSTERS.read_text(encoding="utf-8")))

    def test_the_same_overlap_between_always_on_blocks_still_fails(self):
        # The quick buttons are HUD, not a panel the player opens: standing on the hotbar is a defect.
        code, out = Cmd.run(hud(), hud(quick_on_hotbar=True))
        self.assertEqual(code, 1)
        self.assertIn("NEW: ", out)
        self.assertIn("1 new", the_line(out, "Overlaps"))

    def test_a_panel_without_the_classification_counts_as_hud(self):
        code, out = Cmd.run(hud(), hud(slideout=True), spec={"clusters": []})
        self.assertEqual(code, 1)
        self.assertIn("1 new", the_line(out, "Overlaps"))

    def test_a_panel_drawn_under_the_hud_fails(self):
        # w732's first bug: the slide-out stood before the hotbar among the panels, so the hotbar showed through it.
        code, out = Cmd.run(hud(), hud(slideout=True, slideout_depth=-5), closed=hud())
        self.assertEqual(code, 1)
        self.assertIn("UNDER: ", out)
        self.assertNotIn(" 0 under the HUD", the_line(out, "Opened panels"))

    def test_a_panel_already_drawn_under_the_hud_before_is_standing(self):
        # w1475: at 1280x800 docked, master's Station Info draws over the docked window on both sides of the change;
        # that is not the change's to fix, so it is listed as standing and not counted.
        under = hud(slideout=True, slideout_depth=-5)
        code, out = Cmd.run(under, hud(slideout=True, slideout_depth=-5), closed=hud())
        self.assertEqual(code, 0, out)
        self.assertIn(" 0 under the HUD", the_line(out, "Opened panels"))
        self.assertIn("standing (on the before census too, not counted)", the_line(out, "Opened panels"))
        self.assertIn("STANDING UNDER: ", out)

    def test_a_panel_whose_graphics_ignore_clicks_leaves_the_hud_clickable_through_it(self):
        code, out = Cmd.run(hud(), hud(slideout=True, slideout_raycast=False), closed=hud())
        self.assertEqual(code, 1)
        self.assertIn("NOT CLICKABLE: ", out)

    def test_a_panel_cut_off_by_the_screen_edge_fails(self):
        code, out = Cmd.run(hud(), hud(blueprint_window=True, window_rect=[1100, 68, 1400, 444]), closed=hud())
        self.assertEqual(code, 1)
        self.assertIn("CUT OFF: ", out)
        self.assertIn("1 cut off by the screen edge", the_line(out, "Opened panels"))

    def test_a_panel_with_scrolled_content_past_the_edge_is_not_cut_off(self):
        # A scroll list's rows past the viewport are clipped by its mask, so they are not "past the screen edge".
        after = hud(blueprint_window=True)
        after["elements"].append(el("BlueprintPanelChild/List/Row (40)", [400, 300, 800, 1000], depth=1200, canvasOrder=0,
                                    visible=[400, 300, 800, 600]))
        code, out = Cmd.run(hud(), after, closed=hud())
        self.assertNotIn("CUT OFF", out)

    def test_closing_must_restore_the_hud(self):
        closed = hud()
        for e in closed["elements"]:
            if "ActionBarParent" in e["path"]:
                e["rect"] = e["visible"] = [e["rect"][0] + 40, e["rect"][1], e["rect"][2] + 40, e["rect"][3]]
        code, out = Cmd.run(hud(), hud(slideout=True), closed=closed)
        self.assertEqual(code, 1)
        self.assertIn("NOT RESTORED: ", out)

    def test_siblings_sharing_a_name_are_matched_by_place_not_order(self):
        # w1329: an objective's three tips are all ObjectivesPanel/.../TipParent/TipText; the census after the close listed
        # them in another order at the same three places, and the check said one was "not where it was".
        tip = "ObjectivesPanel/Content/ObjectiveItem(Clone)/TipParent/TipText"
        places = [[20, 140, 310, 190], [20, 194, 310, 228], [20, 231, 310, 290]]
        covered = {el(tip, places[0])["path"]: list(places)}
        closed = {"elements": [el(tip, r) for r in (places[1], places[2], places[0])]}
        self.assertEqual(ul.restored(closed, covered), [])
        closed["elements"][0] = el(tip, [20, 260, 310, 294])
        self.assertTrue(any("not where it was" in p for p in ul.restored(closed, covered)))

    def test_a_census_without_draw_order_says_it_did_not_measure(self):
        after = hud(slideout=True)
        for e in after["elements"]:
            e.pop("depth", None)
        code, out = Cmd.run(hud(), after)
        self.assertIn("NOT measured", the_line(out, "Opened panels"))

    def test_without_a_closed_census_the_restore_is_not_checked(self):
        code, out = Cmd.run(hud(), hud(slideout=True))
        self.assertIn("HUD restored on close: not checked", the_line(out, "Opened panels"))


class RealCaseTest(unittest.TestCase):
    """The two real misses of 2026-10-08 (w733), on the rects the lesson records (1280x800, UI scale 0.9, classic layout)
    rebuilt as drawn censuses: the stills of #1272 are on another machine, so the colour test uses stills synthesised
    to the measured on-screen colours (the window 23.8 from the classic Inventory, 2.1 before)."""

    def test_1272_the_blueprints_window_over_objectives_passes_the_overlap_check_and_fails_the_colour(self):
        # no Inventory window open here: two open windows over each other are the Window overlaps line's (WindowCheckTest)
        code, out = Cmd.run(hud(inventory=False), hud(blueprint_backdrop=True, inventory=False), closed=hud(inventory=False),
                            extra=["--touched", "BlueprintPanelChild"])
        self.assertEqual(code, 1)
        self.assertIn("0 new, 0 kept", the_line(out, "Overlaps"))
        self.assertIn("BlueprintPanelChild  x  ObjectivesPanel", out)
        self.assertNotIn("NEW: ", out)
        self.assertIn("ALLOWED: GamePanels/BlueprintPanelChild  x  Objectives card", out)
        self.assertIn("0 under the HUD, 0 not clickable, 0 cut off by the screen edge, HUD restored on close: yes",
                      the_line(out, "Opened panels"))
        self.assertIn("STYLE: ", out)       # the colour is what fails
        self.assertNotIn("DRIFT: ", out)

    def test_1272_still_fails_the_colour_by_delta_e_on_screen(self):
        classic_rgb, window_rgb = (48, 70, 100), (13, 23, 36)   # the classic Inventory; #0D1724 under the window's 0.98 alpha
        try:
            from PIL import Image
        except ImportError:                  # CI's python may lack Pillow: stand in for the screenshot sampling
            Image = None
        with tempfile.TemporaryDirectory() as tmp:
            classic, window = Path(tmp) / "classic.png", Path(tmp) / "after.png"
            real_sample = ul.sample
            if Image:
                Image.new("RGB", (1280, 800), classic_rgb).save(classic)
                Image.new("RGB", (1280, 800), window_rgb).save(window)
            else:
                ul.sample = lambda shot, rect: classic_rgb if str(shot).endswith("classic.png") else window_rgb
            try:
                code, out = Cmd.run(hud(), hud(blueprint_backdrop=True), closed=hud(),
                                    extra=["--touched", "BlueprintPanelChild", "--shot", str(window), "--ref-shot", str(classic)])
            finally:
                ul.sample = real_sample
        self.assertEqual(code, 1)
        self.assertRegex(the_line(out, "Style"), r"delta E 23\.\d \(on screen\)")
        self.assertIn("0 new, 0 kept", the_line(out, "Overlaps"))

    def test_1272_with_the_classic_look_would_have_passed(self):
        # clear of the Inventory window (two open windows over each other are the Window overlaps line's: WindowCheckTest)
        code, out = Cmd.run(hud(), hud(window_rect=[800, 68, 1260, 444]), closed=hud(), extra=["--touched", "BlueprintPanelChild"])
        self.assertEqual(code, 0, out)

    def test_1264_the_minimap_buttons_drift_still_fails(self):
        code, out = Cmd.run(hud(quick_x0=968), hud(quick_x0=946), closed=hud(quick_x0=946))
        self.assertEqual(code, 1)
        self.assertIn("DRIFT: bottom-right HUD: QuickButtons's left edge moved -22 px", out)
        self.assertIn("max drift 22 px", the_line(out, "Alignment"))


class ClusterTest(unittest.TestCase):
    SPEC = {"clusters": [{"name": "bottom-right HUD", "anchor": "MinimapParent",
                          "members": ["QuickButtons", "OptionToggles", "Hotbars"]}]}

    def test_buttons_moving_off_the_minimap_drift(self):
        before = ul.cluster_edges(hud(quick_x0=968), self.SPEC)
        after = ul.cluster_edges(hud(quick_x0=946), self.SPEC)
        worst, lines = ul.drift(before, after, 2.0)
        self.assertEqual(worst, 22)
        self.assertTrue(any("QuickButtons's left edge moved -22 px" in l for l in lines), lines)

    def test_a_pixel_is_within_tolerance(self):
        worst, lines = ul.drift(ul.cluster_edges(hud(quick_x0=946), self.SPEC),
                                ul.cluster_edges(hud(quick_x0=947), self.SPEC), 2.0)
        self.assertEqual((worst, lines), (1, []))

    def test_a_tour_log_gives_rects_for_built_players(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "tour.txt"
            log.write_text("  12.00    -> InGameScene/UI Canvas/GamePanels/MinimapParent active True screen x 996..1268 "
                           "y 8..280 of 1280x800\n", encoding="utf-8")
            census = ul.load(log)
            self.assertEqual(census["elements"][0]["rect"], [996.0, 520.0, 1268.0, 792.0])


class StyleTest(unittest.TestCase):
    def test_1272s_backdrop_is_new_flat_and_far_from_the_classic_panel(self):
        summaries, failures = ul.style(hud(), hud(blueprint_backdrop=True), "InventoryPanel")
        self.assertTrue(any("SolidBackdrop (new)" in s for s in summaries), summaries)
        self.assertTrue(any("art 'flat fill' vs 'background-main'" in f for f in failures), failures)

    def test_a_touched_panel_is_checked_even_unchanged_and_the_same_look_passes(self):
        summaries, failures = ul.style(hud(), hud(), "InventoryPanel", touched_fragments=["InventoryPanel"])
        self.assertEqual(failures, [])
        summaries, failures = ul.style(hud(), hud(), "InventoryPanel")
        self.assertEqual((summaries, failures), (["no panel changed colour, alpha or art"], []))

    def test_a_touched_panel_is_compared_with_its_own_look_before(self):
        # w1418: the alert tooltip as its own reference ("Style: nothing checked" until then).
        summaries, failures = ul.style(hud(), hud(), "InventoryPanel", touched_fragments=["InventoryPanel"])
        self.assertTrue(any("InvAndCraft/InventoryPanel (touched) vs" in s and "delta E 0.0" in s for s in summaries), summaries)
        self.assertEqual(failures, [])
        after = hud()
        after["elements"] = [dict(e, color="#0D1724FF") if e["path"].endswith("InventoryPanel") else e for e in after["elements"]]
        _, failures = ul.style(hud(), after, "InventoryPanel", touched_fragments=["InventoryPanel"])
        self.assertTrue(any("delta E" in f for f in failures), failures)
        summaries, _ = ul.style(None, hud(), "InventoryPanel", touched_fragments=["InventoryPanel"])
        self.assertEqual(summaries, [])

    def test_tint_colour_and_alpha_on_the_same_art(self):
        after = hud()
        after["elements"].append(el("BlueprintPanelChild", [392, 68, 850, 444], color="#0D1724FF", alpha=0.98))
        before = hud()
        before["elements"].append(el("BlueprintPanelChild", [392, 68, 850, 444], alpha=0.5))
        _, failures = ul.style(before, after, "InventoryPanel")
        self.assertTrue(any("delta E" in f for f in failures), failures)


def station_info(x0, y0, w=163, h=121):
    """The Station Info box (GamePanels/BuildInfoPanel) with a frame and two rows, at (x0, y0)."""
    return [el("BuildInfoPanel/Parent", [x0, y0, x0 + w, y0 + h], alpha=0.39),
            el("BuildInfoPanel/Parent/Title", [x0 + 8, y0 + 4, x0 + 90, y0 + 20], kind="TextMeshProUGUI"),
            el("BuildInfoPanel/Parent/Rows/Row/Label", [x0 + 8, y0 + 24, x0 + 70, y0 + 40], kind="TextMeshProUGUI"),
            el("BuildInfoPanel/Parent/Rows/Row/Label", [x0 + 8, y0 + 44, x0 + 70, y0 + 60], kind="TextMeshProUGUI")]


class MovedTest(unittest.TestCase):
    """w826: #1282 moved the Station Info box from above the ability row to the top left on every screen, and put the
    objectives card under the Station strip; Ben: "why is station info at the top left? i didnt tell you to move that"
    and "you did more with the overall layout than i wanted". Every move is listed, one line per object that moved."""

    def census(self, *extra):
        base = hud()
        base["elements"] += [e for group in extra for e in group]
        return base

    def test_nothing_moved_is_zero(self):
        result = ul.moves(self.census(station_info(558, 515)), self.census(station_info(558, 515)))
        self.assertEqual((result["moved"], result["gone"]), ([], []))

    def test_a_box_that_moved_as_a_whole_is_one_line_at_its_object(self):
        result = ul.moves(self.census(station_info(558, 515)), self.census(station_info(540, 62)))
        self.assertEqual([u["path"] for u in result["moved"]], [f"{GP}/BuildInfoPanel"])
        self.assertEqual([u["path"] for u in result["moved"][0]["parts"]], [f"{GP}/BuildInfoPanel"])
        self.assertEqual(result["moved"][0]["elements"], 4)
        line = ul.describe_move(result["moved"][0])
        self.assertEqual(line, "x -18, y -453 px (was 558,515 163x121, now 540,62 163x121)")

    def test_a_move_under_the_tolerance_is_not_listed_and_a_box_that_grew_says_so(self):
        self.assertEqual(ul.moves(self.census(station_info(558, 515)), self.census(station_info(561, 517)))["moved"], [])
        grown = ul.moves(self.census(station_info(558, 515)), self.census(station_info(558, 515, w=260)))
        self.assertEqual([u["path"] for u in grown["moved"]], [f"{GP}/BuildInfoPanel"])
        self.assertEqual([u["path"] for u in grown["moved"][0]["parts"]], [f"{GP}/BuildInfoPanel/Parent"])
        self.assertIn("x +48, y +0 px, size +97 x +0 px", ul.describe_move(grown["moved"][0]))

    def test_the_rest_of_the_hud_is_not_blamed_for_one_move(self):
        before = self.census(station_info(558, 515))
        after = self.census(station_info(540, 62))
        names = {u["path"] for u in ul.moves(before, after)["moved"]}
        self.assertFalse(any("ObjectivesPanel" in n or "ActionBarParent" in n for n in names), names)

    def test_a_live_bar_whose_fill_follows_its_value_is_not_a_move(self):
        # w1627: a production bar's Fill Area is as wide as its value; two moments of the same screen are no move.
        def bar(fill_w):
            panel = f"{GP}/DysonSegmentPanel/Parent/Content/Production/Slider"
            return [el(panel, [924, 120, 1124, 132]), el(f"{panel}/Fill Area", [930, 120, 930 + fill_w, 132]),
                    el(f"{panel}/Fill Area/Fill", [930, 120, 930 + fill_w, 132], sprite="UISprite")]
        result = ul.moves(self.census(station_info(558, 515), bar(160)), self.census(station_info(558, 515), bar(54)))
        self.assertEqual(result["moved"], [])
        moved = ul.moves(self.census(station_info(558, 515), bar(160)), self.census(station_info(540, 62), bar(54)))
        self.assertEqual([u["path"] for u in moved["moved"]], [f"{GP}/BuildInfoPanel"], "a real move is still listed")

    def test_two_objects_that_moved_differently_are_two_lines(self):
        # w722/w723: the objectives card went down under the strip while the box went to the top left.
        before = self.census(station_info(558, 515))
        after = self.census(station_info(540, 62))
        for e in after["elements"]:
            if "ObjectivesPanel" in e["path"]:
                e["rect"] = [e["rect"][0], e["rect"][1] + 69, e["rect"][2], e["rect"][3] + 69]
        names = sorted(ul.under_canvas(u["path"]) for u in ul.moves(before, after)["moved"])
        self.assertEqual(names, ["GamePanels/BuildInfoPanel", "GamePanels/ObjectivesPanel"])

    def test_a_hidden_block_is_gone_and_a_new_one_is_not_counted(self):
        before = self.census(station_info(558, 515))
        after = self.census([el("NewThing/Icon", [10, 10, 40, 40])])
        result = ul.moves(before, after)
        self.assertEqual(result["gone"], [f"{GP}/BuildInfoPanel"])
        self.assertEqual(result["new"], [f"{GP}/NewThing"])
        lines = ul.moved_lines([result], 4, "test")
        self.assertTrue(lines[0].startswith("Moved: 1 element move(s) over 4 px at 1280x800"))
        self.assertIn("GamePanels/BuildInfoPanel: gone from the screen: mark: ?", lines[1])

    def test_a_block_moved_under_another_parent_in_the_same_place_is_not_gone(self):
        # w1487: the map's arrow went from the canvas root to under GamePanels, so the windows draw over it.
        root = "InGameScene/UI Canvas"
        arrow = [dict(path=f"{root}/PointingArrow(Clone)/MapArrowGlyph", kind="Image", rect=[880, 267, 1105, 413],
                      color="#FFFFFFFF", alpha=1.0, sprite="arrow", raycast=False, visible=[880, 267, 1105, 413]),
                 dict(path=f"{root}/PointingArrow(Clone)/MapArrowGlyph/MapArrowDistance/Text", kind="TextMeshProUGUI",
                      rect=[948, 383, 1020, 401], color="#FFFFFFFF", alpha=1.0, sprite="", raycast=False,
                      visible=[948, 383, 1020, 401])]
        moved_under = [dict(e, path=e["path"].replace(f"{root}/", f"{GP}/")) for e in arrow]
        result = ul.moves(self.census(arrow), self.census(moved_under))
        self.assertEqual((result["gone"], result["new"]), ([], []))
        self.assertEqual(len(result["reparented"]), 1)
        lines = ul.moved_lines([result], 4, "test")
        self.assertTrue(lines[0].startswith("Moved: 0 element move(s)"), lines[0])
        self.assertIn("reparented", lines[1])
        # Under another parent and somewhere else: gone, as before.
        elsewhere = [dict(e, rect=[r + 300 for r in e["rect"]]) for e in moved_under]
        self.assertEqual(len(ul.moves(self.census(arrow), self.census(elsewhere))["gone"]), 1)

    def test_unnamed_siblings_are_paired_in_reading_order(self):
        # The two Row/Label texts share a path; a census lists them in any order.
        before, after = self.census(station_info(558, 515)), self.census(station_info(558, 515))
        after["elements"].reverse()
        self.assertEqual(ul.moves(before, after)["moved"], [])

    def test_moves_prints_one_line_over_both_sizes(self):
        import contextlib
        import io
        big = {"screen": [1920, 1080], "elements": station_info(873, 777)}
        big_after = {"screen": [1920, 1080], "elements": station_info(683, 64)}
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, census in (("b1", big), ("a1", big_after), ("b2", self.census(station_info(558, 515))),
                                 ("a2", self.census(station_info(540, 62)))):
                path = Path(tmp) / f"{name}.json"
                path.write_text(json.dumps(census), encoding="utf-8")
                paths.append(str(path))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ul.main(["moves", "--pair", paths[0], paths[1], "--pair", paths[2], paths[3]])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("Moved: 2 element move(s) over 4 px at 1920x1080 undocked, 1280x800 undocked", text)
        self.assertIn("- 1920x1080 undocked GamePanels/BuildInfoPanel: x -190, y -713 px", text)
        self.assertIn("- 1280x800 undocked GamePanels/BuildInfoPanel: x -18, y -453 px", text)


class RecordedMoveTest(unittest.TestCase):
    """w826, MEASURED: editor censuses of develop before #1282 (4762a5bc3) and with it (102e46bed), the classic layout, a
    new game with the tutorial objectives and a selected station (tests/fixtures/w826-1282-*.json). #1282 was the Deck's
    classic layout (w723); Ben had asked for "a new place for Station Info hover panel thing ... in the steam deck ui",
    and it moved the box from above the ability row to the top left on the desktop too. Ben, 2026-10-10: "why is
    station info at the top left? i didnt tell you to move that"."""

    def pair(self, size):
        fixtures = HERE / "fixtures"
        return (ul.load(fixtures / f"w826-1282-before-{size}.json"), ul.load(fixtures / f"w826-1282-after-{size}.json"))

    def test_the_station_info_move_is_listed_at_both_sizes_and_the_unchanged_hud_is_not(self):
        for size, shift in (("1920", "x -312, y -736 px, size +201 x -37 px"), ("1280", "x -30, y -476 px, size +190 x -35 px")):
            result = ul.moves(*self.pair(size))
            names = [ul.under_canvas(b["path"]) for b in result["moved"]]
            self.assertEqual(names[0], "GamePanels/BuildInfoPanel", (size, names))
            self.assertTrue(ul.describe_move(result["moved"][0]).startswith(shift), ul.describe_move(result["moved"][0]))
            for steady in ("GamePanels/ActionBarParent", "GamePanels/MinimapParent", "GamePanels/QuickButtons",
                           "GamePanels/ObjectivesPanel", "GamePanels/TopInfoPanel"):
                self.assertNotIn(steady, names)
            self.assertEqual(result["gone"], [])

    def test_the_census_against_itself_moves_nothing(self):
        before, _ = self.pair("1920")
        self.assertEqual(ul.moves(before, before)["moved"], [])


class PinTest(unittest.TestCase):
    """w894: the places Ben fixed himself (hud-pins.json), checked in every census whatever the PR's parent showed. The
    dock had stacked Station Info and the building hover card top left since w772 (0068ccf9b), so every before/after
    diff after it saw them "unmoved" there. Ben, 2026-10-10: "it seems like you keep moving it to the top on the deck. I
    don't want that" and "put it back over the minimap, stop moving panels around that I don't ask you to move around".
    MEASURED: editor censuses of develop 9798f308c (tests/fixtures/w894-develop-*.json)."""

    SPEC = json.loads(ul.DEFAULT_PINS.read_text(encoding="utf-8"))

    def verdicts(self, name):
        census = ul.load(HERE / "fixtures" / name)
        return {pin["name"]: ul.pin_check(census, pin)[0] for pin in self.SPEC["pins"]}

    def test_todays_docked_layout_breaks_station_info_and_the_hover_card(self):
        census = ul.load(HERE / "fixtures" / "w894-develop-1280-docked.json")
        self.assertEqual(ul.layout_of(census), "docked")
        self.assertEqual(self.verdicts("w894-develop-1280-docked.json"),
                         {"Station Info": "broken", "building hover card": "broken", "Player Inventory": "ok"})

    def test_todays_classic_layout_keeps_every_pin(self):
        for name in ("w894-develop-1920-classic.json", "w894-develop-1280-classic.json"):
            self.assertEqual(ul.layout_of(ul.load(HERE / "fixtures" / name)), "undocked")
            self.assertEqual(set(self.verdicts(name).values()), {"ok"}, name)

    def test_1282_broke_the_station_info_pin_and_its_parent_kept_it(self):
        self.assertEqual(self.verdicts("w826-1282-after-1920.json")["Station Info"], "broken")
        self.assertEqual(self.verdicts("w826-1282-before-1920.json")["Station Info"], "ok")

    def test_the_inventory_against_the_left_edge_is_broken(self):
        census = hud()
        census["elements"].append(el("MiniInventory/Content", [6, 300, 470, 560]))
        pin = next(p for p in self.SPEC["pins"] if p["name"] == "Player Inventory")
        self.assertEqual(ul.pin_check(census, pin)[0], "broken")
        census["elements"][-1].update(rect=[60, 300, 524, 560], visible=[60, 300, 524, 560])
        self.assertEqual(ul.pin_check(census, pin)[0], "ok")

    def test_a_pin_not_on_screen_is_not_shown_and_the_command_fails_on_a_broken_one(self):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ul.main(["pins", str(HERE / "fixtures" / "w894-develop-1920-classic.json"),
                            str(HERE / "fixtures" / "w894-develop-1280-docked.json")])
        text = out.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("Pinned: 3 pin(s) in 2 census(es) (1920x1080 undocked, 1280x800 docked): 2 broken, 0 not shown", text)
        self.assertIn("BROKEN 1280x800 docked (w894-develop-1280-docked.json): Station Info", text)
        self.assertIn("BROKEN 1280x800 docked (w894-develop-1280-docked.json): building hover card", text)
        self.assertEqual(ul.pin_check(hud(), self.SPEC["pins"][0])[0], "not shown")

    def test_moves_refuses_a_pair_of_different_layouts(self):
        with self.assertRaises(ValueError):
            ul.moves(ul.load(HERE / "fixtures" / "w894-develop-1280-classic.json"),
                     ul.load(HERE / "fixtures" / "w894-develop-1280-docked.json"))


SPEC = json.loads(ul.DEFAULT_CLUSTERS.read_text(encoding="utf-8"))


def screen(*elements):
    """A 1280x800 census of just these elements (path, rect) in the order given; a window draws above the HUD."""
    out = []
    for i, (path, rect) in enumerate(elements):
        e = el(path, rect)
        e.setdefault("depth", i + (1000 if ul.opened_prefix(e["path"], OPENED) else 0))
        e.setdefault("canvasOrder", 0)
        out.append(e)
    return {"screen": [1280, 800], "elements": out}


STRIP, INVENTORY, STATION_INFO = "SelectionColumnStrip", "MiniInventory/Background", "BuildInfoPanel/Parent"


def blueprint_bar(save_x0, save_y0):
    """The Blueprints window's action bar with its Save New Blueprint button at (save_x0, save_y0) and a sibling."""
    return [el("BlueprintPanelChild/ActionBar/Background", [392, 400, 850, 444]),
            el("BlueprintPanelChild/ActionBar/SaveNewBlueprint/Icon", [save_x0, save_y0, save_x0 + 120, save_y0 + 30]),
            el("BlueprintPanelChild/ActionBar/SaveNewBlueprint/Label", [save_x0 + 30, save_y0 + 6, save_x0 + 110,
                                                                         save_y0 + 24], kind="TextMeshProUGUI"),
            el("BlueprintPanelChild/ActionBar/Delete/Icon", [700, 408, 760, 438])]


def station_strip(y0):
    """The classic layout's Station controls strip (GamePanels/SelectionColumnStrip) at y0."""
    return [el("SelectionColumnStrip/Frame", [470, y0, 790, y0 + 60]),
            el("SelectionColumnStrip/Frame/Buttons/Pause", [480, y0 + 10, 520, y0 + 50])]


class OptionsTest(unittest.TestCase):
    """w1429: on w1386 Ben asked only to move the Save New Blueprint button ("move the save new blueprint button up so
    that the warning buttons show underneath... and move it so slightly to the right") and had said "keep the station
    controls where they were"; the worker's round-3 options A, B and C for 1280 each moved the station controls panel.
    Ben: "getting extremely worried you guys moved the fucking station controls panel when i told you not to twelve
    times". w826 and w894 checked the pull request's moves; nothing checked the options offered before it."""

    NAMED = ["BlueprintPanelChild/ActionBar/SaveNewBlueprint"]
    PINS = json.loads(ul.DEFAULT_PINS.read_text(encoding="utf-8"))

    def census(self, save=(400, 408), strip_y=470, info=(558, 515)):
        base = hud()
        base["elements"] += blueprint_bar(*save) + station_strip(strip_y) + station_info(*info)
        return base

    def test_an_option_that_moves_the_station_controls_is_out(self):
        check = ul.option_check(self.census(), self.census(save=(410, 360), strip_y=420), self.NAMED, self.PINS)
        self.assertEqual(check["unnamed"], ["GamePanels/SelectionColumnStrip: x +0, y -50 px"])
        self.assertEqual(check["named"], ["GamePanels/BlueprintPanelChild/ActionBar/SaveNewBlueprint: x +10, y -48 px"])

    def test_an_option_that_moves_only_the_named_button_keeps_everything_else(self):
        check = ul.option_check(self.census(), self.census(save=(410, 360)), self.NAMED, self.PINS)
        self.assertEqual(check["unnamed"], [])

    def test_naming_a_child_does_not_name_its_whole_window(self):
        before, after = self.census(), self.census()
        for e in after["elements"]:
            if "BlueprintPanelChild" in e["path"]:
                e["rect"] = [e["rect"][0], e["rect"][1] - 40, e["rect"][2], e["rect"][3] - 40]
        unnamed = ul.option_check(before, after, self.NAMED, self.PINS)["unnamed"]
        self.assertEqual(unnamed, ["GamePanels/BlueprintPanelChild: x +0, y -40 px"])
        self.assertFalse(ul.is_named(f"{GP}/BlueprintPanelChild", self.NAMED))
        self.assertTrue(ul.is_named(f"{GP}/BlueprintPanelChild/ActionBar/SaveNewBlueprint/Label", self.NAMED))
        self.assertFalse(ul.is_named(f"{GP}/BlueprintPanelChild/ActionBar/SaveNewBlueprintOld", self.NAMED))

    def test_a_gone_panel_is_out(self):
        after = self.census()
        after["elements"] = [e for e in after["elements"] if "SelectionColumnStrip" not in e["path"]]
        self.assertEqual(ul.option_check(self.census(), after, self.NAMED, self.PINS)["unnamed"],
                         ["GamePanels/SelectionColumnStrip: gone from the screen"])

    def test_the_command_puts_each_option_in_or_out_and_fails_while_one_is_out(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            paths = {}
            for name, census in (("master", self.census()), ("a", self.census(save=(410, 360), strip_y=420)),
                                 ("b", self.census(save=(410, 360)))):
                paths[name] = Path(tmp) / f"{name}.json"
                paths[name].write_text(json.dumps(census), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ul.main(["options", "--option", "A", str(paths["master"]), str(paths["a"]),
                                "--option", "B", str(paths["master"]), str(paths["b"]), "--named", self.NAMED[0]])
            self.assertEqual(code, 1)
            text = out.getvalue()
            self.assertIn("Options: 2 option(s), 1 keep every element the person did not name in place, 1 OUT (A)", text)
            self.assertIn("- A 1280x800 undocked: OUT, moves what the person did not name: GamePanels/SelectionColumnStrip", text)
            self.assertIn("- B 1280x800 undocked: keeps every unnamed element in place; named moved:", text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ul.main(["options", "--option", "B", str(paths["master"]), str(paths["b"]),
                                "--named", self.NAMED[0]])
            self.assertEqual(code, 0)

    def test_the_recorded_1282_station_info_move_is_out_unless_named(self):
        # MEASURED censuses (w826): offered as an option, #1282's layout moves Station Info and breaks its pin.
        fixtures = HERE / "fixtures"
        before, after = ul.load(fixtures / "w826-1282-before-1920.json"), ul.load(fixtures / "w826-1282-after-1920.json")
        unnamed = ul.option_check(before, after, [], self.PINS)["unnamed"]
        self.assertTrue(any(u.startswith("GamePanels/BuildInfoPanel") for u in unnamed), unnamed)
        self.assertTrue(any(u.startswith("pin Station Info broken") for u in unnamed), unnamed)
        named = ul.option_check(before, after, ["BuildInfoPanel"], self.PINS)["unnamed"]
        self.assertFalse(any("BuildInfoPanel" in u or "Station Info" in u for u in named), named)


class WindowOverlapTest(unittest.TestCase):
    """w981: `overlaps` counted only always-on HUD blocks, so the Station strip standing 11 px over the Player Inventory
    (Deck classic, 1280x800 UI 0.8, a Cargo Hold in reach; #1444, w961) was reported as 0 and the w978 worker measured the
    rects by hand. Ben, w873: "yes put the station panel controls above station info and it should be over the player
    inventory": that one pair, with the strip above Station Info, is allow-listed; every other pair is reported."""

    def found(self, census):
        return ul.window_overlaps(census, SPEC)

    def test_the_strip_left_of_station_info_over_the_inventory_is_not_allowed(self):
        # the w978 combined case, the rects measured from the built player: strip 193..482 x 713..791, inventory 26..489 x 448..724
        census = screen((INVENTORY, [26, 448, 489, 724]), (STRIP, [193, 713, 482, 791]), (STATION_INFO, [489, 639, 773, 725]))
        (v,) = self.found(census)
        self.assertEqual(v["status"], "not allowed")
        self.assertEqual([round(x) for x in v["rect"]], [193, 713, 482, 724])
        self.assertEqual({v["a"], v["b"]}, {f"{GP}/MiniInventory", f"{GP}/{STRIP}"})
        text = ul.window_overlap_text(v, SPEC)
        self.assertIn("Player Inventory (GamePanels/MiniInventory)", text)
        self.assertIn("Station controls strip (GamePanels/SelectionColumnStrip)", text)
        self.assertIn("overlap rect 193,713 to 482,724 (289x11 px)", text)

    def test_the_strip_above_station_info_over_the_inventory_is_ben_w873(self):
        # develop before w961: the strip stands right above Station Info, centred on it, over the inventory's right edge
        census = screen((INVENTORY, [26, 448, 466, 724]), (STRIP, [444, 536, 818, 626]), (STATION_INFO, [489, 639, 773, 725]))
        (v,) = self.found(census)
        self.assertEqual(v["status"], "allowed")
        self.assertIn("yes put the station panel controls above station info and it should be over the player inventory", v["why"])
        self.assertEqual([round(x) for x in v["rect"]], [444, 536, 466, 626])

    def test_the_allowance_follows_the_words_not_the_pair(self):
        # the same strip and inventory, but Station Info is not on screen or the strip is not above it: not allowed
        base = [(INVENTORY, [26, 448, 489, 724]), (STRIP, [444, 536, 818, 626])]
        self.assertEqual(self.found(screen(*base))[0]["status"], "not allowed")
        beside = base + [(STATION_INFO, [900, 639, 1100, 725])]
        self.assertEqual(self.found(screen(*beside))[0]["status"], "not allowed")

    def test_the_strip_over_station_info_or_a_cargo_hold_is_not_allowed(self):
        census = screen((STATION_INFO, [489, 639, 773, 725]), (STRIP, [444, 700, 818, 791]),
                        ("CargoEntityPanel/MainPanel", [84, 176, 436, 382]), ("SelectionColumnStrip/Hint", [300, 300, 440, 330]))
        pairs = {(ul.under_canvas(v["a"]), ul.under_canvas(v["b"]), v["status"], v["kind"]) for v in self.found(census)}
        self.assertEqual(pairs, {
            ("GamePanels/BuildInfoPanel", "GamePanels/SelectionColumnStrip", "not allowed", "window x HUD"),
            ("GamePanels/CargoEntityPanel", "GamePanels/SelectionColumnStrip", "not allowed", "window x window")})

    def test_a_structure_window_over_station_info_is_the_layer_order(self):
        # w2150: a critic flagged the Station Grid and Cargo Hold over Station Info at 1280x800 (w1911/w1966) and a worker
        # built a two-request fix; Ben: "Station UI is a higher layer than tutorial or station info"
        for window in ("StationGridEntityPanel/MainPanel", "CargoEntityPanel/MainPanel", "StructuredDock/Frame"):
            (v,) = self.found(screen((STATION_INFO, [489, 639, 773, 725]), (window, [400, 300, 700, 700])))
            self.assertEqual(v["status"], "allowed", window)
            self.assertIn("Think of it in layers", v["why"])

    def test_the_layer_order_does_not_allow_two_windows_over_each_other(self):
        census = screen(("CargoEntityPanel/MainPanel", [84, 176, 436, 382]), ("StationGridEntityPanel/MainPanel", [300, 300, 700, 600]))
        (v,) = self.found(census)
        self.assertEqual(v["status"], "not allowed")

    def test_two_windows_over_each_other_are_found_and_named(self):
        # 1920x1080 classic, the Player Inventory over a Station Grid panel (a census of #1444)
        census = screen((INVENTORY, [500, 500, 1000, 620]), ("StationGridEntityPanel/MainPanel", [924, 300, 1200, 600]))
        (v,) = self.found(census)
        self.assertEqual(v["status"], "not allowed")
        self.assertIn("Station Grid (GamePanels/StationGridEntityPanel)", ul.window_overlap_text(v, SPEC))
        self.assertEqual([round(x) for x in v["rect"]], [924, 500, 1000, 600])

    def test_a_window_over_the_objectives_card_is_ben_w742_and_w813(self):
        census = screen(("ObjectivesPanel/Card", [10, 100, 420, 260]), ("BlueprintPanelChild/Window", [200, 68, 600, 444]))
        (v,) = self.found(census)
        self.assertEqual(v["status"], "allowed")
        self.assertIn("game Ui panels should just show over top of them", v["why"])

    def test_a_window_over_the_minimap_or_station_info_is_reported(self):
        census = screen(("MinimapParent/Background", [996, 520, 1268, 792]), ("BlueprintPanelChild/Window", [900, 500, 1100, 700]),
                        (STATION_INFO, [489, 639, 773, 725]), ("InvAndCraft/InventoryPanel", [400, 600, 600, 760]))
        statuses = {(ul.under_canvas(v["a"]), ul.under_canvas(v["b"])): v["status"] for v in self.found(census)}
        self.assertEqual(set(statuses.values()), {"not allowed"})
        self.assertIn(("GamePanels/BlueprintPanelChild", "GamePanels/MinimapParent"), statuses)
        self.assertIn(("GamePanels/BuildInfoPanel", "GamePanels/InvAndCraft/InventoryPanel"), statuses)

    def test_the_inventory_and_crafting_windows_are_two_windows_not_their_bounding_box(self):
        # w1911: GamePanels/InvAndCraft holds the Crafting window (UtilityPanel) and the Inventory window (InventoryPanel) side by
        # side, and `InvAndCraft` as an opened-panel path made them ONE window, the union of both: Station Info standing in the
        # gap between them (touching neither) was reported as covered ("InvAndCraft x Station Info", 3440x1440 and 1280x800
        # censuses of master 3ae973117b, a Command Core selected, the Inventory key pressed).
        census = screen(("InvAndCraft/UtilityPanel", [100, 100, 400, 400]), ("InvAndCraft/InventoryPanel", [600, 100, 900, 400]),
                        (STATION_INFO, [450, 300, 550, 380]))
        self.assertEqual(self.found(census), [])
        # and the same Station Info standing under the Crafting window is reported, naming that window
        census = screen(("InvAndCraft/UtilityPanel", [100, 100, 400, 400]), ("InvAndCraft/InventoryPanel", [600, 100, 900, 400]),
                        (STATION_INFO, [350, 300, 450, 380]))
        (v,) = self.found(census)
        self.assertEqual(v["status"], "not allowed")
        self.assertEqual({ul.under_canvas(v["a"]), ul.under_canvas(v["b"])},
                         {"GamePanels/BuildInfoPanel", "GamePanels/InvAndCraft/UtilityPanel"})

    def test_a_building_panel_inside_the_docks_frame_is_hosted_not_an_overlap(self):
        # a docked census of #1444: the Station Core panel is the dock's tab, inside StructuredDock's frame
        census = screen(("StructuredDock", [751, 59, 1270, 256]), ("StationCoreEntityPanel/MainPanel/Content/Text", [772, 96, 1134, 231]))
        (v,) = self.found(census)
        self.assertEqual(v["status"], "hosting")
        self.assertIn("docs/UI-Architecture.md", v["why"])

    def test_a_docked_turret_window_whose_entity_panel_has_another_name_is_hosted(self):
        # w1684, 1280x800 docked: the Railgun's LaserTurretEntityPanel sits on the object LaserTurretPanel, inside the
        # dock's frame; `*EntityPanel` alone read the pair as KEPT when the window grew by its Connector Inventory row
        census = screen(("StructuredDock", [751, 59, 1270, 307]), ("LaserTurretPanel/MainPanel", [771, 107, 1068, 299]))
        (v,) = self.found(census)
        self.assertEqual(v["status"], "hosting")

    def test_always_on_hud_pairs_stay_overlaps_not_window_overlaps(self):
        census = hud(quick_on_hotbar=True)
        self.assertEqual([v for v in self.found(census) if "Hotbars" in v["example"][1] and "QuickButtons" in v["example"][0]], [])
        self.assertEqual(len(ul.overlaps(census, opened=OPENED)), 1)

    def test_each_allowed_entry_carries_the_requesters_words(self):
        for entry in SPEC["windowOverlaps"]["allowed"]:
            self.assertTrue(entry["who"] and all('"' in quote for quote in entry["who"]), entry)
        for host in SPEC["windowOverlaps"]["hosting"]:
            self.assertTrue(host["source"] and host["tenants"], host)

    def test_an_unknown_condition_is_an_error_not_a_silent_pass(self):
        spec = json.loads(json.dumps(SPEC))
        spec["windowOverlaps"]["allowed"][0]["when"] = {"nearby": "BuildInfoPanel"}
        census = screen((INVENTORY, [26, 448, 489, 724]), (STRIP, [193, 713, 482, 791]))
        with self.assertRaises(ValueError):
            ul.window_overlaps(census, spec)


class WindowCheckTest(unittest.TestCase):
    """The census pair: a window overlap that is new, or kept between windows the change moved, fails; one both censuses
    show and the change did not touch is listed as standing."""

    INVENTORY_BOX = [26, 448, 489, 724]
    BEFORE = [(INVENTORY, [26, 448, 466, 724]), (STRIP, [444, 536, 818, 626]), (STATION_INFO, [489, 639, 773, 725])]

    def test_1444_moves_the_strip_onto_the_inventory_and_fails(self):
        after = screen((INVENTORY, [26, 448, 466, 724]), (STRIP, [193, 713, 482, 791]), (STATION_INFO, [489, 639, 773, 725]))
        code, out = Cmd.run(screen(*self.BEFORE), after)
        self.assertEqual(code, 1)
        self.assertIn("1 not allowed after, 0 before, 1 new, 0 kept", the_line(out, "Window overlaps"))
        self.assertIn("  NEW: Player Inventory (GamePanels/MiniInventory)  x  Station controls strip", out)
        self.assertIn("overlap rect 193,713 to 466,724 (273x11 px)", out)
        self.assertIn("0 new, 0 kept", the_line(out, "Overlaps"))

    def test_the_allowed_overlap_before_is_listed_and_does_not_fail(self):
        code, out = Cmd.run(screen(*self.BEFORE), screen(*self.BEFORE))
        self.assertEqual(code, 0, out)
        self.assertIn("0 not allowed after, 0 before, 0 new, 0 kept between windows the change moved, 0 standing; 1 allow-listed",
                      the_line(out, "Window overlaps"))
        self.assertIn("  ALLOWED: Player Inventory", out)

    def test_1447_moves_the_inventory_and_leaves_the_overlap_kept(self):
        strip_left = [(STRIP, [193, 713, 482, 791]), (STATION_INFO, [489, 639, 773, 725])]
        before = screen((INVENTORY, [3, 448, 466, 724]), *strip_left)
        after = screen((INVENTORY, self.INVENTORY_BOX), *strip_left)
        code, out = Cmd.run(before, after)
        self.assertEqual(code, 1)
        self.assertIn("0 new, 1 kept between windows the change moved, 0 standing", the_line(out, "Window overlaps"))
        self.assertIn("  KEPT: ", out)

    def test_an_overlap_neither_window_moved_stands_and_does_not_fail(self):
        census = screen((INVENTORY, self.INVENTORY_BOX), (STRIP, [193, 713, 482, 791]), (STATION_INFO, [489, 639, 773, 725]))
        code, out = Cmd.run(census, census)
        self.assertEqual(code, 0, out)
        self.assertIn("0 new, 0 kept between windows the change moved, 1 standing", the_line(out, "Window overlaps"))
        self.assertIn("  STANDING: ", out)

    def test_parts_moved_inside_a_window_leave_an_unchanged_overlap_standing(self):
        # w1058, game PR #1512: one row added inside the full-screen Technology screen moved its inner parts; its
        # overlaps with the HUD were the same rects before and after, and were called kept.
        others = [(STRIP, [193, 713, 482, 791]), (STATION_INFO, [489, 639, 773, 725])]
        before = screen((INVENTORY, self.INVENTORY_BOX), ("MiniInventory/Content/Row", [40, 500, 200, 520]), *others)
        after = screen((INVENTORY, self.INVENTORY_BOX), ("MiniInventory/Content/Row", [40, 540, 200, 560]), *others)
        code, out = Cmd.run(before, after)
        self.assertEqual(code, 0, out)
        self.assertIn("0 new, 0 kept between windows the change moved, 1 standing", the_line(out, "Window overlaps"))

    def test_overlaps_command_reports_every_window_overlap_and_fails_on_one(self):
        import contextlib
        import io
        census = screen((INVENTORY, self.INVENTORY_BOX), (STRIP, [193, 713, 482, 791]), (STATION_INFO, [489, 639, 773, 725]))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "census.json"
            path.write_text(json.dumps(census), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ul.main(["overlaps", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("0 overlapping block pairs between always-on HUD blocks", out.getvalue())
        self.assertIn("1 window overlap(s) not allowed, 0 allow-listed", out.getvalue())
        self.assertIn("NOT ALLOWED: Player Inventory (GamePanels/MiniInventory)  x  Station controls strip", out.getvalue())


class RecordedWindowTest(unittest.TestCase):
    """w981, on censuses of built development players of #1444's head (64482cf0b, w961), 1280x800 UI 0.8 and 1920x1080
    UI 0.9 classic, a Cargo Hold / Command Core in reach (specs/w961-station-panel-left/run_tour.sh, NOTUT=1). The old
    `overlaps` printed 0 block pairs on every one of them."""

    def census(self, name):
        return ul.load(HERE / "fixtures" / name)

    def test_the_station_strip_over_the_player_inventory_is_reported_with_its_rect(self):
        census = self.census("w981-1444-1280-classic-cargo-hold-locked.json")
        self.assertEqual(ul.overlaps(census, opened=OPENED), {})
        (v,) = ul.window_overlaps(census, SPEC)
        self.assertEqual(v["status"], "not allowed")
        self.assertEqual([round(x) for x in v["rect"]], [193, 713, 466, 724])
        self.assertIn("Player Inventory (GamePanels/MiniInventory)  x  Station controls strip (GamePanels/SelectionColumnStrip)",
                      ul.window_overlap_text(v, SPEC))

    def test_two_windows_over_each_other_at_1920_are_reported(self):
        (v,) = ul.window_overlaps(self.census("w981-1444-1920-classic-flying.json"), SPEC)
        self.assertEqual(v["status"], "not allowed")
        self.assertEqual({ul.under_canvas(v["a"]), ul.under_canvas(v["b"])},
                         {"GamePanels/MiniInventory", "GamePanels/StationGridEntityPanel"})

    def test_develop_before_1444_has_the_strip_over_the_inventory_that_ben_w873_asked_for(self):
        # develop 84dc2f03f, the same tour: the strip stands above Station Info over the inventory's right edge, 22x90 px
        census = self.census("w981-develop-84dc2f03f-1280-classic-cargo-hold-locked.json")
        (v,) = ul.window_overlaps(census, SPEC)
        self.assertEqual(v["status"], "allowed")
        self.assertEqual([round(x) for x in v["rect"]], [444, 536, 466, 626])

    def test_develop_to_1444_is_a_new_window_overlap_and_the_old_check_saw_nothing(self):
        before = self.census("w981-develop-84dc2f03f-1280-classic-cargo-hold-locked.json")
        after = self.census("w981-1444-1280-classic-cargo-hold-locked.json")
        self.assertEqual(ul.overlaps(before, opened=OPENED), ul.overlaps(after, opened=OPENED))
        diff = ul.window_diff(before, after, SPEC)
        self.assertEqual((len(diff["new"]), len(diff["kept"]), len(diff["standing"])), (1, 0, 0))
        code, out = Cmd.run(before, after)
        self.assertEqual(code, 1)
        self.assertIn("1 not allowed after, 0 before, 1 new, 0 kept", the_line(out, "Window overlaps"))
        self.assertIn("0 new, 0 kept", the_line(out, "Overlaps"))


    def test_w1004_repeated_inventory_slots_are_no_move_and_develop_s_overlaps_stand(self):
        # w1004 (game PR #1466, a glyph colour change): the same tour on develop 59713ef45 and the PR; `moves` found 0
        # moves, but keyed by path alone the Player Inventory's item-slot(Clone) siblings read as moved 300-400 px and
        # develop's three window overlaps were called kept between windows the change moved
        before = self.census("w1004-develop-59713ef45-1280-classic-cargo-hold.json")
        after = self.census("w1004-1466-1280-classic-cargo-hold.json")
        self.assertEqual(ul.moves(before, after)["moved"], [])
        self.assertEqual(ul.moved_units(before, after, SPEC), set())
        diff = ul.window_diff(before, after, SPEC)
        # w1911: four pairs, not three: the Crafting and Inventory windows are two windows now, each against the Station Grid
        self.assertEqual((len(diff["new"]), len(diff["kept"]), len(diff["standing"])), (0, 0, 4))


class RepeatedSiblingsTest(unittest.TestCase):
    def test_siblings_that_share_a_path_are_matched_in_reading_order(self):
        def census():
            c = hud()
            for i in range(3):
                c["elements"].append(el("MiniInventory/Content/Inventory/item-slot(Clone)/Background",
                                        [600 + 38 * i, 320, 625 + 38 * i, 345], depth=2000 + i, canvasOrder=0))
            return c

        self.assertEqual(ul.moved_blocks(census(), census()), set())
        self.assertEqual(ul.moved_units(census(), census(), SPEC), set())
        moved = census()
        for e in moved["elements"]:
            if "item-slot" in e["path"]:
                e["rect"] = e["visible"] = [e["rect"][0] + 10, 320, e["rect"][2] + 10, 345]
        self.assertEqual(ul.moved_blocks(census(), moved), {f"{GP}/MiniInventory"})


class CoveredTextTest(unittest.TestCase):
    """w727: the Technology tab's "Excess Research 0.0" label wrapped to a second line that ran under the hub's tab bar. Its
    RectTransform box was clear of the bar, so every rect check passed; the census now holds `textRect`, the drawn glyph bounds."""
    HUB = "InGameScene/UI Canvas/StructuredHub/Tab"

    def census(self, text_rect, bar_alpha=1.0, bar_depth=20, text_extra=None):
        label = dict(path=f"{self.HUB}/Technology/Queue/Excess Research", kind="TextMeshProUGUI", rect=[40, 90, 240, 112],
                     visible=[40, 90, 240, 112], color="#FFFFFFFF", alpha=1.0, sprite="", raycast=False, selectable=False,
                     maskOnly=False, canvasOrder=0, depth=10, text="Excess Research 0.0", textRect=text_rect)
        label.update(text_extra or {})
        bar = dict(path="InGameScene/UI Canvas/StructuredHub/TabBar/Background", kind="Image", rect=[0, 40, 1280, 100],
                   visible=[0, 40, 1280, 100], color="#101820FF", alpha=bar_alpha, sprite="background-main", raycast=True,
                   selectable=False, maskOnly=False, canvasOrder=0, depth=bar_depth)
        return {"screen": [1280, 800], "elements": [label, bar]}

    def test_a_label_whose_drawn_text_reaches_under_the_bar_is_covered(self):
        found = ul.covered_text(self.census([40, 70, 200, 112]), OPENED)
        self.assertEqual(1, len(found))
        self.assertEqual("Excess Research 0.0", found[0]["text"])
        self.assertGreater(found[0]["share"], 0.2)
        self.assertIn("TabBar/Background", found[0]["by"])

    def test_the_same_label_clear_of_the_bar_is_not(self):
        self.assertEqual([], ul.covered_text(self.census([40, 104, 200, 126]), OPENED))

    def test_a_bar_drawn_below_the_text_does_not_cover_it(self):
        self.assertEqual([], ul.covered_text(self.census([40, 70, 200, 112], bar_depth=5), OPENED))

    def test_a_translucent_element_does_not_cover_it(self):
        self.assertEqual([], ul.covered_text(self.census([40, 70, 200, 112], bar_alpha=0.5), OPENED))

    def test_a_hollow_selection_frame_does_not_cover_the_text_inside_it(self):
        # the real Technology census (w727): the selected tile's orange `SelectionFrame` (sprite TechDependencyBorder) is a ring
        # whose rect holds the tile's own cost text
        census = self.census([40, 70, 200, 112])
        census["elements"][1].update(path=census["elements"][1]["path"].replace("TabBar/Background", "TechButton/SelectionFrame"),
                                     sprite="TechDependencyBorder")
        self.assertEqual([], ul.covered_text(census, OPENED))

    def test_a_census_without_text_bounds_is_not_measured(self):
        census = self.census([40, 70, 200, 112])
        del census["elements"][0]["textRect"]
        self.assertEqual([], ul.covered_text(census, OPENED))

    def test_a_masked_text_is_skipped(self):
        self.assertEqual([], ul.covered_text(self.census([40, 70, 200, 112], text_extra={"visible": [40, 100, 240, 112]}), OPENED))

    def test_the_command_exits_one_on_a_covered_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps(self.census([40, 70, 200, 112])), encoding="utf-8")
            self.assertEqual(1, ul.main(["covered-text", str(path)]))
            path.write_text(json.dumps(self.census([40, 104, 200, 126])), encoding="utf-8")
            self.assertEqual(0, ul.main(["covered-text", str(path)]))


class ShapeTest(unittest.TestCase):
    """w1396: what a player calls obviously broken, judged on one census. The fixtures are the w1386 Deck tour's censuses of
    the stills Ben answered with "the light panel is really messed up obviously" (2026-10-16), trimmed to the windows."""

    SPRITES = {"SwitchOn": (225, 150, False), "SwitchOff": (225, 150, False), "item-slot": (64, 64, False),
               "background-main": (64, 64, True), "borderless-primary": (64, 64, True), "x-button": (64, 64, False)}

    @staticmethod
    def fixture(name):
        return ul.load(HERE / "fixtures" / f"{name}.json")

    def test_the_docked_light_switch_drawn_as_a_bar_is_stretched(self):
        found = ul.shape(self.fixture("w1386-docked-lamp"), self.SPRITES)["stretched"]
        self.assertEqual([s["path"].split("/")[-1] for s in found], ["Switch"])
        self.assertGreater(found[0]["ratio"], 10)  # 225x150 drawn 485x23: 14x off its own aspect

    # w2102 (Ben, 2026-10-26: "the overdriver bonus and production icons are stretched"): the docked Station Grid's square
    # 256x256 bonus icons drawn 34x20 px, 1.67x off their aspect, which the 2x line passed. The after census draws them 20x20.
    def test_small_icons_squashed_under_two_x_are_stretched(self):
        found = ul.shape(self.fixture("w2102-docked-bonus-icons-before"), {})["stretched"]
        self.assertEqual(sorted(s["sprite"] for s in found), ["Tex_skill_03", "Tex_skill_63"])
        self.assertTrue(all(1.6 < s["ratio"] < ul.STRETCH_RATIO for s in found))
        self.assertEqual(ul.shape(self.fixture("w2102-docked-bonus-icons-after"), {})["stretched"], [])

    def test_a_big_image_off_by_the_same_ratio_is_not(self):
        census = self.fixture("w2102-docked-bonus-icons-before")
        for e in census["elements"]:
            x0, y0, x1, y1 = e["rect"]
            e["rect"] = e["visible"] = [x0, y0, x0 + (x1 - x0) * 4, y0 + (y1 - y0) * 4]  # 136x81: no longer an icon
        self.assertEqual(ul.shape(census, {})["stretched"], [])

    def test_the_same_switch_at_its_own_shape_is_not(self):
        found = ul.shape(self.fixture("w1386-1920-lamp"), self.SPRITES)["stretched"]
        self.assertEqual(found, [])  # 36x24 at 1920x1080

    def test_a_switch_that_keeps_its_aspect_or_is_sliced_is_not_stretched(self):
        census = self.fixture("w1386-docked-lamp")
        switch = next(e for e in census["elements"] if e["path"].endswith("/Switch"))
        switch["preserveAspect"] = True
        self.assertEqual(ul.shape(census, self.SPRITES)["stretched"], [])
        switch["preserveAspect"] = False
        self.assertEqual(ul.shape(census, dict(self.SPRITES, SwitchOn=(225, 150, True)))["stretched"], [])

    def test_the_census_sprite_size_wins_over_the_repo(self):
        census = self.fixture("w1386-docked-lamp")
        switch = next(e for e in census["elements"] if e["path"].endswith("/Switch"))
        switch["spriteSize"], switch["spriteBorder"], switch["imageType"] = [485, 23], [0, 0, 0, 0], "Simple"
        self.assertEqual(ul.shape(census, self.SPRITES)["stretched"], [])

    def test_an_unknown_sprite_is_named_not_judged(self):
        out = ul.shape(self.fixture("w1386-docked-lamp"), {})
        self.assertEqual(out["stretched"], [])
        self.assertIn("SwitchOn", out["unknown_sprites"])

    # w1468 (PR #1937): the projector panel's side, turn and reset buttons, like the game's TabSettingsButton and
    # MainMenuButton, put `transparent-block` (512x512, every pixel alpha 0) behind them as their hit area, drawn 91x32
    # at colour alpha 1. It draws nothing, and the shape line read 45 STRETCHED.
    QUIET = {"path": f"{GP}/BlueprintProjectorEntityPanel/MainPanel/Content/Sides/Side1", "kind": "Image",
             "rect": [453, 468, 544, 501], "visible": [453, 468, 544, 501], "color": "#FFFFFFFF", "alpha": 1.0,
             "sprite": "transparent-block", "spriteSize": [512, 512], "spriteBorder": [0, 0, 0, 0], "imageType": "Sliced",
             "preserveAspect": False}

    # w1486 (PR #1936): the Oracle shop's last row, half under its scroll view's mask at 1920x1080. The census gives the
    # icon's own rect and the part that shows; the shape read the clipped part as the drawn shape (6 STRETCHED, master too).
    CLIPPED = {"path": f"{GP}/OracleEntityPanelParent/OraclePanel/ActivatedContent/ScrollView/Viewport/Content/"
                       "OracleShopItem(Clone)/ShopImageAndLevel/ShopItemImage", "kind": "Image",
               "rect": [1385.4, 447.3, 1428.6, 490.5], "visible": [1385.4, 447.3, 1428.6, 468.7], "color": "#FFFFFFFF",
               "alpha": 1.0, "sprite": "afterburner", "spriteSize": [512, 512], "spriteBorder": [0, 0, 0, 0],
               "imageType": "Simple", "preserveAspect": False}

    def test_a_row_cut_by_its_scroll_view_is_not_stretched(self):
        census = {"screen": [1920, 1080], "elements": [dict(self.CLIPPED)]}
        self.assertEqual(ul.shape(census)["stretched"], [])

    def test_the_same_icon_drawn_off_its_shape_still_is(self):
        squashed = dict(self.CLIPPED, rect=[1385.4, 447.3, 1428.6, 468.7])
        self.assertEqual(len(ul.shape({"screen": [1920, 1080], "elements": [squashed]})["stretched"]), 1)

    def test_a_sliver_showing_under_a_mask_is_not_judged(self):
        sliver = dict(self.CLIPPED, rect=[1385.4, 447.3, 1428.6, 490.5], visible=[1385.4, 447.3, 1428.6, 450.3])
        self.assertEqual(ul.shape({"screen": [1920, 1080], "elements": [sliver]})["stretched"], [])

    @staticmethod
    def write_png(path, alpha):
        from PIL import Image  # noqa: PLC0415
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (64, 64), (255, 255, 255, alpha)).save(path)

    def test_a_transparent_hit_area_is_flagged_without_the_repo(self):
        census = {"screen": [1920, 1080], "elements": [dict(self.QUIET)]}
        self.assertEqual(len(ul.shape(census)["stretched"]), 1)  # nothing says it draws nothing

    def test_a_sprite_whose_every_pixel_is_transparent_is_not_stretched(self):
        census = {"screen": [1920, 1080], "elements": [dict(self.QUIET)]}
        self.assertEqual(ul.shape(census, invisible={"transparent-block"})["stretched"], [])

    def test_invisible_sprites_reads_the_pixels(self):
        try:
            import PIL  # noqa: F401, PLC0415
        except ImportError:
            self.skipTest("Pillow")
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp, "Assets")
            self.write_png(assets / "UI" / "transparent-block.png", 0)
            self.write_png(assets / "UI" / "selected-tab.png", 255)
            self.write_png(assets / "A" / "twice.png", 0)
            self.write_png(assets / "B" / "twice.png", 128)  # two files of one name, one drawn: not skipped
            self.assertEqual(ul.invisible_sprites(tmp, {"transparent-block", "selected-tab", "twice", "missing"}),
                             {"transparent-block"})
            self.assertEqual(ul.invisible_sprites(None, {"transparent-block"}), set())

    def test_the_shape_command_drops_a_transparent_hit_area_with_the_repo(self):
        try:
            import PIL  # noqa: F401, PLC0415
        except ImportError:
            self.skipTest("Pillow")
        import contextlib  # noqa: PLC0415
        import io  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            self.write_png(Path(tmp, "Assets", "Art", "UI", "UI2", "transparent-block.png"), 0)
            census = Path(tmp, "a-1920-projector-off-layout.json")
            census.write_text(json.dumps({"screen": [1920, 1080], "elements": [dict(self.QUIET)]}), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(0, ul.main(["shape", str(census), "--repo", tmp]))
            self.assertIn("Shape: 0 stretched", out.getvalue())
            self.assertIn("not judged: transparent-block: every pixel transparent", out.getvalue())

    def test_the_1920_light_panel_is_mostly_empty(self):
        found = ul.shape(self.fixture("w1386-1920-lamp"), self.SPRITES)["sparse"]
        self.assertEqual([s["path"].split("/")[-2:] for s in found], [["LightEntityPanel", "MainPanel"]])
        self.assertGreaterEqual(found[0]["hole"], ul.HOLE_SHARE)

    def test_the_cargo_hold_with_less_coverage_is_not(self):
        out = ul.shape(self.fixture("w1386-1920-cargo-hold"), self.SPRITES)
        self.assertEqual(out["sparse"], [])  # 24 % covered, but its largest hole is 25 %: rows across the whole panel

    def test_a_narrow_dialog_of_many_lines_is_a_wall_of_text(self):
        def dialog(lines):
            return {"screen": [1920, 1080], "elements": [
                el("ConfirmationModalParent", [710, 300, 1210, 780], sprite="background-main"),
                el("ConfirmationModalParent/ConfirmationText", [730, 320, 1190, 700], kind="TextMeshProUGUI", sprite="",
                   text="Content removed from this save", lines=lines, fontSize=16.0)]}
        self.assertEqual(len(ul.shape(dialog(14), self.SPRITES)["walls"]), 1)
        self.assertEqual(ul.shape(dialog(5), self.SPRITES)["walls"], [])

    def test_a_census_without_line_counts_says_walls_are_not_measured(self):
        lines, flagged = ul.shape_lines([("docked", ul.shape(self.fixture("w1386-docked-lamp"), self.SPRITES))])
        self.assertEqual(flagged, 1)
        self.assertIn("walls of text not measured", lines[0])
        self.assertTrue(lines[0].startswith("Shape: 1 stretched, 0 mostly empty, 0 wall(s) of text over 1 census(es)"))

    def test_the_command_exits_one_on_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "Assets" / "UI"
            repo.mkdir(parents=True)
            png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + (225).to_bytes(4, "big") + (150).to_bytes(4, "big")
            (repo / "SwitchOn.png").write_bytes(png)
            (repo / "SwitchOn.png.meta").write_text("  spriteMode: 1\n  spriteBorder: {x: 0, y: 0, z: 0, w: 0}\n")
            self.assertEqual(ul.sprite_sizes(tmp), {"SwitchOn": (225, 150, False)})
            code = ul.main(["shape", "--repo", tmp, str(HERE / "fixtures" / "w1386-docked-lamp.json")])
        self.assertEqual(code, 1)


class CommandTest(unittest.TestCase):
    def test_check_prints_the_three_lines_and_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, a = Path(tmp) / "before.json", Path(tmp) / "after.json"
            b.write_text(json.dumps(hud(quick_x0=968)), encoding="utf-8")
            a.write_text(json.dumps(hud(quick_x0=946, slideout=True)), encoding="utf-8")
            self.assertEqual(ul.main(["check", "--before", str(b), "--after", str(a)]), 1)
            self.assertEqual(ul.main(["check", "--before", str(b), "--after", str(b)]), 0)


@unittest.skipUnless(importlib.util.find_spec("PIL"), "needs Pillow (the CI runner has none)")
class SamplePanelFillTest(unittest.TestCase):
    FIXTURES = Path(__file__).resolve().parent / "fixtures"

    def test_new_rows_in_a_window_do_not_move_its_colour(self):
        # w1475: the Station Grid window at 1280x800 before and after two new rows; the median pixel read delta E 12.1
        # (the rows shifted the content under it), the window's fill is the same (#133754 against #123654)
        before = ul.sample(self.FIXTURES / "w1475-station-grid-1280-before.png", [0, 0, 567, 432])
        after = ul.sample(self.FIXTURES / "w1475-station-grid-1280-after.png", [0, 0, 567, 432])
        self.assertLess(ul.delta_e(after, before), 3)

    def test_a_recoloured_window_still_reads_far_off(self):
        from PIL import Image  # noqa: PLC0415
        with Image.open(self.FIXTURES / "w1475-station-grid-1280-after.png") as image:
            tinted = Image.eval(image.convert("RGB"), lambda v: min(255, v + 40))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tinted.png"
            tinted.save(path)
            before = ul.sample(self.FIXTURES / "w1475-station-grid-1280-before.png", [0, 0, 567, 432])
            self.assertGreater(ul.delta_e(ul.sample(path, [0, 0, 567, 432]), before), 10)


class SampleWithoutPillowTest(unittest.TestCase):
    def test_a_missing_pillow_says_how_to_get_it(self):
        # w807: a bare "ModuleNotFoundError: No module named 'PIL'" was all a Mac with no Pillow printed
        saved = sys.modules.get("PIL", False)
        sys.modules["PIL"] = None  # makes `from PIL import Image` raise ImportError
        try:
            with self.assertRaises(SystemExit) as raised:
                ul.sample("nowhere.png", [0, 0, 10, 10])
        finally:
            if saved is False:
                sys.modules.pop("PIL", None)
            else:
                sys.modules["PIL"] = saved
        self.assertIn("pillow", str(raised.exception).lower())
        self.assertIn("venv", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
