"""Tests for ci_local.py and ci_local.sh (w4917): the plan read from a workflow shaped like ffu's ci.yml, the drift
checks that stop it, and one end-to-end run with a passing and a failing step."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import ci_local  # noqa: E402

WORKFLOW = """\
# a comment
name: ci
on:
  pull_request:
    paths-ignore: ['docs/**']
env:
  CARGO_TERM_COLOR: always
  CARGO_INCREMENTAL: 0
  CARGO_PROFILE_DEV_DEBUG: line-tables-only
jobs:
  lint:
    runs-on: [self-hosted, ffu-linux-biscuit]
    timeout-minutes: 70  # 25 + 45
    steps:
      - name: cargo on PATH
        if: runner.os != 'Windows'
        run: echo "$HOME/.cargo/bin" >> "$GITHUB_PATH"
      - uses: actions/checkout@v4
        with:
          clean: false
      - name: toolchain
        run: rustup toolchain install 1.94.0 --profile minimal && rustup show active-toolchain
      - run: echo fmt ok
      # a comment between steps
      - name: numbers (w3640)
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: |
          echo "event=${{ github.event_name }} pr=${{ github.event.pull_request.number }}"
          if [ "${{ github.event_name }}" = pull_request ]; then
            git fetch -q --no-tags --depth=1 origin "+refs/heads/${{ github.base_ref }}:refs/remotes/origin/${{ github.base_ref }}"
          fi
      - name: fuzz
        run: |
          cargo check --manifest-path fuzz/Cargo.toml --locked --target-dir target
      - name: fails on purpose
        shell: bash
        run: |
          echo "# not a comment, a line of the script"
          echo boom >&2
          exit 3
      - name: keep target
        if: always()
        shell: bash
        run: tools/ci-runners/keep_target.sh end
      - run: tools/ci-runners/runner_health_test.sh
      - run: tools/ci-runners/sweep_target_test.sh
      - name: runner health
        if: always() && runner.os == 'Linux'
        run: tools/ci-runners/runner_health.sh "$(dirname "$RUNNER_WORKSPACE")"
  check:
    runs-on: ffu-linux
    steps:
      - run: echo check ok
        env:
          FFU_REQUIRE_GPU: "1"
          FFU_CAPTURE_DIR: ${{ github.workspace }}/caps
