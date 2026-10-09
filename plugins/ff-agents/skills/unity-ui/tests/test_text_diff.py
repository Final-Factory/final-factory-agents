"""Offline tests for text_diff.py (w761) on the texts its censuses measured. Standard library only.

    python3 -m unittest discover -s plugins/ff-agents/skills/unity-ui/tests -p 'test_*.py' -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import text_diff as td  # noqa: E402

GP = "InGameScene/UI Canvas/GamePanels"


def text(path, value, size, lines, rendered, box, wrap="Normal", overflowing=False, truncated=False):
    return dict(path=f"{GP}/{path}", kind="TextMeshProUGUI", text=value, fontSize=size, lines=lines,
                overflowing=overflowing, truncated=truncated, renderedW=rendered, rectW=box, wrap=wrap)


def census(*elements):
    return {"screen": [1920, 1080], "elements": list(elements)}


class TextDiffTest(unittest.TestCase):
    def write(self, folder, name, data):
        path = Path(folder) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_the_w761_labels_are_flagged_and_a_bigger_text_that_still_fits_is_not(self):
        # Measured at 1920x1080 on 4762a5bc3 (before #1282) and ca58de9c8 (develop, Build 90).
        filter_path = "MassDriverEntityPanel/MainPanel/Content/FilterComponentPanel/OptionsParent/Options/Categories"
        before = census(
            text(f"{filter_path}/Components/Text (TMP)", "Components", 14.0, 1, 91.8, 102.0),
            text("BlueprintPanelChild/Content/LeftPanel/BlueprintFolderBar/ActionsRow/RenameFolder/Text (TMP)",
                 "Rename folder", 14.0, 1, 104.4, 134.7),
            text("Hotbars/Label", "Space", 14.0, 1, 40.0, 60.0),
            text("TopInfoPanel/Resources", "1,992/2,000", 14.0, 1, 80.0, 90.0))
        after = census(
            text(f"{filter_path}/Components/Text (TMP)", "Components", 16.0, 2, 96.9, 102.0, overflowing=True),
            text("BlueprintPanelChild/Content/LeftPanel/BlueprintFolderBar/ActionsRow/RenameFolder/Text (TMP)",
                 "Rename folder", 15.0, 1, 107.2, 134.7, truncated=True),
            text("Hotbars/Label", "Space", 15.0, 1, 43.0, 60.0),
            text("TopInfoPanel/Resources", "2,000/2,000", 15.0, 2, 95.0, 90.0, overflowing=True))
        with tempfile.TemporaryDirectory() as folder:
            flagged = td.compare(self.write(folder, "b.json", before), self.write(folder, "a.json", after))
        texts = {t for _, t, _ in flagged}
        self.assertEqual({"Components", "Rename folder"}, texts, "a live counter whose text changed is not compared")
        reasons = {t: r for _, t, r in flagged}
        self.assertIn("lines 1 -> 2", reasons["Components"])
        self.assertIn("cut off (ellipsis or truncate)", reasons["Rename folder"])

    def test_dir_mode_pairs_states_by_prefix_and_exits_1_on_a_finding(self):
        before = census(text("ModPanel/Right/Game Version/Label", "Game Version", 14.0, 1, 98.3, 105.0))
        after = census(text("ModPanel/Right/Game Version/Label", "Game Version", 15.0, 2, 56.9, 105.0))
        same = census(text("Menu/Save", "Save", 14.0, 1, 30.0, 200.0))
        with tempfile.TemporaryDirectory() as folder:
            self.write(folder, "b-title-mods.json", before)
            self.write(folder, "a-title-mods.json", after)
            self.write(folder, "b-menu.json", same)
            self.write(folder, "a-menu.json", same)
            self.write(folder, "b-only-before.json", same)
            self.assertEqual(1, td.main(["--dir", folder, "b-", "a-"]))
            self.write(folder, "a-title-mods.json", before)
            self.assertEqual(0, td.main(["--dir", folder, "b-", "a-"]))


if __name__ == "__main__":
    unittest.main()
