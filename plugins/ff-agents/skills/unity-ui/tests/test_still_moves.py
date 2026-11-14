"""still_moves.py (w4153): a mock that draws only inside the region the person named passes; one that also grows the
sidebar's block and pushes the list under it 74 px lower is OUT, with the box that changed.

    python3 -m unittest discover -s plugins/ff-agents/skills/unity-ui/tests -p 'test_*.py' -v
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ui_look  # noqa: E402

SCRIPT = HERE.parent / "still_moves.py"
W, H = 400, 300
BG, BLOCK, LIST, PANEL = (18, 20, 24), (200, 150, 40), (90, 110, 140), (40, 44, 52)
NAMED = "240,0,400,300"  # the right panel: where the person asked for the list


def still(*rects):
    px = [[BG] * W for _ in range(H)]
    for x0, y0, x1, y1, colour in rects:
        for y in range(y0, y1):
            px[y][x0:x1] = [colour] * (x1 - x0)
    return ui_look.Still(W, H, bytes(v for row in px for p in row for v in p), "s")


BEFORE = still((10, 60, 110, 120, BLOCK), (10, 140, 110, 220, LIST))
# The mock as asked: the new panel, inside the named region, and nothing else.
ASKED = still((10, 60, 110, 120, BLOCK), (10, 140, 110, 220, LIST), (240, 0, 400, 300, PANEL))
# w4153, round 1: the sidebar's block grew by 74 px and pushed the list under it 74 px lower.
MOVED = still((10, 60, 110, 194, BLOCK), (10, 214, 110, 294, LIST), (240, 0, 400, 300, PANEL))


def run(before, after, *args):
    with tempfile.TemporaryDirectory() as d:
        b, a = Path(d) / "before.png", Path(d) / "after.png"
        ui_look.write_png(b, before)
        ui_look.write_png(a, after)
        r = subprocess.run([sys.executable, str(SCRIPT), str(b), str(a), *args], capture_output=True, text=True, check=False)
        return r.returncode, r.stdout


class StillMovesTest(unittest.TestCase):
    def test_a_mock_inside_the_named_region_passes(self):
        code, out = run(BEFORE, ASKED, "--named", NAMED)
        self.assertEqual(code, 0, out)
        self.assertIn("Moves: none outside the named region", out)

    def test_a_grown_block_that_pushes_the_list_down_is_out(self):
        code, out = run(BEFORE, MOVED, "--named", NAMED)
        self.assertEqual(code, 1, out)
        self.assertIn("Moves: OUT, 1 block changed outside the named region", out)
        self.assertIn("CHANGED 10,120-110,294 (100x174 px, 16800 pixels differ)", out)

    def test_without_a_named_region_the_stills_must_match(self):
        self.assertEqual(run(BEFORE, BEFORE)[0], 0)
        code, out = run(BEFORE, ASKED)
        self.assertEqual(code, 1, out)
        self.assertIn("CHANGED 240,0-400,300", out)

    def test_a_faint_repaint_is_not_a_move(self):
        faint = still((10, 60, 110, 120, (203, 152, 43)), (10, 140, 110, 220, LIST))
        self.assertEqual(run(BEFORE, faint)[0], 0)
        self.assertEqual(run(BEFORE, faint, "--tolerance", "0")[0], 1)

    def test_stills_of_two_sizes_are_refused(self):
        small = ui_look.Still(200, 300, bytes(BG) * (200 * 300), "s")
        code, out = run(BEFORE, small)
        self.assertEqual(code, 2, out)
        self.assertIn("Sizes differ", out)


if __name__ == "__main__":
    unittest.main()