"""


def plan(root: Path, workflow: str, *extra: str):
    wf = root / "repo" / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "ci.yml").write_text(workflow, encoding="utf-8")
    out = root / "out"
    code = ci_local.main(["plan", "--repo", str(root / "repo"), "--out", str(out), *extra])
    rows = []
    if (out / "plan.tsv").exists():
        rows = [l.split("\t") for l in (out / "plan.tsv").read_text(encoding="utf-8").splitlines()]
    return code, rows, out


class Yaml(unittest.TestCase):
    def test_block_scalar_keeps_hash_lines_and_comments_drop(self):
        doc = ci_local.load_yaml(WORKFLOW)
        steps = doc["jobs"]["lint"]["steps"]
        self.assertEqual(doc["jobs"]["lint"]["timeout-minutes"], "70")
        self.assertIn('echo "# not a comment', steps[6]["run"])
        self.assertEqual(steps[1]["with"], {"clean": "false"})
        self.assertEqual(doc["jobs"]["check"]["steps"][0]["env"]["FFU_REQUIRE_GPU"], "1")
        self.assertEqual(len(steps), 11)

    def test_unreadable_line_raises(self):
        with self.assertRaises(ci_local.PlanError):
            ci_local.load_yaml("jobs:\n  lint:\n    steps:\n      - run: x\n       oops: y\n")


class Plan(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_runs_the_checks_and_skips_only_runner_upkeep(self):
        code, rows, _ = plan(self.tmp, WORKFLOW)
        self.assertEqual(code, 0)
        verdicts = {r[3]: r[0] for r in rows}
        for name in ("cargo on PATH", "actions/checkout@v4", "toolchain", "keep target", "runner health"):
            self.assertEqual(verdicts[name], "SKIP", name)
        for name in ("echo fmt ok", "numbers (w3640)", "fuzz", "fails on purpose",
                     "tools/ci-runners/runner_health_test.sh", "echo check ok"):
            self.assertEqual(verdicts[name], "RUN", name)
        linux = sys.platform not in ("win32", "darwin")
        self.assertEqual(verdicts["tools/ci-runners/sweep_target_test.sh"], "RUN" if linux else "SKIP")
        self.assertTrue(rows[0][1].startswith("lint-01-"))

    def test_push_and_pr_context(self):
        _, rows, _ = plan(self.tmp, WORKFLOW)
        s = Path(next(r[2] for r in rows if r[3] == "numbers (w3640)")).read_text(encoding="utf-8")
        self.assertIn("event=push pr=", s)
        body = self.tmp / "body.txt"
        body.write_text("Plan-edit: x\n", encoding="utf-8")
        _, rows, out = plan(self.tmp, WORKFLOW, "--pr", "17", "--body-file", str(body))
        s = Path(next(r[2] for r in rows if r[3] == "numbers (w3640)")).read_text(encoding="utf-8")
        self.assertIn("event=pull_request pr=17", s)
        self.assertIn("refs/heads/main:refs/remotes/origin/main", s)
        self.assertIn("Plan-edit: x", (out / "runner-temp" / "event.json").read_text(encoding="utf-8"))

    def test_rewrites_and_token(self):
        _, rows, _ = plan(self.tmp, WORKFLOW, "--pr", "17", "--body-file", os.devnull)
        numbers = Path(next(r[2] for r in rows if r[3] == "numbers (w3640)")).read_text(encoding="utf-8")
        self.assertNotIn("--depth", numbers)
        self.assertIn(f"export GITHUB_TOKEN={ci_local.TOKEN_SHELL}", numbers)
        self.assertNotIn(ci_local.TOKEN, numbers.replace(ci_local.TOKEN_SHELL, ""))
        fuzz = Path(next(r[2] for r in rows if r[3] == "fuzz")).read_text(encoding="utf-8")
        self.assertIn('--target-dir "${CARGO_TARGET_DIR:-target}"', fuzz)

    def test_cargo_build_env_only_on_request(self):
        _, rows, _ = plan(self.tmp, WORKFLOW)
        s = Path(rows[3][2]).read_text(encoding="utf-8")
        self.assertIn("CARGO_TERM_COLOR", s)
        self.assertNotIn("CARGO_INCREMENTAL", s)
        _, rows, _ = plan(self.tmp, WORKFLOW, "--ci-cargo-env")
        self.assertIn("export CARGO_INCREMENTAL='0'", Path(rows[3][2]).read_text(encoding="utf-8"))

    def test_drift_stops_the_plan(self):
        cases = {
            "an unknown if": WORKFLOW.replace("if: always()\n", "if: github.ref == 'refs/heads/main'\n"),
            "an unknown expression": WORKFLOW.replace("echo fmt ok", "echo ${{ matrix.os }}"),
            "an unknown key": WORKFLOW.replace("      - run: echo fmt ok", "      - run: echo fmt ok\n        foo: 1"),
            "another shell": WORKFLOW.replace("shell: bash\n        run: |\n          echo \"# not",
                                              "shell: pwsh\n        run: |\n          echo \"# not"),
            "a missing job": WORKFLOW.replace("  check:", "  checks:"),
        }
        for what, wf in cases.items():
            code, _, _ = plan(self.tmp, wf)
            self.assertEqual(code, 2, what)


def git_bash():
    b = shutil.which("bash")
    if not b or (sys.platform == "win32" and "system32" in b.lower()):
        return None
    return b


class LocalEnv(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_step_writes_python_output_as_utf8_unless_the_workflow_says(self):
        wf = WORKFLOW.replace("  CARGO_TERM_COLOR: always\n", "  CARGO_TERM_COLOR: always\n  PYTHONIOENCODING: latin-1\n")
        _, rows, _ = plan(self.tmp, wf)
        s = Path(next(r[2] for r in rows if r[3] == "echo fmt ok")).read_text(encoding="utf-8")
        self.assertIn("export PYTHONUTF8='1'", s)
        self.assertIn("export PYTHONIOENCODING='latin-1'", s)  # the workflow's own value wins
        self.assertNotIn("export PYTHONIOENCODING='utf-8'", s)

    def test_step_minutes_column(self):
        wf = WORKFLOW.replace("      - run: echo fmt ok\n", "      - run: echo fmt ok\n        timeout-minutes: 7\n")
        code, rows, _ = plan(self.tmp, wf)
        self.assertEqual(code, 0)
        self.assertTrue(all(len(r) == 5 for r in rows), rows)
        by = {r[3]: r[4] for r in rows}
        self.assertEqual((by["echo fmt ok"], by["fuzz"], by["toolchain"]), ("7", "-", "-"))
        code, _, _ = plan(self.tmp, wf.replace("timeout-minutes: 7", "timeout-minutes: ${{ inputs.t }}"))
        self.assertEqual(code, 2)


@unittest.skipUnless(git_bash() and shutil.which("git"), "needs bash and git")
class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        (self.repo / ".github" / "workflows").mkdir(parents=True)
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "check_sim_rules.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        fake = self.tmp / "bin"  # the script stops without a cargo; these steps never call it
        fake.mkdir()
        (fake / "cargo").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (fake / "cargo").chmod(0o755)
        self.env = dict(os.environ, TMPDIR=str(self.tmp).replace("\\", "/"), CARGO_HOME=str(self.tmp))
        for k in ("PYTHONUTF8", "PYTHONIOENCODING"):  # the run must set them itself
            self.env.pop(k, None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_local(self, wf, *args, **env):
        (self.repo / ".github" / "workflows" / "ci.yml").write_text(wf, encoding="utf-8")
        return subprocess.run([git_bash(), str(HERE / "ci_local.sh"), *args], cwd=self.repo,
                              env=dict(self.env, **env), capture_output=True, text=True, encoding="utf-8")

    def test_a_pr_body_with_an_emoji_passes_the_row_doc_read(self):
        # ffu ci.yml's row-doc step prints the PR body to a file with Python; on Windows that wrote cp1252 and the
        # robot emoji of the "Generated with Claude Code" line raised UnicodeEncodeError (w4987)
        wf = """\
