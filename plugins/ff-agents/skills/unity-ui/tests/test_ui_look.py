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
from contextlib import redirect_stderr, redirect_stdout
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
        self.assertLess(fails[0]["ratio"], 2.5)                                   # MEASURED 2.13:1
        fails, _ = uk.text_contrast(label((54, 268, 118, 290), "#FFFFFFFF"), uk.read_png(self.R1), [(0, 0, 450, 310)])
        self.assertEqual(fails, [])                                              # 4.60:1 on #2178C6

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

    def test_a_pack_without_a_reference_window_is_refused(self):
        """The critic judges a window beside the game's others (w1818): no --ref and no --repo is an error."""
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                code = uk.main(["pack", "--after", f"{RealCaseTest.R2}@0,0,450,310", "--out", str(Path(d) / "pack")])
            self.assertEqual(code, 2)


def rounded(img, rect, radius, colour, alpha=1.0, sub=4):
    """A rounded rectangle drawn with anti-aliased corners (sub x sub samples a pixel), as uGUI draws a sliced sprite."""
    data, width, height = img
    x0, y0, x1, y1 = rect
    for y in range(max(0, y0), min(height, y1)):
        for x in range(max(0, x0), min(width, x1)):
            hits = 0
            for sy in range(sub):
                for sx in range(sub):
                    px, py = x + (sx + 0.5) / sub, y + (sy + 0.5) / sub
                    cx = min(max(px, x0 + radius), x1 - radius)
                    cy = min(max(py, y0 + radius), y1 - radius)
                    hits += (px - cx) ** 2 + (py - cy) ** 2 <= radius * radius
            a = alpha * hits / (sub * sub)
            if a:
                i = 3 * (y * width + x)
                for c in range(3):
                    data[i + c] = int(round(a * colour[c] + (1 - a) * data[i + c]))


FRAME, ROW, BUTTON, DISC = (0x13, 0x3A, 0x54), (0x08, 0x1C, 0x2C), (0x21, 0x78, 0xC6), (0x2C, 0x83, 0x9C)


def family_window(img, x, name, header_pt, header_lines, bottom_pad, disc_radius, disc_gap, button_radius):
    """A window at x on a dark screen: a frame (radius 8), a header, two rows (radius 6), a disc in each row's left end
    and a button at the bottom. Returns its census elements."""
    path = f"{name}Panel"
    top, w = 20, 300
    rounded(img, (x, top, x + w, 380), 8, FRAME)
    els = [el(path, (x, top, x + w, 380), sprite="background-main"),
           el(f"{path}/Title", (x + 14, top + 10, x + 200, top + 10 + 1.3 * header_pt * header_lines),
              kind="TextMeshProUGUI", text="Calculations", fontSize=header_pt, lines=header_lines,
              textRect=[x + 14, top + 12, x + 180, top + 8 + 1.2 * header_pt * header_lines])]
    for k in range(2):
        ry = 80 + 70 * k
        rounded(img, (x + 14, ry, x + w - 14, ry + 50), 6, ROW)
        els.append(el(f"{path}/Rows/Row{k}", (x + 14, ry, x + w - 14, ry + 50), sprite="row"))
        d = 2 * disc_radius
        dx, dy = x + 14 + disc_gap, ry + 25 - disc_radius
        rounded(img, (dx, dy, dx + d, dy + d), disc_radius, DISC)
        els.append(el(f"{path}/Rows/Row{k}/Disc", (dx, dy, dx + d, dy + d), sprite="circle"))
        els.append(el(f"{path}/Rows/Row{k}/Label", (dx + d + 8, ry + 15, dx + d + 120, ry + 35), kind="TextMeshProUGUI",
                      text=f"Signal {k}", fontSize=16, lines=1))
    by1 = 380 - bottom_pad
    rounded(img, (x + 14, by1 - 32, x + 160, by1), button_radius, BUTTON)
    els.append(el(f"{path}/Add", (x + 14, by1 - 32, x + 160, by1), sprite="button", selectable=True))
    return els


