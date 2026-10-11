"""Tests for bin/ffdiscord, the POSIX launcher: how it picks a Python (w912).

On Windows git-bash, `python3` resolves to the Microsoft Store "App Execution Alias"
(...\\WindowsApps\\python3.exe), which exists but only prints "Python was not found". The
launcher must run past it to a real Python. These cases fake that machine in a temp dir: a PATH
holding only coreutils plus the fake interpreters under test, so the host's real Python never
leaks in. No network, no Discord.

Run:  python3 -m unittest discover -s plugins/ff-discord/skills/discord-cli -p 'test_ffdiscord_shim.py'
"""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SHIM = os.path.join(HERE, "bin", "ffdiscord")
TOOLS = ("basename", "dirname", "ls", "sort", "tail", "cat", "head", "tr")

STORE_STUB = "#!/bin/sh\necho 'Python was not found; run without arguments to install from the Microsoft Store' >&2\nexit 49\n"
# A working "Python": ignores the one-liner probe's source and answers the way python would.
REAL_PY = "#!/bin/sh\ncase \"$1\" in -c) exit 0;; esac\necho \"real-python ran $*\"\n"
PY_LAUNCHER = "#!/bin/sh\n[ \"$1\" = -3 ] || exit 2\nshift\ncase \"$1\" in -c) exit 0;; esac\necho \"py-launcher ran $*\"\n"


def write_exe(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


class ShimPythonLookup(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ffdiscord-shim-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.home = os.path.join(self.root, "home")
        os.makedirs(self.home)
        # The shim finds ffdiscord.py through FFDISCORD_CLI; the fake interpreters never read it.
        self.cli = os.path.join(self.root, "cli", "ffdiscord.py")
        os.makedirs(os.path.dirname(self.cli))
        open(self.cli, "w").close()
        self.tools = os.path.join(self.root, "tools")
        os.makedirs(self.tools)
        for t in TOOLS:
            src = shutil.which(t)
            self.assertIsNotNone(src, t)
            os.symlink(src, os.path.join(self.tools, t))

    def run_shim(self, path_dirs, **extra_env):
        env = {
            "HOME": self.home,
            "PATH": os.pathsep.join(list(path_dirs) + [self.tools]),
            "FFDISCORD_CLI": self.cli,
        }
        env.update(extra_env)
        return subprocess.run(["/bin/sh", SHIM, "read", "dev_chat"], env=env,
                              capture_output=True, text=True)

    def bin_dir(self, name, **exes):
        d = os.path.join(self.root, name)
        for exe, body in exes.items():
            write_exe(os.path.join(d, exe), body)
        return d

    def test_store_stub_first_real_python_second(self):
        # The LothDesktop case: python3 is the Store alias, `python` is a real install.
        stub = self.bin_dir("Microsoft/WindowsApps", python3=STORE_STUB)
        real = self.bin_dir("Python313", python=REAL_PY)
        r = self.run_shim([stub, real])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("real-python ran", r.stdout)
        self.assertIn("read dev_chat", r.stdout)

    def test_stub_outside_windowsapps_still_skipped(self):
        # The check is "does it run", not "is it under WindowsApps".
        stub = self.bin_dir("somewhere", python3=STORE_STUB)
        real = self.bin_dir("Python313", python=REAL_PY)
        r = self.run_shim([stub, real])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("real-python ran", r.stdout)

    def test_plain_python3_still_works(self):
        r = self.run_shim([self.bin_dir("usrbin", python3=REAL_PY)])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_py_launcher(self):
        stub = self.bin_dir("Microsoft/WindowsApps", python3=STORE_STUB, python=STORE_STUB)
        launcher = self.bin_dir("Windows", py=PY_LAUNCHER)
        r = self.run_shim([stub, launcher])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("py-launcher ran", r.stdout)

    def test_known_install_dir_when_path_has_only_the_stub(self):
        stub = self.bin_dir("Microsoft/WindowsApps", python3=STORE_STUB, python=STORE_STUB)
        write_exe(os.path.join(self.home, "AppData/Local/Programs/Python/Python313/python.exe"), REAL_PY)
        r = self.run_shim([stub])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("real-python ran", r.stdout)

    def test_newest_install_dir_wins(self):
        base = os.path.join(self.home, "AppData/Local/Programs/Python")
        write_exe(os.path.join(base, "Python39/python.exe"), "#!/bin/sh\ncase \"$1\" in -c) exit 0;; esac\necho py39\n")
        write_exe(os.path.join(base, "Python313/python.exe"), "#!/bin/sh\ncase \"$1\" in -c) exit 0;; esac\necho py313\n")
        write_exe(os.path.join(base, "Python310/python.exe"), "#!/bin/sh\ncase \"$1\" in -c) exit 0;; esac\necho py310\n")
        r = self.run_shim([])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split()[0], "py313")

    def test_override(self):
        stub = self.bin_dir("Microsoft/WindowsApps", python3=STORE_STUB)
        mine = self.bin_dir("mine", python=REAL_PY)
        r = self.run_shim([stub], FFDISCORD_PYTHON=os.path.join(mine, "python"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("real-python ran", r.stdout)

    def test_bad_override_says_so(self):
        r = self.run_shim([], FFDISCORD_PYTHON=os.path.join(self.root, "nope.exe"))
        self.assertEqual(r.returncode, 127)
        self.assertIn("FFDISCORD_PYTHON", r.stderr)

    def test_nothing_found_names_what_was_tried(self):
        stub = self.bin_dir("Microsoft/WindowsApps", python3=STORE_STUB, python=STORE_STUB)
        r = self.run_shim([stub])
        self.assertEqual(r.returncode, 127)
        for needle in ("no working Python 3", "python3", "python", "py -3", "AppData/Local/Programs/Python",
                       "Microsoft Store", "FFDISCORD_PYTHON"):
            self.assertIn(needle, r.stderr)
        self.assertNotIn("real-python", r.stdout)

    def test_real_store_install_under_windowsapps_is_the_last_resort(self):
        # A Python installed FROM the Store also lives under WindowsApps and does run.
        stub = self.bin_dir("Microsoft/WindowsApps", python3=REAL_PY)
        r = self.run_shim([stub])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("real-python ran", r.stdout)


if __name__ == "__main__":
    unittest.main()
