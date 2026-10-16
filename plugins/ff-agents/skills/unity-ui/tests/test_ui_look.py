"""Offline tests for ui_look.py (w1399): the colour checks on drawn stills and on crops of the real cases. Standard library
only (the script decodes PNG itself).

    python3 -m unittest discover -s plugins/ff-agents/skills/unity-ui/tests -p 'test_*.py' -v
"""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ui_look as uk  # noqa: E402

FIX = HERE / "fixtures"
GP = "InGameScene/UI Canvas/GamePanels"
NAVY = (0x15, 0x37, 0x4C)


def canvas(width=400, height=300, colour=NAVY):
    return bytearray(bytes(colour) * (width * height)), width, height


def fill(img, rect, colour, alpha=1.0):
    data, width, height = img
    x0, y0, x1, y1 = rect
    for y in range(max(0, y0), min(height, y1)):
        for x in range(max(0, x0), min(width, x1)):
            i = 3 * (y * width + x)
            for c in range(3):
                data[i + c] = int(round(alpha * colour[c] + (1 - alpha) * data[i + c]))


def still(img, name="t"):
    data, width, height = img
    return uk.Still(width, height, data, name)


def el(path, rect, kind="Image", color="#FFFFFFFF", alpha=1.0, **extra):
    return dict(path=f"{GP}/{path}", kind=kind, rect=list(rect), visible=list(rect), color=color, alpha=alpha, **extra)


def stop_list(chip_alpha, active_alpha=0.25):
    """Three stop rows on the navy panel; the first is the active stop, its row a see-through orange (w1334's #C17040 at
    0x40). Each row holds a chip drawn white at chip_alpha over the row (round 2's "flat" chips are #FFFFFF17, alpha 0.09;
    an opaque chip keeps its own colour)."""
    img = canvas(400, 300)
    rows = [(10, 10, 390, 90), (10, 100, 390, 180), (10, 190, 390, 270)]
    elements = [el("HaulerEntityPanel/MainPanel", (0, 0, 400, 300), color="#15374CFF")]
    chip_colour = (0x2A, 0x4B, 0x60)
    for i, r in enumerate(rows):
        if i == 0:
            fill(img, r, (0xC1, 0x70, 0x40), active_alpha)
            row_col = "#C1704040"
        else:
            fill(img, r, (0x08, 0x1C, 0x2C), 0.78)
            row_col = "#081C2CC8"
        chip = (r[0] + 20, r[1] + 30, r[0] + 140, r[1] + 60)
        if chip_alpha >= 1.0:
            fill(img, chip, chip_colour)
        else:
            fill(img, chip, (255, 255, 255), chip_alpha)
        elements.append(el("HaulerEntityPanel/MainPanel/Viewport/Content/StopRow(Clone)", r, color=row_col))
        elements.append(el("HaulerEntityPanel/MainPanel/Viewport/Content/StopRow(Clone)/Conditions/WaitConditionChip(Clone)",
                           chip, color="#FFFFFF17" if chip_alpha < 1 else "#2A4B60FF", alpha=min(1.0, chip_alpha)))
    return still(img), {"screen": [400, 300], "elements": elements}


class ColourMathTest(unittest.TestCase):
    def test_apca_matches_its_published_example(self):
        # APCA's README: #888 text on #fff is Lc 63.1, #fff on #888 is Lc -68.5.
        self.assertAlmostEqual(uk.apca_lc((0x88,) * 3, (255,) * 3), 63.06, places=1)
        self.assertAlmostEqual(uk.apca_lc((255,) * 3, (0x88,) * 3), -68.54, places=1)

    def test_wcag_ratio_bounds(self):
        self.assertAlmostEqual(uk.contrast_ratio((0, 0, 0), (255, 255, 255)), 21.0, places=2)
        self.assertAlmostEqual(uk.contrast_ratio(NAVY, NAVY), 1.0, places=6)

    def test_png_round_trip(self):
        img = canvas(37, 23)
        fill(img, (5, 5, 20, 15), (250, 10, 120))
        s = still(img)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.png"
            uk.write_png(p, s)
            back = uk.read_png(p)
        self.assertEqual((back.width, back.height, back.data), (37, 23, s.data))


