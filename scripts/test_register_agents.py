"""registerAgents.sh records its checkout in publish-skills' marker, but never a clone in a temp folder (w2655).

A worker on BEAST cloned final-factory-agents into its $TMPDIR, ran registerAgents.sh there, and the marker named
that clone until its temp folder was swept; every later publish-skills run on the machine then stopped at step 1.

Run: python3 -m unittest scripts/test_register_agents.py -v
"""
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = shutil.which("sh")


def make_checkout(parent: str, name: str) -> str:
    """A minimal checkout: the script and the marketplace file record_checkout looks for."""
    co = os.path.join(parent, name)
    os.makedirs(os.path.join(co, ".claude-plugin"))
    shutil.copy(os.path.join(REPO, "registerAgents.sh"), co)
    shutil.copy(os.path.join(REPO, ".claude-plugin", "marketplace.json"), os.path.join(co, ".claude-plugin"))
    return co


@unittest.skipIf(SH is None, "needs a POSIX sh")
class RecordCheckoutTest(unittest.TestCase):
    def setUp(self):
        # The lasting checkout must sit outside every temp folder, so it goes beside the repo, not in tempfile's dir.
        self.lasting_root = os.path.join(REPO, f".test-register-{os.getpid()}")
        os.makedirs(self.lasting_root)
        self.addCleanup(shutil.rmtree, self.lasting_root, True)
        lowered = self.lasting_root.replace("\\", "/").lower() + "/"
        if "/tmp/" in lowered or "/temp/" in lowered or lowered.startswith("/var/folders/"):
            self.skipTest(f"the repo itself is under a temp folder ({REPO})")
        self.tmp = tempfile.mkdtemp(prefix="ffa-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.lasting_root, "home")
        os.makedirs(self.home)
        self.marker = os.path.join(self.home, ".claude", "final-factory-agents-checkout")

    def run_marker_only(self, checkout: str, tmpdir: str):
        env = dict(os.environ, HOME=self.home, TMPDIR=tmpdir, TMP=tmpdir, TEMP=tmpdir)
        return subprocess.run([SH, os.path.join(checkout, "registerAgents.sh"), "--marker-only"],
                              env=env, capture_output=True, text=True, timeout=60)

    def read_marker(self):
        with open(self.marker, encoding="utf-8") as f:
            return f.read().strip()

    @staticmethod
    def same(a: str, b: str) -> bool:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))

    def test_a_lasting_checkout_is_recorded(self):
        co = make_checkout(self.lasting_root, "final-factory-agents")
        r = self.run_marker_only(co, self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.same(self.read_marker(), co), self.read_marker())

    def test_a_clone_in_tmpdir_keeps_the_lasting_marker(self):
        lasting = make_checkout(self.lasting_root, "final-factory-agents")
        self.assertEqual(self.run_marker_only(lasting, self.tmp).returncode, 0)
        before = self.read_marker()
        clone = make_checkout(self.tmp, "fa-w2558")
        r = self.run_marker_only(clone, self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_marker(), before)
        self.assertIn("checkout marker kept on", r.stderr)

    def test_a_tmp_path_is_refused_even_when_tmpdir_is_elsewhere(self):
        # The w2558 clone's path, F:/ffw/tmp/ffa-<session>/..., is caught by its /tmp/ component alone.
        parent = os.path.join(self.lasting_root, "tmp", "ffa-30d16bd4")
        os.makedirs(parent)
        clone = make_checkout(parent, "fa-w2558")
        r = self.run_marker_only(clone, self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.marker))
        self.assertIn("WARNING", r.stderr)


if __name__ == "__main__":
    unittest.main()