class FamilyTest(unittest.TestCase):
    """The window against the game's other windows: corners, header, edges (w1818; Ben on w1761 and w1296)."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        d = Path(cls.dir.name)
        img = canvas(1000, 400, (0x05, 0x0A, 0x14))
        # the reference: one radius family (the frame 8, rows and button 6, a disc tucked in concentrically), 24 pt title
        ref = family_window(img, 20, "Fleet", 24, 1, 14, 6, 0, 6)
        # w1761's look: letter circles (radius 11) 3 px inside rows of radius 6, a button of radius 14, a 19 pt header
        # and the button 4 px off the bottom
        bad = family_window(img, 350, "Calc", 19, 1, 4, 11, 3, 14)
        # the same window made consistent
        good = family_window(img, 680, "Clean", 24, 1, 14, 6, 0, 6)
        uk.write_png(d / "s.png", still(img))
        (d / "s.json").write_text(json.dumps({"screen": [1000, 400], "elements": ref + bad + good}), encoding="utf-8")
        cls.spec = f"{d / 's.png'}::{d / 's.json'}"

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_corner_radius_is_read_off_the_pixels(self):
        for r in (0, 3, 6, 10, 14):
            img = canvas(80, 80, (0x05, 0x0A, 0x14))
            rounded(img, (10, 10, 70, 60), r, FRAME)
            got = uk.shape_radius(still(img), (10, 10, 70, 60))
            self.assertIsNotNone(got)
            self.assertLess(abs(got - r), 1.0, f"radius {r} read as {got}")

    def test_w1761s_look_is_flagged_and_a_consistent_window_is_not(self):
        out = io.StringIO()
        with redirect_stdout(out):
            bad = uk.main(["family", self.spec + "#CalcPanel", "--ref", self.spec + "#FleetPanel"])
            good = uk.main(["family", self.spec + "#CleanPanel", "--ref", self.spec + "#FleetPanel"])
        text = out.getvalue()
        self.assertEqual(bad, 1, text)
        self.assertEqual(good, 0, text)
        lines = text.split("Family:")[1]
        for tag in ("MIXED CORNERS", "NESTED CORNERS", "SMALL HEADER", "CRAMPED BOTTOM"):
            self.assertIn(tag, lines)
        self.assertNotIn("HEADER TWO LINES", lines)
        self.assertIn("Family: 1 window(s) against 1 reference window(s), 0 finding(s)", text)

    def test_w1761s_round_6_window_matches_the_station_core_window(self):
        # The built game's Calculations window after Ben's notes (round 6: one corner size, the Station Core window's
        # 18 pt title, 14 units under the last button), cut from its 1920x1080 still with its census, against the Station
        # Core window from the same build. The rows' sprite draws 1-3 px inside its rect and two row corners sit over
        # the nebula: both read as rounder corners before the drawn-edge snap and the lower median.
        calc = f"{FIX / 'w1761r6-calculations.png'}::{FIX / 'w1761r6-calculations.json'}#CalculationEntityPanel/MainPanel"
        core = f"{FIX / 'w1761r6-station-core.png'}::{FIX / 'w1761r6-station-core.json'}#StationCoreEntityPanel/MainPanel"
        out = io.StringIO()
        with redirect_stdout(out):
            code = uk.main(["family", calc, "--ref", core])
        self.assertEqual(code, 0, out.getvalue())
        win = uk._measure(calc)[0]
        self.assertTrue(all(2.0 <= s["radius"] <= 5.0 for s in win["shapes"]), win["shapes"])
        # The same window with round 3's title (15 pt, the connector window's type; w1761 commit 9d54a3c116) and its
        # 8 units under the last button (7.2 px; commit 9dc22a2517), the two Ben named: "the header font seems smaller
        # than other headers" and "make the bottom padding a few more pixels too it feels crammed".
        ref = uk._measure(core)
        r3 = dict(win, header=dict(win["header"], fontSize=15.0), edges=dict(win["edges"], bottom=7.2))
        found = [f.split(":")[0] for f in uk.family_findings(r3, ref)]
        self.assertEqual(found, ["SMALL HEADER", "CRAMPED BOTTOM"])

    def test_a_two_line_header_is_flagged(self):
        s = {"radii": [], "nested": [], "screen": [1000, 400], "edges": None,
             "header": {"text": "Content removed from this save", "fontSize": 24, "lines": 2}}
        r = {"radii": [], "screen": [1000, 400], "edges": None, "header": {"text": "Mods", "fontSize": 24, "lines": 1}}
        self.assertTrue(any(f.startswith("HEADER TWO LINES") for f in uk.family_findings(s, [r])))

    def test_no_reference_window_is_an_error(self):
        d = Path(self.dir.name)
        census = json.loads((d / "s.json").read_text(encoding="utf-8"))
        census["elements"] = [e for e in census["elements"] if "/CalcPanel" in e["path"]]
        (d / "alone.json").write_text(json.dumps(census), encoding="utf-8")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = uk.main(["family", f"{d / 's.png'}::{d / 'alone.json'}#CalcPanel"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
