"""Tests for check_frontmatter.py (w1479): the ci-release description YAML cut at " #dev-patch-notes" is the fixture."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import check_frontmatter as cf  # noqa: E402

CUT = "description: Cut a release ... then post the patch notes as Max in #dev-patch-notes. Never start it on your own initiative."


class Tests(unittest.TestCase):
    def test_hash_in_a_plain_description_is_caught(self):
        self.assertIn("YAML comment", cf.problem(cf.description(f"---\nname: ci-release\n{CUT}\n---\n# body\n")))

    def test_quoted_and_plain_descriptions_pass(self):
        self.assertIsNone(cf.problem(cf.description('---\nname: x\ndescription: "posts in #dev-patch-notes: done"\n---\n')))
        self.assertIsNone(cf.problem(cf.description("---\nname: x\ndescription: Use when asked, never on its own.\n---\n")))
        self.assertIsNone(cf.problem("C# and x#y stay text (no space before the hash)"))

    def test_colon_space_is_caught(self):
        self.assertIn("YAML error", cf.problem("one thing: another"))

    def test_problems_names_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "plugins/ff-agents/skills/ci-release")
            p.mkdir(parents=True)
            (p / "SKILL.md").write_text(f"---\nname: ci-release\n{CUT}\n---\n", encoding="utf-8")
            found = cf.problems(Path(d))
            self.assertEqual(len(found), 1)
            self.assertIn("ci-release", found[0])

    def test_the_repo_is_clean(self):
        self.assertEqual(cf.problems(Path(__file__).resolve().parent.parent), [])


if __name__ == "__main__":
    unittest.main()
