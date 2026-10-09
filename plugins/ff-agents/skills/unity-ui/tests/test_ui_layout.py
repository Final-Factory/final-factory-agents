"""Offline tests for ui_layout.py (w733, w742) on drawn censuses. Standard library only (Pillow for the on-screen colour test).

    python3 -m unittest discover -s plugins/ff-agents/skills/unity-ui/tests -p 'test_*.py' -v
"""
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
        quick_on_hotbar=False, slideout_depth=None, slideout_raycast=True):
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
        el("InvAndCraft/InventoryPanel", [208, 6, 778, 610]),
        el("ObjectivesPanel/ScrollviewParent/ScrollView/Viewport", [10, 100, 420, 260], sprite="UIMask", maskOnly=True),
        el("CraftQueuePanels/Viewport", [0, 100, 600, 700], sprite="UIMask", maskOnly=True),
    ]
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
        code, out = Cmd.run(hud(), hud(blueprint_backdrop=True), closed=hud(), extra=["--touched", "BlueprintPanelChild"])
        self.assertEqual(code, 1)
        self.assertIn("0 new, 0 kept", the_line(out, "Overlaps"))
        self.assertIn("BlueprintPanelChild  x  ObjectivesPanel", out)
        self.assertNotIn("NEW: ", out)
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
        code, out = Cmd.run(hud(), hud(blueprint_window=True), closed=hud(), extra=["--touched", "BlueprintPanelChild"])
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

    def test_tint_colour_and_alpha_on_the_same_art(self):
        after = hud()
        after["elements"].append(el("BlueprintPanelChild", [392, 68, 850, 444], color="#0D1724FF", alpha=0.98))
        before = hud()
        before["elements"].append(el("BlueprintPanelChild", [392, 68, 850, 444], alpha=0.5))
        _, failures = ul.style(before, after, "InventoryPanel")
        self.assertTrue(any("delta E" in f for f in failures), failures)


class CommandTest(unittest.TestCase):
    def test_check_prints_the_three_lines_and_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, a = Path(tmp) / "before.json", Path(tmp) / "after.json"
            b.write_text(json.dumps(hud(quick_x0=968)), encoding="utf-8")
            a.write_text(json.dumps(hud(quick_x0=946, slideout=True)), encoding="utf-8")
            self.assertEqual(ul.main(["check", "--before", str(b), "--after", str(a)]), 1)
            self.assertEqual(ul.main(["check", "--before", str(b), "--after", str(b)]), 0)


if __name__ == "__main__":
    unittest.main()
