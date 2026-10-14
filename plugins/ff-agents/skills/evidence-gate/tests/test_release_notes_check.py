"""Offline tests for release_notes_check.py: a small git repo shaped like the game's (w1264).

    python3 -m unittest discover -s plugins/ff-agents/skills/evidence-gate/tests -p 'test_*.py' -v

The repo has the game's toggle file and merge-commit PRs: #1666 declares a toggle (Build 104's w243 case), #1671 is
an ordinary fix, #1650 removes a toggle (its content ships). The two corrections from Ben, 2026-10-13, are the
two failing notes below: Build 101's workflow line (w1190) and Build 104's toggled-off line (w1242).
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import release_notes_check as rnc  # noqa: E402

TOGGLE_TEMPLATE = '''namespace FFCore.Features
{
  public static class FeatureToggles
  {
%s
  }
}
'''

SHIPPED = '''    public static readonly FeatureToggle OldThing = new(
      "old-thing",
      FeatureKind.Simulation,
      "Ben (w1)",
      "2026-09-01",
      "2027-01-01",
      "Ship it.",
      "The Old Thing: a rotating beacon on every station.",
      false);
'''

RIDE = '''    public static readonly FeatureToggle InsertersRideStations = new(
      "inserters-ride-stations",
      FeatureKind.Simulation,
      "Ben (w243)",
      "2026-10-13",
      "2027-02-28",
      "Ben decides once he has played it: ship it " +
      "or drop it.",
      "Inserter Bots and Cargo Barges with both ends on a mobile station fly and land with it.",
      false);
'''

PLAIN_RELEASE = '''    public static readonly FeatureToggle Plain = new(
      "plain-thing",
      FeatureKind.Presentation,
      "Ben (w2)",
      "2026-09-01",
      "2027-01-01",
      "Ship it.",
      "A plain thing.",
      false,
      Release1_0);
'''


def run(repo, *args):
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise AssertionError(f"git {args}: {done.stderr}")
    return done.stdout.strip()


def write(repo, rel, text):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def commit(repo, message):
    run(repo, "add", "-A")
    run(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", message)


def merge_pr(repo, branch, number, build):
    """A branch off the current main, one commit made by build(), merged with a merge commit like GitHub's."""
    run(repo, "checkout", "-q", "-b", branch)
    build()
    commit(repo, f"{branch} work")
    run(repo, "checkout", "-q", "main")
    run(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "merge", "--no-ff", "-q", branch, "-m",
        f"Merge pull request #{number} from Final-Factory/{branch}")


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._folder = tempfile.TemporaryDirectory()
        repo = cls.repo = Path(cls._folder.name)
        run(repo, "init", "-q", "-b", "main")
        write(repo, rnc.TOGGLES_PATH, TOGGLE_TEMPLATE % (SHIPPED + PLAIN_RELEASE))
        write(repo, "Assets/Scripts/Station/Beacon.cs", "if (FeatureToggles.IsOn(FeatureToggles.OldThing)) Spin();\n")
        commit(repo, "base")
        cls.base = run(repo, "rev-parse", "HEAD")

        def declare():  # w243: the toggle and its gated code
            write(repo, rnc.TOGGLES_PATH, TOGGLE_TEMPLATE % (SHIPPED + RIDE + PLAIN_RELEASE))
            write(repo, "Assets/Scripts/Station/MobileStationUndockingSystem.cs",
                  "if (FeatureToggles.IsOn(FeatureToggles.InsertersRideStations)) TakeUnitsAlong();\n")
        merge_pr(repo, "ffbox-f-slot5-w243", 1666, declare)

        merge_pr(repo, "w1237-railgun-splash", 1671,
                 lambda: write(repo, "Assets/Scripts/Railgun/Splash.cs", "radius = 20;\n"))

        def ship():  # w1: the toggle is removed, the content ships
            write(repo, rnc.TOGGLES_PATH, TOGGLE_TEMPLATE % (RIDE + PLAIN_RELEASE))
            write(repo, "Assets/Scripts/Station/Beacon.cs", "Spin();\n")
        merge_pr(repo, "w1-ship-the-beacon", 1650, ship)
        cls.head = run(repo, "rev-parse", "HEAD")
        cls.rng = f"{cls.base}..{cls.head}"

    @classmethod
    def tearDownClass(cls):
        cls._folder.cleanup()

    def check(self, notes, accept=()):
        problems, gated, _ = rnc.check(self.repo, self.rng, notes, set(accept))
        return problems, gated


class ToggleParsing(Fixture):
    def test_reads_ids_descriptions_and_release(self):
        toggles = rnc.toggles_at(self.repo, self.head)
        self.assertEqual({"inserters-ride-stations", "plain-thing"}, set(toggles))
        self.assertIn("mobile station", toggles["inserters-ride-stations"]["description"])
        self.assertEqual("Release1_0", toggles["plain-thing"]["release"])
        self.assertEqual("Presentation", toggles["plain-thing"]["kind"])
        self.assertFalse(toggles["inserters-ride-stations"]["dev_default"])


