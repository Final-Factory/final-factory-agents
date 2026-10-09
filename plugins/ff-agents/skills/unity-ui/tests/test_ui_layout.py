"""Offline tests for ui_layout.py (w733) on drawn censuses. Standard library only.

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


def el(path, rect, kind="Image", color="#FFFFFFFF", alpha=1.0, sprite="background-main", **extra):
    return dict(path=f"{GP}/{path}", kind=kind, rect=rect, visible=rect, color=color, alpha=alpha, sprite=sprite, **extra)


def hud(quick_x0=946, slideout=False, blueprint_backdrop=False):
    """The bottom-right HUD at 1280x800, as the w733 census of develop measured it, roughly."""
    elements = [
        el("MinimapParent/Background", [996, 520, 1268, 792], alpha=0.71),
        el("QuickButtons/ProductionStats/Icon", [quick_x0, 700, quick_x0 + 26, 740], selectable=True),
        el("QuickButtons/Help/Icon", [quick_x0, 745, quick_x0 + 26, 785], selectable=True),
        el("QuckControls/OptionToggles/BlueprintOptions", [866, 650, 904, 690], selectable=True),
        el("ActionBarParent/Hotbars/BuildBar/ItemSlot (7)/Background", [735, 688, 770, 723]),
        el("ActionBarParent/Hotbars/BuildBar/ItemSlot (8)/Background", [795, 688, 830, 723]),
        el("InvAndCraft/InventoryPanel", [208, 6, 778, 610]),
        el("ObjectivesPanel/ScrollviewParent/ScrollView/Viewport", [10, 100, 420, 260], sprite="UIMask", maskOnly=True),
        el("CraftQueuePanels/Viewport", [0, 100, 600, 700], sprite="UIMask", maskOnly=True),
    ]
    if slideout:
        elements.append(el("QuckControls/OptionsPanels/BpControls/Controls", [696, 652, 858, 692]))
    if blueprint_backdrop:
        elements.append(el("BlueprintPanelChild/SolidBackdrop", [392, 68, 850, 444], color="#0D1724FA", alpha=0.98, sprite=""))
    return {"screen": [1280, 800], "elements": elements}


class OverlapTest(unittest.TestCase):
    def test_blocks_are_two_levels_under_the_canvas(self):
        self.assertEqual(ul.block_of(f"{GP}/QuickButtons/Help/Icon", 2), f"{GP}/QuickButtons")

    def test_a_closed_hud_has_no_overlap_and_masks_do_not_count(self):
        self.assertEqual(ul.overlaps(hud()), {})

    def test_the_blueprint_slide_out_over_the_hotbar_is_found(self):
        pairs = ul.overlaps(hud(slideout=True))
        self.assertIn((f"{GP}/ActionBarParent", f"{GP}/QuckControls"), pairs)


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