class LoudFillTest(unittest.TestCase):
    # A 640x360 "screen" (0.1 % of it is 230 px) keeps the pure-Python scan quick in CI.
    def test_a_bright_saturated_button_is_loud_and_a_muted_one_is_not(self):
        img = canvas(640, 360)
        fill(img, (40, 40, 140, 60), (0x2F, 0xB7, 0xE8))         # a bright cyan button, 100x20
        fill(img, (40, 100, 140, 120), (0x2D, 0x64, 0x7D))       # the accent at a third over navy: quiet
        fill(img, (40, 160, 43, 200), (0x2F, 0xB7, 0xE8))        # a thin accent edge: too small to be a fill
        found = uk.loud_fills(still(img), [(0, 0, 640, 360)])
        self.assertEqual(len(found), 1, found)
        self.assertEqual([round(v) for v in found[0]["rect"][:2]], [40, 40])

    def test_white_and_grey_are_not_judged(self):
        # On master's Esc menu the big flat white shapes are the logo's letters and the social icons (w1399 sweep).
        img = canvas(640, 360)
        fill(img, (40, 40, 140, 60), (0xFF, 0xFF, 0xFF))
        fill(img, (40, 100, 140, 120), (0xD6, 0xD6, 0xD6))
        self.assertEqual(uk.loud_fills(still(img), [(0, 0, 640, 360)]), [])


class BleedTest(unittest.TestCase):
    def test_see_through_chips_in_the_active_row_take_its_colour(self):
        s, census = stop_list(chip_alpha=0.09)
        found = uk.bleed_in_census(census, s, "w1334-like")
        self.assertEqual(len(found), 1, found)
        self.assertTrue(found[0]["controls"][0]["path"].endswith("WaitConditionChip(Clone)"))
        self.assertGreater(found[0]["controls"][0]["de"], uk.BLEED_DE)

    def test_opaque_chips_keep_their_colour_in_the_active_row(self):
        s, census = stop_list(chip_alpha=1.0)
        self.assertEqual(uk.bleed_in_census(census, s, "w1334-round-1-like"), [])

    def test_same_pairs_on_a_still_alone(self):
        s, _ = stop_list(chip_alpha=0.09)
        pairs = [((40, 50, 140, 60), (40, 140, 140, 150))]   # the chip of the active row against the chip of row 2
        self.assertEqual(len(uk.same_pairs(s, pairs)), 1)
        s2, _ = stop_list(chip_alpha=1.0)
        self.assertEqual(uk.same_pairs(s2, pairs), [])


class ContrastTest(unittest.TestCase):
    def test_grey_text_on_navy_fails_and_white_passes(self):
        img = canvas(400, 120)
        fill(img, (0, 0, 400, 120), NAVY)
        fill(img, (20, 20, 120, 34), (0x3B, 0x55, 0x66))     # "glyphs": a dim grey-blue bar
        fill(img, (20, 70, 120, 84), (0xF0, 0xF4, 0xF8))     # bright text
        census = {"screen": [400, 120], "elements": [
            el("SomePanel/MainPanel", (0, 0, 400, 120), color="#15374CFF"),
            el("SomePanel/MainPanel/Dim", (10, 10, 130, 44), kind="TextMeshProUGUI", color="#3B5566FF", text="20 sec"),
            el("SomePanel/MainPanel/Bright", (10, 60, 130, 94), kind="TextMeshProUGUI", color="#F0F4F8FF", text="Pick"),
        ]}
        fails, weak = uk.text_contrast(census, still(img), [(0, 0, 400, 120)])
        self.assertEqual([f["text"] for f in fails], ["20 sec"])
        self.assertEqual(weak, [])


