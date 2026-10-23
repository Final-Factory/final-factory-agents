import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import copy_check as cc  # noqa: E402

# The live Patch notes intro on final-factory.com (w1825, 2026-10-23). It had passed a word lint clean.
# Ben: "this text is LLM speak lol i told you not to use llm prose!"
W1825_INTRO = ("Every build since late September 2026, newest first. New builds reach Steam's opt-in betas first. "
               "Older updates are in Steam news.\n")

# Feature paragraphs of 34, 35 and 36 words, the shape the w1825 worker noted in its own copy.
TEMPLATE_PARAGRAPHS = """\
Build sprawling factories across a solar system, linking mines to smelters with belts and drones. Every planet
has its own resources, and moving them where they are needed is the heart of the game.

Fight off waves of raiders that grow stronger as your factory grows. Turrets, shields and fleets of warships keep
your lines running, while research opens heavier weapons and tougher armour for the long fights later.

Play with friends in online co-op, sharing one big factory and one research tree across the whole map. Everyone builds
at once, splits the work as they like, and the game keeps every player in step.
"""

# Lines Ben sent back on 2026-10-02 as awkward. Nothing here is a stock phrase or a rhythm a tool can count: only a
# reader catches it, which is why no flags is never a pass.
BEN_2026_10_02 = "I make Final Factory. Build one space factory with your friends.\n"

# A control in the voice Ben asked for: short, plain, uneven.
CASUAL = """\
Patch notes for every build. The newest is up top.

Big one this week: belts got a full rework, so old saves will rebuild their lines the first time you load them, which
takes a few seconds on a large map. Sorry about that. It only happens once.
"""

PATCH_LIST = """\
## 1.0.0.12

- Enemy camps now respawn after a raid is beaten.
- Fixed a crash when a mass driver lost power mid-shot.
- Belts show their speed in the hover card.
- Turrets stop firing at wrecks.
- The minimap remembers its zoom.
- Mining drones return home when their station is full.
- Enemy camps on moons no longer spawn inside rock.
"""


class CopyCheckTest(unittest.TestCase):
    def test_the_w1825_intro_is_flagged_for_rhythm_and_explainers(self):
        flags = cc.check_text(W1825_INTRO)
        self.assertTrue(any("rhythm: sentences of 8, 7, 6 words" in f for f in flags), flags)
        explainers = [f for f in flags if "explainer" in f]
        self.assertEqual(len(explainers), 2, flags)
        self.assertTrue(any("newest first" in f for f in explainers))
        self.assertTrue(any("Older updates are in Steam news." in f for f in explainers))

    def test_paragraphs_of_one_length_are_flagged(self):
        counts = [len(cc.words(t)) for _, k, t in cc.blocks(TEMPLATE_PARAGRAPHS) if k == "p"]
        self.assertEqual(counts, [34, 35, 36])
        flags = cc.check_text(TEMPLATE_PARAGRAPHS)
        self.assertTrue(any("3 of 3 paragraphs are 34-36 words" in f for f in flags), flags)

    def test_no_flags_is_not_a_pass(self):
        # Ben's 2026-10-02 lines raise nothing, and the tool says so without calling it clean.
        self.assertEqual(cc.check_text(BEN_2026_10_02), [])
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "copy.txt"
            p.write_text(BEN_2026_10_02, encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                code = cc.main([str(p)])
        self.assertEqual(code, 0)
        self.assertIn("This is not a pass", out.getvalue())
        self.assertIn("fresh critic", out.getvalue())

    def test_casual_uneven_copy_raises_nothing(self):
        self.assertEqual(cc.check_text(CASUAL), [])

    def test_parallel_openings_close_together(self):
        text = ("New ships fly faster now. New belts carry twice as much. Turrets got cheaper. "
                "New enemies show up on moons.\n")
        flags = cc.check_text(text)
        self.assertIn('<copy>:1,1,1: parallel openings: 3 close together start with "new ..."', flags)

    def test_a_subject_repeated_far_apart_in_patch_notes_is_fine(self):
        self.assertEqual(cc.check_text(PATCH_LIST), [])

    def test_stock_phrases_and_taglines(self):
        flags = cc.check_text("# Embark on an immersive journey\n\nWhether you're a veteran or new, it awaits.\n")
        joined = "\n".join(flags).lower()
        for word in ("embark", "immersive", "journey", "whether you're", "awaits"):
            self.assertIn(word, joined)

    def test_game_words_are_not_stock(self):
        self.assertEqual(cc.check_text("One unlocks Dyson Spheres, two unlock Singularity Navigation.\n"), [])
        self.assertEqual(cc.check_text("Out in space you'll find the ruins of an old civilization.\n"), [])

    def test_em_dashes(self):
        flags = cc.check_text("Belts are faster — much faster — and cheaper too.\n")
        self.assertTrue(any("em dashes: 2" in f for f in flags), flags)

    def test_html_is_read_as_its_visible_paragraphs(self):
        page = ("<html><head><title>x</title><style>p{}</style></head><body><nav>Home Patch notes</nav>"
                f"<main><h1>Patch notes</h1><p>{W1825_INTRO}</p><script>var a = 'newest first';</script>"
                "</main></body></html>")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "index.html"
            p.write_text(page, encoding="utf-8")
            flags = cc.check_text(cc.read(str(p)))
        self.assertEqual(len([f for f in flags if "explainer" in f]), 2, flags)

    def test_code_and_frontmatter_are_skipped(self):
        text = "---\ntitle: Embark on an immersive journey\n---\n\n```\nnewest first\n```\n\nShort and plain.\n"
        self.assertEqual(cc.check_text(text), [])


if __name__ == "__main__":
    unittest.main()
