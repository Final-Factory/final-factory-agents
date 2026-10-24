"""window_changes.py (w1911's review): a placement fix that lifts a window over a window that was clear is a NEW COVER, one
that shortens a window is RESIZED, and a fix that touches nothing is OK.

    python3 -m unittest discover -s plugins/ff-agents/skills/unity-ui/tests -p 'test_*.py' -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "window_changes.py"


def census(crafting, grid):
    def el(path, rect):
        return {"path": path, "rect": rect, "visible": True}
    return {"elements": [
        el("UI/InvAndCraft/UtilityPanel", crafting), el("UI/InvAndCraft/UtilityPanel/Tabs", crafting),
        el("UI/StationCoreEntityPanel/MainPanel", [1664, 92, 2228, 409]), el("UI/StationCoreEntityPanel/MainPanel/Title", [1664, 92, 2228, 130]),
        el("UI/StationGridEntityPanel/MainPanel", grid), el("UI/StationGridEntityPanel/MainPanel/Rows", grid),
        el("UI/BuildInfoPanel/Parent", [1487, 1000, 1953, 1142]),
    ]}


def run(before, after):
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for name, data in (("b.json", before), ("a.json", after)):
            p = Path(d) / name
            p.write_text(json.dumps(data), encoding="utf-8")
            paths.append(str(p))
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), *paths], capture_output=True, text=True)
        return r.returncode, r.stdout


class WindowChanges(unittest.TestCase):
    def test_a_window_lifted_over_station_core_is_a_new_cover(self):
        code, out = run(census([1779, 216, 2731, 1090], [820, 92, 1648, 700]), census([1779, 105, 2731, 979], [820, 92, 1648, 700]))
        self.assertEqual(code, 1)
        self.assertIn("NEW COVER Crafting / Station Core", out)

    def test_a_shortened_window_is_resized(self):
        code, out = run(census([1779, 216, 2731, 1090], [820, 92, 1648, 700]), census([1779, 216, 2731, 1090], [820, 92, 1648, 655]))
        self.assertEqual(code, 1)
        self.assertIn("RESIZED Station Grid", out)

    def test_a_pair_that_moves_nothing_is_ok(self):
        c = census([1779, 216, 2731, 1090], [820, 92, 1648, 700])
        code, out = run(c, c)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("OK"))


if __name__ == "__main__":
    unittest.main()