class RealCaseTest(unittest.TestCase):
    """The stills Ben judged on 2026-10-16 (crops of them, at their own pixels): w1334's stop list in round 2 (#1817,
    rejected: "the active stop color is bleeding into a bunch of the panel's elements, it looks bad, like its washing
    everything out", "the add stop bright blue is also painful on the eyes") and round 1 (#1810, "ok i like the stops
    panel"), cut from the same before/after still; and w1386's docked Light Structure panel ("the light panel is really
    messed up obviously")."""

    R2 = FIX / "w1334r2-stop-list.png"
    R1 = FIX / "w1334r1-stop-list.png"
    LAMP = FIX / "w1386-docked-lamp-still.png"
    # The "Cargo holds full" chip in the active stop (row 1) and the "Cargo holds:" chip in a plain stop (row 3).
    CHIPS = [((206, 40, 320, 64), (66, 166, 164, 190))]
    SCREEN = 1920 * 1080

    def test_round_two_chips_take_the_active_rows_colour_and_round_one_chips_do_not(self):
        r2 = uk.same_pairs(uk.read_png(self.R2), self.CHIPS)
        self.assertEqual(len(r2), 1)
        self.assertAlmostEqual(r2[0]["controls"][0]["de"], 13.6, delta=1.0)    # MEASURED, w1399
        self.assertEqual(uk.same_pairs(uk.read_png(self.R1), self.CHIPS), [])  # opaque #CCCCCC chips: delta E 0.0

    def test_round_two_add_stop_is_a_loud_fill(self):
        found = uk.loud_fills(uk.read_png(self.R2), [(0, 0, 450, 310)], self.SCREEN)
        self.assertEqual([uk.hex_of(f["colour"]) for f in found], ["#57B2D0"])  # L* 68, C* 30
        self.assertEqual([round(v) for v in found[0]["rect"]], [33, 261, 153, 297])

    def test_round_one_has_no_loud_fill_once_its_progress_fill_is_known(self):
        # Round 1's only bright fill is a met condition's green progress fill (as Factorio's train schedule fills one),
        # which the census names `Fill`: exempt. Its full-width blue Add stop bar (#2178C6, L* 49) is not loud.
        still = uk.read_png(self.R1)
        census = {"screen": [1920, 1080], "elements": [
            el("HaulerEntityPanel/MainPanel/Viewport/Content/StopRow(Clone)/Conditions/WaitConditionChip(Clone)/Condition/Fill",
               (240, 193, 380, 217), color="#5ED66CFF")]}
        result = uk.judge(still, census, [[0, 0, 450, 310]], "r1", [], {})
        self.assertEqual(result["loud"], [])

    def test_the_add_stop_label_on_round_two_is_under_3_to_1_and_round_one_is_not(self):
        def label(rect, colour):
            return {"screen": [1920, 1080], "elements": [
                el("HaulerEntityPanel/MainPanel/AddStop/Label", rect, kind="TextMeshProUGUI", color=colour, text="Add stop")]}
        fails, _ = uk.text_contrast(label((54, 268, 118, 290), "#DFF4FBFF"), uk.read_png(self.R2), [(0, 0, 450, 310)])
        self.assertEqual(len(fails), 1)
        self.assertLess(fails[0]["ratio"], 2.5)                                   # MEASURED 2.06:1
        fails, _ = uk.text_contrast(label((54, 268, 118, 290), "#FFFFFFFF"), uk.read_png(self.R1), [(0, 0, 450, 310)])
        self.assertEqual(fails, [])                                              # 4.34:1 on #2178C6

    def test_the_stretched_docked_switch_is_a_loud_green_bar(self):
        found = uk.loud_fills(uk.read_png(self.LAMP), [(0, 0, 540, 150)], 1280 * 800)
        self.assertEqual([uk.hex_of(f["colour"]) for f in found], ["#39B54A"])   # 338x19 px, L* 65, C* 71


class PackTest(unittest.TestCase):
    """The critic's input is built by the script, so the worker's account never reaches it (w1399)."""

    def test_the_pack_holds_crops_references_and_the_words_apart(self):
        with tempfile.TemporaryDirectory() as d:
            brief = Path(d) / "brief.txt"
            brief.write_text('Ben: "make the add stop button button stand out just a little more" and "keep it clean"',
                             encoding="utf-8")
            out = Path(d) / "pack"
            with redirect_stdout(io.StringIO()):
                code = uk.main(["pack", "--after", f"{RealCaseTest.R2}@0,0,450,310", "--before", str(RealCaseTest.R1),
                                "--ref", str(RealCaseTest.R1), "--brief", str(brief), "--out", str(out)])
            self.assertEqual(code, 0)
            a = sorted(p.name for p in (out / "a").iterdir())
            self.assertEqual(a, ["s1-full.png", "s1-w1-2x.png", "s1-w1.png"])
            words = (out / "b" / "words.md").read_text(encoding="utf-8")
            self.assertIn("make the add stop button button stand out just a little more", words)
            prompt = (out / "prompt.md").read_text(encoding="utf-8")
            self.assertIn("Write Pass A for every still before you open anything in", prompt)
            self.assertNotIn("stand out", prompt)        # the words wait in b/ until Pass A is written
            self.assertTrue((out / "b" / "s1-before.png").exists() and (out / "b" / "s1-after.png").exists())
            self.assertTrue(any(p.name.startswith("ref1-") for p in (out / "refs").iterdir()))


if __name__ == "__main__":
    unittest.main()
