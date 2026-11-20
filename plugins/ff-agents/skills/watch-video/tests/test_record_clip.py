"""record_clip --player: which process is the game behind this worker's player-slot lease (w4823)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import record_clip as rc  # noqa: E402

GAME = r"V:\ffw\players\slot3-0\player\FinalFactory.exe"
PY = r"C:\Python312\python.exe"


def proc(pid, ppid, name, exe):
    return {"pid": pid, "ppid": ppid, "name": name, "exe": exe}


class PickGamePid(unittest.TestCase):
    def test_scenario_runner_lease_records_its_game_child(self):
        # w4823, 2026-11-19 on lothdesktop: `ffnightly.py run --scenario` (python pid 28000, no window) held the lease
        # on slot 3-0 and launched the game from it; record_clip --player took 28000 and recorded nothing.
        procs = [proc(1000, 4, "bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"),
                 proc(28000, 1000, "python.exe", PY),
                 proc(28100, 28000, "FinalFactory.exe", GAME),
                 proc(28101, 28100, "UnityCrashHandler64.exe", r"V:\ffw\players\slot3-0\player\UnityCrashHandler64.exe")]
        windows = {28100}
        self.assertEqual(rc.pick_game_pid(28000, "3-0", procs, lambda p: p in windows), (28100, None))

    def test_player_launched_directly_keeps_its_own_pid(self):
        procs = [proc(500, 4, "python.exe", PY), proc(600, 500, "FinalFactory.exe", GAME)]
        self.assertEqual(rc.pick_game_pid(600, "3-0", procs, lambda p: True), (600, None))

    def test_detached_game_found_by_its_slot_folder(self):
        # the runner started the game through a launcher that exited, so the game is no longer below it in the tree
        procs = [proc(28000, 1000, "python.exe", PY), proc(29000, 4, "FinalFactory.exe", GAME),
                 proc(29500, 4, "FinalFactory.exe", r"V:\ffw\players\slot4-0\player\FinalFactory.exe")]
        self.assertEqual(rc.pick_game_pid(28000, "3-0", procs, lambda p: True), (29000, None))

    def test_pair_run_takes_the_game_in_the_lease_slot(self):
        procs = [proc(28000, 1000, "python.exe", PY), proc(28100, 28000, "FinalFactory.exe", GAME),
                 proc(28200, 28000, "FinalFactory.exe", r"V:\ffw\players\slot3-1\player\FinalFactory.exe")]
        self.assertEqual(rc.pick_game_pid(28000, "3-0", procs, lambda p: True), (28100, None))

    def test_no_game_yet_says_why(self):
        procs = [proc(28000, 1000, "python.exe", PY)]
        pid, why = rc.pick_game_pid(28000, "3-0", procs, lambda p: True)
        self.assertIsNone(pid)
        self.assertIn("runs no game yet", why)

    def test_another_workers_game_is_never_taken(self):
        procs = [proc(28000, 1000, "python.exe", PY),
                 proc(29500, 4, "FinalFactory.exe", r"V:\ffw\players\slot4-0\player\FinalFactory.exe")]
        self.assertIsNone(rc.pick_game_pid(28000, "3-0", procs, lambda p: True)[0])

    def test_slot_folder_is_not_a_prefix_match(self):
        self.assertFalse(rc.in_player_slot({"exe": r"V:\ffw\players\slot3-01\x.exe"}, "3-0"))
        self.assertTrue(rc.in_player_slot({"exe": "/Users/x/ffw/players/slot3-0/finalfactory.app/Contents/MacOS/x"}, "3-0"))

    def test_mac_and_linux_players_are_players(self):
        self.assertTrue(rc.is_player_process({"name": "finalfactory", "exe": "/p/slot1-0/finalfactory.app/Contents/MacOS/finalfactory"}))
        self.assertTrue(rc.is_player_process({"name": "finalfactory.x86_64", "exe": "/p/slot1-0/finalfactory.x86_64 -batchmode"}))
        self.assertFalse(rc.is_player_process({"name": "python3", "exe": "python3 scripts/nightly/ffnightly.py run"}))
        self.assertFalse(rc.is_player_process({"name": "finalfactory_tool.py", "exe": "finalfactory_tool.py"}))


if __name__ == "__main__":
    unittest.main()
