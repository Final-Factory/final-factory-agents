import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import quote_check as qc  # noqa: E402

# The person's words as w1334's packs held them (w1399, exp/packA-k3/b/words.md).
WORDS = """# The person's words, verbatim

- "I like C: Flat but can you make the add stop button button stand out just a little more and the pop out too cus it kind of bleeds into the rest of the panel"
- "ok i like the stops panel but i still think we can clean up the the rest of the panel too, either with better colors of ttext, cleaner component elements, etc. ... i want the ux to look more modern and clean"
"""

# A critic report's finding as it was written: emphasis, a quoted label, a line break inside the sentence.
REPORT = """2. **"+ Add stop" is the loudest thing on the panel and hard to read** (UGLY; items 2, 7, 8). In `zoom-s1-addstop-rect-2x`
   and `zoom-s2-bottom-rect-2x`, the pale blue (88,178,210) is 1.9x the brightest ref fill and 5x Deploy, and the label is
   2.12:1, where the words asked for "just a little more".
"""


class QuoteCheckTest(unittest.TestCase):
    def run_check(self, report: str, sources: dict[str, str]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rp = root / "report.md"
            rp.write_bytes(report.encode("utf-8"))
            (root / "src").mkdir()
            for name, text in sources.items():
                (root / "src" / name).write_bytes(text.encode("utf-8"))
            return qc.check(rp, [str(root / "src")])

    def test_the_w1399_misquote_is_caught(self):
        # The draft proof's line: the first piece is Ben's, the second he never wrote.
        report = ('| Control | 3 UGLY. Ben\'s next message asked for exactly these: "better colors of ttext, cleaner '
                  'component elements ... making the add stop button look nicer" |\n')
        n, misses, _ = self.run_check(report, {"words.md": WORDS})
        self.assertEqual(n, 1)
        self.assertEqual([m[2] for m in misses], ["making the add stop button look nicer"])
        self.assertEqual(misses[0][0], 1)

    def test_a_copied_quote_passes_through_curly_marks_ellipses_wraps_and_emphasis(self):
        report = ("Critic A: “'+ Add stop' is the loudest thing on the panel and hard to read … the label is\n"
                  "2.12:1, where the words asked for 'just a little more'”.\n")
        n, misses, _ = self.run_check(report, {"critic.md": REPORT})
        self.assertEqual((n, misses), (1, []))

    def test_a_retyped_critic_quote_is_caught(self):
        # w1399's draft: "A dark box sits behind every list line"; the report said "A dark box behind every list line".
        n, misses, _ = self.run_check('A: "A dark box sits behind every list line".\n',
                                      {"critic.md": "1. **A dark box behind every list line** (s1 and s2)"})
        self.assertEqual(len(misses), 1)

    def test_code_spans_short_quotes_and_the_report_itself_are_not_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            rp = Path(tmp) / "proof.md"
            rp.write_bytes(b'Run `ui_look.py colour "a b c d"`; the critic said "minor".\nShe said "nothing like this at all".\n')
            n, misses, n_files = qc.check(rp, [tmp])
        self.assertEqual(n_files, 0)                       # the report is never its own source
        self.assertEqual(n, 1)                             # only the three-word quote outside the code span
        self.assertEqual(len(misses), 1)

    def test_a_json_source_is_read_as_its_strings(self):
        brief = json.dumps({"brief": "can you also go through the latest discord bug reports and fix the ones that are\n"
                                     "clearly bugs"})
        n, misses, _ = self.run_check('The words: "fix the ones that are clearly bugs".\n', {"brief.json": brief})
        self.assertEqual((n, misses), (1, []))

    def test_main_exits_1_on_a_miss_and_0_without(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "words.md").write_bytes(WORDS.encode("utf-8"))
            bad, good = root / "bad.md", root / "good.md"
            bad.write_bytes(b'Ben: "make the add stop button look nicer".\n')
            good.write_bytes(b'Ben: "make the add stop button button stand out just a little more".\n')
            self.assertEqual(qc.main([str(bad), str(root / "words.md")]), 1)
            self.assertEqual(qc.main([str(good), str(root / "words.md")]), 0)


if __name__ == "__main__":
    unittest.main()
