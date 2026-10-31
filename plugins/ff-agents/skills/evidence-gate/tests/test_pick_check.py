"""Offline tests for the 'Picked:' rule in pr_evidence.py (w2669). No network, no gh.

    python3 -m unittest discover -s plugins/ff-agents/skills/evidence-gate/tests -p 'test_*.py' -v

The second correction of one kind: a worker built a different design than the one the person picked.
w1323: Ben's screenshot showed the new assembler, the worker changed the classic one ("what no, i was talking about
updating the new assembler model, not the old one lol"). w2580: Ben picked "C, the Tiles" from a card whose C and D
stills had not rendered for him (w2664); his words pointed at the bottom-left card mock and the worker built the
bottom-centre tiles ("That's not the hover panel mock I chose. I wanted the tile on the left above the controls panel").
"""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import pr_evidence as pe  # noqa: E402
from test_pr_evidence import GOOD, edit  # noqa: E402

# The pick as it was relayed on w2580, with Ben's own words.
BRIEF_2580 = ('Brief (Ben): picked "C, the Tiles", and: "i like the tiles but i\'m worried it might get cut off by the '
              'objectives panel"\n')

GOOD_PICK = ('Picked (Ben): still: proofs/mock-card-bottom-left.png; shows: one tile at the bottom left, above the '
             'station controls panel, clear of the objectives panel; words: "i\'m worried it might get cut off by the '
             'objectives panel"; matches: the card mock sits on the left, away from the objectives panel, which is what '
             'his worry points at; beside: proofs/built-beside-picked.png')


def with_pick(line, brief=BRIEF_2580):
    return brief + edit(GOOD, "Not verified: nothing", line + "\nNot verified: nothing")


def pick_problems(body):
    return [p for p in pe.check(body)[0] if "Picked" in p or "pick is named" in p]


class TriggerTest(unittest.TestCase):
    def test_the_relayed_picks_count(self):
        for text in ('Ben picked "C, the Tiles"', "the label Ben picked", "the cut Ben chose", "picked by lothsahn's brief",
                     "option C", "look A: a tall spire", 'he said "C, the Tiles"', "i picked the second one"):
            self.assertTrue(pe.names_a_pick(text), text)

    def test_words_that_are_not_a_pick_do_not(self):
        # Each is from a game PR merged 2026-10-20..31 that had no design pick.
        for text in ("chosen tab #2A839C both", "drop boxes get picked up by player bots", "the 137 classes "
                     "test_select.py picks", "lothsahn chose to merge without them", "about 1 picked Terra World in 8",
                     "t2 line B, the operator rows", "when Value range is picked", "it looks a bit dark",
                     "a clean cherry-picked commit", "PICKED 100.104.235.48"):
            self.assertFalse(pe.names_a_pick(text), text)


class PickedLineTest(unittest.TestCase):
    def test_2580_as_built_fails_on_the_missing_line(self):
        problems = pick_problems(BRIEF_2580 + GOOD)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("no 'Picked:' line", problems[0])
        self.assertIn("w2580", problems[0])

    def test_no_pick_named_needs_no_line(self):
        self.assertEqual(pick_problems(GOOD), [])

    def test_a_full_line_passes(self):
        self.assertEqual(pick_problems(with_pick(GOOD_PICK)), [])

    def test_a_letter_alone_fails(self):
        # What w2580's brief carried: the letter and the label, nothing of the picture.
        problems = "\n".join(pick_problems(with_pick(
            'Picked (Ben): still: C, the Tiles; shows: the tiles; words: "i like the tiles"; matches: yes; beside: C')))
        self.assertIn("is not a still file or link", problems)
        self.assertIn("say what is visible in the still", problems)
        self.assertIn("how their words fit", problems)
        self.assertIn("'Picked' beside", problems)

    def test_words_must_be_the_persons(self):
        problems = pick_problems(with_pick(GOOD_PICK.replace("i'm worried it might get cut off by the objectives panel",
                                                             "keep it clear of the objectives")))
        self.assertTrue(any("not in the brief word for word" in p for p in problems), problems)

    def test_words_must_be_quoted(self):
        problems = pick_problems(with_pick(GOOD_PICK.replace('"i\'m worried it might get cut off by the objectives '
                                                             'panel"', "he was worried about the objectives panel")))
        self.assertTrue(any("in quotation marks" in p for p in problems), problems)

    def test_who_and_beside_are_needed(self):
        problems = "\n".join(pick_problems(with_pick(
            GOOD_PICK.replace("Picked (Ben):", "Picked:").replace("; beside: proofs/built-beside-picked.png", ""))))
        self.assertIn("does not say who picked", problems)
        self.assertIn("no 'beside:' part", problems)

    def test_na_needs_a_reason(self):
        self.assertTrue(pick_problems(with_pick("Picked: n/a")))
        problems, notes = pe.check(with_pick("Picked: n/a (Ben chose the cut depth, a number, not a design or a mock)"))
        self.assertFalse([p for p in problems if "Picked" in p or "pick is named" in p], problems)
        self.assertTrue(any("no pick" in n for n in notes), notes)

    def test_a_multi_line_pick_reads_its_bullets(self):
        lines = GOOD_PICK.replace("; ", "\n  - ").replace("Picked (Ben): still:", "Picked (Ben):\n  - still:")
        self.assertEqual(pick_problems(with_pick(lines)), [])


class BeforeBuildingTest(unittest.TestCase):
    """--pick: the brief or the first step's note, before anything is built, so no 'beside:' yet."""

    def run_pick(self, text):
        with tempfile.TemporaryDirectory() as d:
            note = Path(d) / "pick.md"
            note.write_text(text, encoding="utf-8")
            return pe.main(["--pick", str(note)])

    def test_a_pick_without_beside_passes_before_building(self):
        before = GOOD_PICK.replace("; beside: proofs/built-beside-picked.png", "")
        self.assertEqual(self.run_pick(BRIEF_2580 + before + "\n"), 0)

    def test_the_2580_brief_alone_fails(self):
        self.assertEqual(self.run_pick(BRIEF_2580), 1)


if __name__ == "__main__":
    unittest.main()
