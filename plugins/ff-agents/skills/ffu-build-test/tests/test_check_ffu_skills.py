"""Tests for check_ffu_skills.py: each kind of problem it must catch, on a small fake ffu tree (w2895, M0.8)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_ffu_skills as c  # noqa: E402

GOOD = """---
name: ffu-x
description: x
---

```sh
$B/ffu-headless run --start factory:2000:1 --ticks 600 --record "$TMPDIR/a"
cargo build --release -p ffu-headless --features agent-api
./tools/check_sim_rules.sh
printf '%s\\n' '{"jsonrpc":"2.0","id":1,"method":"stats"}' | $B/ffu-headless serve --start factory:2000:1
```

Then `ffu-headless replay dir`, `ffu_query` and `ffu_engine`; `gh run list -R Final-Factory/ffu --commit <sha>`.
See `/ff-agents:ffu-drive`. There is no Unity editor here.
"""


def fake_ffu(root: Path) -> Path:
    ffu = root / "ffu"
    h = ffu / "crates" / "ffu-headless"
    (h / "src").mkdir(parents=True)
    (h / "Cargo.toml").write_text('[package]\nname = "ffu-headless"\n\n[features]\nagent-api = []\n')
    (h / "src" / "cli.rs").write_text(
        'match c { "run" => 1, "replay" => 2, "serve" => 3 }\n'
        'a.flag("--start"); a.flag("--ticks"); a.flag("--record");\n')
    a = ffu / "crates" / "ffu-agent"
    (a / "src").mkdir(parents=True)
    (a / "Cargo.toml").write_text('[package]\nname = "ffu-agent"\n')
    (a / "src" / "lib.rs").write_text('match m { "stats" => 1, "query" => 2, "set" => 3, "remove" => 4 }\n')
    (ffu / "tools").mkdir()
    (ffu / "tools" / "check_sim_rules.sh").write_text("")
    return ffu


class CheckFfuSkills(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ffu = fake_ffu(self.root)
        self.skill = self.root / "agents" / "plugins" / "ff-agents" / "skills" / "ffu-x" / "SKILL.md"
        self.skill.parent.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def problems(self, text, with_ffu=True):
        self.skill.write_text(text, encoding="utf-8")
        return c.check(self.root / "agents", self.ffu if with_ffu else None)

    def test_a_good_skill_passes(self):
        self.assertEqual(self.problems(GOOD), [])

    def test_a_unity_tool_fails_offline(self):
        p = self.problems(GOOD + "\nPin with `mcp__UnityMCP__set_active_instance` first.\n", with_ffu=False)
        self.assertTrue(any("Unity MCP" in x for x in p), p)

    def test_a_game_repo_script_fails(self):
        p = self.problems(GOOD + "\nRun `python scripts/nightly/player_slots.py launch`.\n", with_ffu=False)
        self.assertTrue(any("FF1 game-repo tool" in x for x in p), p)

    def test_a_non_ffu_skill_fails(self):
        p = self.problems(GOOD + "\nThen `/ff-agents:editor-ops`.\n", with_ffu=False)
        self.assertTrue(any("non-FFU skill" in x for x in p), p)

    def test_an_unknown_flag_fails(self):
        p = self.problems(GOOD + "\n`ffu-headless run --start factory:1 --bogus 3`\n")
        self.assertTrue(any("no flag --bogus" in x for x in p), p)

    def test_an_unknown_subcommand_fails(self):
        p = self.problems(GOOD + "\n`ffu-headless frobnicate --start x`\n")
        self.assertTrue(any("no subcommand frobnicate" in x for x in p), p)

    def test_an_unknown_feature_fails(self):
        p = self.problems(GOOD + "\n`cargo build -p ffu-headless --features hot-reload`\n")
        self.assertTrue(any("no feature hot-reload" in x for x in p), p)

    def test_an_unknown_method_and_tool_fail(self):
        p = self.problems(GOOD + '\n`{"method":"teleport"}` and `ffu_teleport`\n')
        self.assertTrue(any("no method teleport" in x for x in p), p)
        self.assertTrue(any("no tool ffu_teleport" in x for x in p), p)

    def test_a_missing_tools_script_fails(self):
        p = self.problems(GOOD + "\n`./tools/nope.sh`\n")
        self.assertTrue(any("no tools/nope.sh" in x for x in p), p)

    def test_a_repo_slug_is_not_a_binary(self):
        self.assertEqual(self.problems(GOOD + "\n`gh pr merge 1 -R Final-Factory/ffu --merge`\n"), [])

    def map_problems(self, rows, ff1_description="Drive FF1. Not for an ffu checkout, where ffu-x replaces it."):
        skills = self.skill.parents[1]
        for name, desc in (("drive-game", ff1_description), ("handoff", "Hand off.")):
            (skills / name).mkdir(exist_ok=True)
            (skills / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n\nbody ffu-x\n")
        (skills / "ffu-build-test").mkdir(exist_ok=True)
        (skills / "ffu-build-test" / "skill-map.md").write_text(
            "| Skill | In an ffu checkout | Why |\n|---|---|---|\n" + "".join(f"| {a} | {b} | c |\n" for a, b in rows))
        self.skill.write_text(GOOD, encoding="utf-8")
        return [p for p in c.check(self.root / "agents", None) if p.startswith("skill-map")]

    def test_a_complete_map_passes(self):
        self.assertEqual(self.map_problems([("drive-game", "ffu-x"), ("handoff", "shared")]), [])

    def test_a_skill_missing_from_the_map_fails(self):
        p = self.map_problems([("drive-game", "ffu-x")])
        self.assertTrue(any("no row for handoff" in x for x in p), p)

    def test_a_replacement_that_does_not_exist_fails(self):
        p = self.map_problems([("drive-game", "ffu-nope"), ("handoff", "shared")])
        self.assertTrue(any("ffu-nope: not an ffu-* skill" in x for x in p), p)

    def test_a_replaced_skill_must_name_its_replacement(self):
        p = self.map_problems([("drive-game", "ffu-x"), ("handoff", "shared")], ff1_description="Drive FF1.")
        self.assertTrue(any("does not name its FFU replacement ffu-x" in x for x in p), p)


if __name__ == "__main__":
    unittest.main()
