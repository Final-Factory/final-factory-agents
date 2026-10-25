import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import approval_ask as aa  # noqa: E402

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None

# The shape of the ask Ben had to send back twice: one line per change, full-screen stills.
ONE_LINER = """# Stacked windows: OK to merge?

## Change 1: stacked windows
Windows stacked on each other no longer show ghost labels.

![before](before-full.png) ![after](after-full.png)
"""

GOOD = """# Stacked windows: OK to merge?

## Change 1: the window underneath stops showing through
**Before:**
1. The player opens a Mining Station's window, then opens a Refinery's window on top of it.
2. The Refinery window is see-through where it overlaps, so the Mining Station's labels show through it as grey ghost text.

**After:** the Refinery window on top is solid; only its own labels show, and the Mining Station window is hidden behind it.

**Fixes:** two windows' labels drawn on top of each other made the top window hard to read, and looked broken.

**Code:** `Assets/Scripts/UI/StructureWindow.cs`, method `ApplyBackground()`: the panel's background alpha 0.85 -> 1.0.

**Unchanged:** window positions, sizes, the order they open in, and every window that is not stacked look exactly as before.

**Stills:** ![pair](marked/pair.png)
"""


@unittest.skipIf(Image is None, "Pillow is not installed")
class ApprovalAskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        a = Image.new("RGB", (1920, 1080), (30, 40, 60))
        b = a.copy()
        ImageDraw.Draw(a).rectangle((1700, 900, 1800, 960), fill=(120, 120, 120))  # the ghost label, a corner
        a.save(self.root / "before-full.png")
        b.save(self.root / "after-full.png")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text):
        p = self.root / "ask.md"
        p.write_text(text, encoding="utf-8")
        return p

    def test_the_one_line_ask_with_full_screen_stills_fails(self):
        misses = aa.check(self.write(ONE_LINER))
        text = "\n".join(misses)
        for part in ("Before", "After", "Fixes", "Code", "Unchanged"):
            self.assertIn(f"no {part}: part", text)
        self.assertIn("before-full.png: not cropped and marked", text)

    def test_mark_crops_to_the_corner_and_the_good_ask_passes(self):
        meta = aa.mark(self.root / "before-full.png", self.root / "after-full.png", self.root / "marked")
        self.assertEqual(meta["ring"], [1700, 900, 1801, 961])
        x0, y0, x1, y1 = meta["crop"]
        self.assertLess(x1 - x0, 1920 // 2)
        with Image.open(self.root / "marked" / "after.png") as im:
            self.assertIn((255, 40, 40), {im.getpixel((x, im.height // 2)) for x in range(im.width)})
        self.assertEqual(aa.check(self.write(GOOD)), [])

    def test_a_still_marked_but_not_cropped_fails(self):
        aa.mark(self.root / "before-full.png", self.root / "after-full.png", self.root / "marked",
                rect=(1700, 900, 100, 60), pad=1200)
        misses = aa.check(self.write(GOOD))
        self.assertTrue(any("most of the" in m for m in misses), misses)

    def test_before_without_steps_and_code_without_values_fail(self):
        aa.mark(self.root / "before-full.png", self.root / "after-full.png", self.root / "marked")
        bad = GOOD.replace("1. The player opens", "The player opens").replace("2. The Refinery", "The Refinery")
        bad = bad.replace("0.85 -> 1.0", "made fully opaque now everywhere")
        misses = "\n".join(aa.check(self.write(bad)))
        self.assertIn("Before: needs the player's steps", misses)
        self.assertIn("gives no value before and after", misses)

    def test_identical_stills_are_refused(self):
        with self.assertRaises(SystemExit):
            aa.mark(self.root / "after-full.png", self.root / "after-full.png", self.root / "same")


if __name__ == "__main__":
    unittest.main()
