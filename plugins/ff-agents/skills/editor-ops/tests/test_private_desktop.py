"""private_desktop.sh (w5285): a private headless desktop that leaves no FUSE mount in a temp folder.

Fixture: the two mountinfo lines w5276 read on biscuit (2026-11-23) under worker bd1baf7b's temp folder, left by a
`dbus-run-session -- gnome-shell` that w994 ran with XDG_RUNTIME_DIR at <temp>/w994/gs.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "private_desktop.sh"
BASH = shutil.which("bash")
TEMP = "/home/u/ffw/tmp/ffa-bd1baf7b"
MOUNTINFO = "\n".join([
    "29 1 259:2 / / rw,relatime shared:1 - ext4 /dev/nvme0n1p2 rw",
    "901 44 0:60 / /run/user/1000/gvfs rw,nosuid,nodev,relatime shared:500 - fuse.gvfsd-fuse gvfsd-fuse rw,user_id=1000",
    "902 44 0:61 / /run/user/1000/doc rw,nosuid,nodev,relatime shared:501 - fuse.portal portal rw,user_id=1000",
    f"5182 44 0:80 / {TEMP}/w994/gs/gvfs rw,nosuid,nodev,relatime shared:1132 - fuse.gvfsd-fuse gvfsd-fuse rw,user_id=1000",
    f"5225 44 0:81 / {TEMP}/w994/gs/doc rw,nosuid,nodev,relatime shared:1229 - fuse.portal portal rw,user_id=1000",
    f"77 44 0:9 / {TEMP}/scratch rw - tmpfs tmpfs rw",
]) + "\n"
SERVICES = [
    "org.gtk.vfs.Daemon.service", "org.gtk.vfs.UDisks2VolumeMonitor.service",
    "org.freedesktop.portal.Documents.service", "org.freedesktop.portal.Desktop.service",
    "org.freedesktop.impl.portal.desktop.gnome.service",
    "org.gnome.Shell.CalendarServer.service", "org.a11y.Bus.service", "ca.desrt.dconf.service",
]


@unittest.skipUnless(BASH, "needs bash")
class PrivateDesktopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pd-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "mountinfo").write_text(MOUNTINFO)
        svc = self.tmp / "services"
        svc.mkdir()
        for n in SERVICES:
            (svc / n).write_text(f"[D-BUS Service]\nName={n[:-8]}\nExec=/bin/true\n")
        self.env = dict(os.environ, FF_MOUNTINFO=(self.tmp / "mountinfo").as_posix(),
                        FF_DBUS_SERVICE_DIRS=svc.as_posix())
        self.env.pop("XDG_RUNTIME_DIR", None)

    def run_sh(self, *args, **env):
        return subprocess.run([BASH, SCRIPT.as_posix(), *args], env={**self.env, **env},
                              capture_output=True, text=True, timeout=60)

    def test_mounts_names_both_biscuit_fuse_mounts_and_exits_1(self):
        r = self.run_sh("mounts", TEMP)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(sorted(r.stdout.split("\n")[:2]),
                         [f"{TEMP}/w994/gs/doc fuse.portal", f"{TEMP}/w994/gs/gvfs fuse.gvfsd-fuse"])
        self.assertNotIn("scratch", r.stdout, "a tmpfs is not a FUSE mount")
        self.assertNotIn("/run/user", r.stdout, "the person's own session is never ours")

    def test_mounts_is_clean_for_another_temp_folder(self):
        r = self.run_sh("mounts", "/home/u/ffw/tmp/ffa-bd1baf7")  # a prefix of the name, not the folder
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_refuses_a_runtime_folder_in_a_temp_folder(self):
        r = self.run_sh("plan", (self.tmp / "out").as_posix(), XDG_RUNTIME_DIR=f"{TEMP}/w994/gs")
        self.assertEqual(r.returncode, 2)
        self.assertIn("w5285", r.stderr)
        self.assertFalse((self.tmp / "out").exists(), "nothing is made before the refusal")

    def test_plan_keeps_the_real_runtime_folder_and_leaves_out_gvfs_and_portals(self):
        out = self.tmp / "out"
        r = self.run_sh("plan", out.as_posix())
        self.assertEqual(r.returncode, 0, r.stderr)
        uid = subprocess.run([BASH, "-c", "id -u"], capture_output=True, text=True).stdout.strip()
        self.assertIn(f"XDG_RUNTIME_DIR=/run/user/{uid}", r.stdout)
        for want in ("GVFS_DISABLE_FUSE=1", "GIO_USE_VFS=local", "GTK_USE_PORTAL=0",
                     f"--config-file={out.as_posix()}/session.conf", "gnome-shell --headless"):
            self.assertIn(want, r.stdout)
        kept = sorted(p.name for p in (out / "dbus-services").iterdir())
        self.assertEqual(kept, ["ca.desrt.dconf.service", "org.a11y.Bus.service",
                                "org.gnome.Shell.CalendarServer.service"])
        conf = (out / "session.conf").read_text()
        self.assertIn(f"<servicedir>{out.as_posix()}/dbus-services</servicedir>", conf)
        self.assertNotIn("<standard_session_servicedirs", conf, "the system service folders would bring gvfs back")


    def test_parse_log_reads_the_on_demand_x_display(self):
        # Mutter starts Xwayland only at the first X client (w5290, biscuit: no Xwayland in 60 s), so start reads the
        # display from this log line instead of waiting for an Xwayland process.
        log = self.tmp / "gnome-shell.log"
        log.write_text("libmutter-Message: 09:27:25.981: Running GNOME Shell (using mutter 46.2) as a Wayland display server\n"
                       "libmutter-Message: 09:27:26.010: Using public X11 display :1, (using :2 for managed services)\n"
                       "gnome-shell[4154920]: GNOME Shell started at Mon Nov 23 2026 09:27:26\n")
        r = self.run_sh("parse-log", log.as_posix())
        self.assertEqual((r.returncode, r.stdout.strip()), (0, ":1"), r.stderr)
        log.write_text("gnome-shell[1]: GNOME Shell started\n")
        self.assertEqual(self.run_sh("parse-log", log.as_posix()).stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