jobs:
  lint:
    steps:
      - name: the body is read
        run: |
          if [ "${{ github.event_name }}" = pull_request ]; then
            python3 -c 'import json, os; print(json.load(open(os.environ["GITHUB_EVENT_PATH"]))["pull_request"].get("body") or "")' > "$RUNNER_TEMP/pr_body.txt"
            python3 -c 'import sys; t = open(sys.argv[1], encoding="utf-8").read(); sys.exit(0 if chr(0x1F916) in t else 5)' "$RUNNER_TEMP/pr_body.txt"
            python3 -c 'print(chr(0x1F916), "to stdout")'
          fi
"""
        body = self.tmp / "body.md"
        body.write_text("Row W1j.\n\n\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)\n",
                        encoding="utf-8")
        r = self.run_local(wf, "--jobs", "lint", str(body))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"PASS  lint-01-the-body-is-read")

    def test_a_step_past_its_minutes_is_ended(self):
        wf = """\
jobs:
  lint:
    steps:
      - name: hangs
        run: echo started; sleep 120
      - run: echo after the hang
"""
        r = self.run_local(wf, "--jobs", "lint", CI_LOCAL_STEP_MINUTES="0.05")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"TIMEOUT lint-01-hangs .*ended after 0.05 min")
        self.assertIn("| started", r.stdout)
        self.assertRegex(r.stdout, r"PASS  lint-02-echo-after-the-hang")

    def test_pass_fail_lines_logs_and_tail(self):
        wf = """\
jobs:
  lint:
    steps:
      - uses: actions/checkout@v4
      - run: echo fine
      - name: red one
        run: |
          echo line-one
          echo line-two >&2
          exit 4
      - run: echo after the red one
  check:
    steps:
      - run: test "$FFU_REQUIRE_GPU" = 1
        env:
          FFU_REQUIRE_GPU: "1"
"""
        r = self.run_local(wf)
        out = r.stdout
        self.assertEqual(r.returncode, 1, out + r.stderr)
        self.assertRegex(out, r"SKIP  lint-01-actions-checkout-v4")
        self.assertRegex(out, r"PASS  lint-02-echo-fine")
        self.assertRegex(out, r"FAIL  lint-03-red-one .*exit 4")
        self.assertIn("| line-two", out)
        self.assertRegex(out, r"PASS  lint-04-echo-after-the-red-one")
        self.assertRegex(out, r"PASS  check-01-test-ffu-require-gpu-1")
        self.assertTrue((self.tmp / "step-lint-03-red-one.log").exists())


if __name__ == "__main__":
    unittest.main()
