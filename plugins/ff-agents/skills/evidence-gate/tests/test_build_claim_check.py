import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_claim_check as bc  # noqa: E402

# w1765's closing report as the ledger holds it (2026-10-22): the tabs "in Build 111" from git alone.
W1765 = ("Nothing to port: pre-1.0 and Build 111 already contain the tabs and filter (#1760) and the quit-save fix (#1794); "
         "checked with git by worker 28cd4257. Players lack them only because Steam default still runs Build 100. They "
         "ship when Ben sets Build 111 live (w1588).")

# The orchestrator's answer to "figure out what happened", from a grep of master.
ORCHESTRATOR = "The 1.0 development build still has the tabs: SaveGamePanel.cs on master has them since #1760."

# w1315's DONE, the first miss: done on master, no word of which build players run carries it.
W1315_DONE = """Saves and Autosaves tabs plus a name filter on the Load list, merged in #1760 (tests green).

DONE: w1315
Learned: nothing new
"""


class BuildClaimCheckTest(unittest.TestCase):
    def test_the_w1765_git_claim_is_caught(self):
        problems = bc.check(W1765)
        self.assertTrue(any("code or git" in p and "Build 111 already contain" in p for p in problems), problems)

    def test_the_orchestrators_grep_claim_is_caught(self):
        problems = bc.check(ORCHESTRATOR)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("1.0 development build still has", problems[0])

    def test_a_run_passes(self):
        text = ("Measured: ran Build 111 from pre-release on beast and opened Load: the Saves and Autosaves tabs show "
                "and the filter finds a save.")
        self.assertEqual(bc.check(text), [])

    def test_a_guess_naming_the_build_to_run_passes(self):
        text = "Guess (from git): Build 111 contains #1760; to check, run Build 111 from pre-release and open Load."
        self.assertEqual(bc.check(text), [])

    def test_a_guess_naming_no_build_to_run_is_caught(self):
        problems = bc.check("Guess: Build 111 contains #1760.")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("names no build to run", problems[0])

    def test_sentences_without_a_build_claim_pass(self):
        text = ("Players have complained on Discord about the clutter. The build server has 4 cores. "
                "I merged #1760 into master. Version 1.0.0.112 was bumped at 19:10Z, see `Build 111 has the tabs`.")
        self.assertEqual(bc.check(text), [])

    def test_the_w1315_done_lacks_where_it_ships(self):
        problems = bc.check(W1315_DONE, done=True)
        self.assertTrue(any("Ships in" in p for p in problems), problems)
        self.assertTrue(any("pre-1.0" in p for p in problems), problems)

    def test_a_done_naming_where_it_ships_passes(self):
        text = W1315_DONE.replace("DONE: w1315", "Ships in: development, the next master bump (1.0.0.113); no pre-release "
                                  "or default build has it\npre-1.0: cherry-pick needed (w1771)\nDONE: w1315")
        self.assertEqual(bc.check(text, done=True), [])

    def test_a_pre10_line_with_no_answer_is_caught(self):
        text = "Ships in: development, Build 112\npre-1.0: maybe later\n"
        problems = bc.check(text, done=True)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("pre-1.0: maybe later", problems[0])

    def test_ships_in_without_a_build_is_caught(self):
        problems = bc.check("Ships in: soon\npre-1.0: not needed: 1.0 replaces default first\n", done=True)
        self.assertEqual(len(problems), 1, problems)

    def test_main_exits_1_on_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.md"
            p.write_text(W1765, encoding="utf-8")
            self.assertEqual(bc.main([str(p)]), 1)
            p.write_text("Merged #1760.", encoding="utf-8")
            self.assertEqual(bc.main([str(p)]), 0)


if __name__ == "__main__":
    unittest.main()