class ToggledOff(Fixture):
    def test_only_the_toggle_declaring_pr_is_gated(self):
        _, gated = self.check("")
        self.assertEqual([1666], [pr["number"] for pr in gated])

    def test_builds_104_line_is_flagged(self):
        # Ben, 2026-10-13: "Mobile stations take their bots and barges with them / Isnt this behind a feature toggle?"
        problems, _ = self.check("* Mobile stations take their bots and barges with them\n")
        self.assertEqual(["toggled-off"], [p[0] for p in problems])
        self.assertIn("inserters-ride-stations", problems[0][3])

    def test_a_paraphrase_is_flagged(self):
        problems, _ = self.check("* Inserter Bots and Cargo Barges now ride along when a mobile station lifts off\n")
        self.assertEqual(["toggled-off"], [p[0] for p in problems])

    def test_naming_the_pr_is_flagged(self):
        problems, _ = self.check("* Riders on the platform (#1666)\n")
        self.assertTrue(any(p[0] == "toggled-off" for p in problems))

    def test_ungated_lines_pass(self):
        problems, _ = self.check("* Railgun splash reaches 20 u (was 10 u), with an impact ring showing that reach\n"
                                 "* Stations spin a rotating beacon\n")
        self.assertEqual([], problems)  # the beacon's toggle was removed in the range: it shipped

    def test_accepting_the_pr_clears_a_mixed_line(self):
        problems, _ = self.check("* Mobile stations take their bots and barges with them\n", accept={1666})
        self.assertEqual([], problems)


class DevWorkflow(Fixture):
    BUILD_101 = ("* Dev builds now come from master: every change lands there first, and the development branch "
                 "follows it\n")

    def test_builds_101_line_is_flagged(self):
        # Ben, 2026-10-13: "please dont put that kind of specific workflow information in patch notes for users."
        problems, _ = self.check(self.BUILD_101)
        self.assertTrue(problems)
        self.assertEqual({"dev workflow"}, {p[0] for p in problems})

    def test_the_standard_steam_branch_lines_pass(self):
        notes = ("**Build 104** Railgun Fixes (Live on the development branch)\n\n"
                 "Restart Steam to pick up the update on the development branch.\n")
        problems, _ = self.check(notes)
        self.assertEqual([], problems)

    def test_other_internal_words(self):
        for line in ("* Fixed in a pull request by a worker", "* The merge queue is faster", "* FFBox builds it",
                     "* CI runs the tests"):
            problems, _ = self.check(line + "\n")
            self.assertTrue(problems, line)


class SyncMergeOnTheBumpBranch(unittest.TestCase):
    """w1242: the bump branch merged origin/master in before its PR merged, and the check was run on
    <previous release>..<bump branch tip>. The sync merge was read as one PR carrying #1666's toggle, so the
    Railgun line (from #1671, also brought in by it) was flagged too."""

    @classmethod
    def setUpClass(cls):
        cls._folder = tempfile.TemporaryDirectory()
        repo = cls.repo = Path(cls._folder.name)
        run(repo, "init", "-q", "-b", "main")
        write(repo, rnc.TOGGLES_PATH, TOGGLE_TEMPLATE % PLAIN_RELEASE)
        commit(repo, "base")
        cls.base = run(repo, "rev-parse", "HEAD")
        run(repo, "checkout", "-q", "-b", "release/0.50.0.104")
        write(repo, "ProjectSettings/version.txt", "0.50.0.104\n")
        commit(repo, "0.50.0.104")
        run(repo, "checkout", "-q", "main")

        def declare():
            write(repo, rnc.TOGGLES_PATH, TOGGLE_TEMPLATE % (RIDE + PLAIN_RELEASE))
            write(repo, "Assets/Scripts/Station/MobileStationUndockingSystem.cs",
                  "if (FeatureToggles.IsOn(FeatureToggles.InsertersRideStations)) TakeUnitsAlong();\n")
        merge_pr(repo, "ffbox-f-slot5-w243", 1666, declare)
        merge_pr(repo, "w1237-railgun-splash", 1671,
                 lambda: write(repo, "Assets/Scripts/Railgun/Splash.cs", "radius = 20;\n"))
        run(repo, "checkout", "-q", "release/0.50.0.104")
        run(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "merge", "--no-ff", "-q", "main", "-m",
            "Merge origin/master into release/0.50.0.104")
        write(repo, "cicd/release-notes/0.50.0.104.md", "notes\n")
        commit(repo, "0.50.0.104 notes")
        cls.rng = f"{cls.base}..{run(repo, 'rev-parse', 'HEAD')}"

    @classmethod
    def tearDownClass(cls):
        cls._folder.cleanup()

    def test_the_sync_merge_is_read_as_the_prs_it_brought_in(self):
        numbers = [pr["number"] for pr in rnc.merged_prs(self.repo, self.rng)]
        self.assertIn(1666, numbers)
        self.assertIn(1671, numbers)
        self.assertNotIn(None, [pr["number"] for pr in rnc.merged_prs(self.repo, self.rng) if pr["merge"]])

    def test_only_the_toggled_line_is_flagged(self):
        problems, gated, _ = rnc.check(self.repo, self.rng, "* Railgun splash reaches 20 u\n", set())
        self.assertEqual([], problems)
        self.assertEqual([1666], [pr["number"] for pr in gated])
        problems, _, _ = rnc.check(self.repo, self.rng, "* Mobile stations take their bots and barges with them\n",
                                   set())
        self.assertEqual(["toggled-off"], [p[0] for p in problems])


class Cli(Fixture):
    def test_exit_codes(self):
        bad = Path(self._folder.name) / "bad.md"
        good = Path(self._folder.name) / "good.md"
        bad.write_text("* Mobile stations take their bots and barges with them\n", encoding="utf-8")
        good.write_text("* Railgun splash reaches 20 u\n", encoding="utf-8")
        args = ["--repo", str(self.repo), "--range", self.rng]
        self.assertEqual(1, rnc.main([str(bad), *args]))
        self.assertEqual(0, rnc.main([str(good), *args]))
        self.assertEqual(2, rnc.main([str(good), "--repo", str(self.repo), "--range", "nope..nope"]))


if __name__ == "__main__":
    unittest.main()
