#!/usr/bin/env python3
"""Plan ffu CI's lint and check jobs as local steps, read from .github/workflows/ci.yml itself (w4917).

ci_local.sh runs this; you rarely call it yourself. It reads the workflow at the checkout's HEAD, so a step added to
ci.yml runs locally with no change here. A step is left out only by a rule in SKIP below, each with its reason, and a
step this script cannot read (an `if:` it cannot evaluate, a `${{ }}` it does not know, a key it does not expect) stops
the plan with exit 2 instead of being dropped: that is the drift check.

    ci_local.py plan --repo <ffu checkout> --out <run folder> [--jobs lint,check] [--pr N] [--body-file F]
                     [--base main] [--all] [--ci-cargo-env]

Writes <out>/plan.tsv, one line per step: RUN<TAB>slug<TAB>script<TAB>name<TAB>minutes (the step's `timeout-minutes`,
or `-`: ci_local.sh then uses its default), or SKIP<TAB>slug<TAB>reason<TAB>name<TAB>-, and one bash script per RUN
step (its env exported, then its `run:` body). Stdlib only, Python 3.8+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class PlanError(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------------------
# A small YAML reader: block maps, block lists, `|`/`>` block scalars, plain and quoted scalars, flow values kept as raw
# text. That is all ci.yml uses; anything else raises, so a new construct is seen, never misread.


def _strip_comment(s: str) -> str:
    q = None
    for i, c in enumerate(s):
        if q:
            if c == q:
                q = None
        elif c in "'\"":
            q = c
        elif c == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s.rstrip()


def _scalar(s: str):
    s = _strip_comment(s).strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return json.loads(s)
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1].replace("''", "'")
    return s


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _blank(line: str) -> bool:
    t = line.strip()
    return not t or t.startswith("#")


KEY = re.compile(r"^([A-Za-z0-9_.-]+|'[^']*'|\"[^\"]*\"):(?:\s+(.*))?$")


class _Reader:
    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.i = 0

    def _next(self):
        while self.i < len(self.lines) and _blank(self.lines[self.i]):
            self.i += 1
        return self.i if self.i < len(self.lines) else None

    def block(self, indent: int):
        j = self._next()
        if j is None or _indent(self.lines[j]) < indent:
            return None
        ind = _indent(self.lines[j])
        if self.lines[j][ind:].startswith("- ") or self.lines[j][ind:] == "-":
            return self._list(ind)
        return self._map(ind)

    def _list(self, ind: int):
        out = []
        while True:
            j = self._next()
            if j is None or _indent(self.lines[j]) != ind:
                break
            line = self.lines[j]
            if not (line[ind:].startswith("- ") or line[ind:] == "-"):
                break
            rest = line[ind + 2:]
            if not rest.strip():
                self.i = j + 1
                out.append(self.block(ind + 1))
            elif KEY.match(rest.strip()):
                self.lines[j] = " " * (ind + 2) + rest  # the item's first key, at the item's own indent
                out.append(self._map(ind + 2))
            else:
                self.i = j + 1
                out.append(_scalar(rest))
        return out

    def _map(self, ind: int):
        out = {}
        while True:
            j = self._next()
            if j is None or _indent(self.lines[j]) < ind:
                break
            line = self.lines[j]
            if _indent(line) > ind:
                raise PlanError(f"ci.yml line {j + 1}: unexpected indentation: {line.strip()[:80]}")
            if line[ind:].startswith("- "):
                break
            m = KEY.match(line[ind:])
            if not m:
                raise PlanError(f"ci.yml line {j + 1}: not a `key: value` line: {line.strip()[:80]}")
            key, rest = _scalar(m.group(1)), (m.group(2) or "")
            self.i = j + 1
            r = _strip_comment(rest).strip() if not rest.lstrip().startswith(("|", ">")) else rest.strip()
            if r.startswith(("|", ">")):
                out[key] = self._block_scalar(ind, r)
            elif r == "":
                k = self._next()
                if k is not None and _indent(self.lines[k]) == ind and self.lines[k][ind:].startswith("- "):
                    out[key] = self._list(ind)
                else:
                    out[key] = self.block(ind + 1)
            else:
                out[key] = _scalar(rest)
        return out

    def _block_scalar(self, ind: int, header: str) -> str:
        body = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.strip() and _indent(line) <= ind:
                break
            body.append(line)
            self.i += 1
        while body and not body[-1].strip():
            body.pop()
        content = [l for l in body if l.strip()]
        cut = min((_indent(l) for l in content), default=0)
        lines = [l[cut:] for l in body]
        if header.startswith(">"):
            return " ".join(l.strip() for l in lines if l.strip()) + "\n"
        return "\n".join(lines) + "\n"


def load_yaml(text: str):
    r = _Reader(text)
    doc = r.block(0)
    if r._next() is not None:
        raise PlanError(f"ci.yml line {r.i + 1}: could not read past here")
    return doc


# ---------------------------------------------------------------------------------------------------------------------
# The plan.

STEP_KEYS = {"name", "run", "uses", "with", "if", "env", "shell", "continue-on-error", "id", "timeout-minutes",
             "working-directory"}

# (test on the step, reason). The first that matches leaves the step out. Each is runner upkeep, not a check.
SKIP = [
    (lambda s: "uses" in s, "an action (checkout, artifact upload): the runner's job, not a check"),
    (lambda s: re.search(r"GITHUB_PATH|GITHUB_ENV", s.get("run", "")), "runner setup (PATH, temp folder)"),
    (lambda s: "rustup toolchain install" in s.get("run", ""), "toolchain setup: rust-toolchain.toml pins it here"),
    (lambda s: "keep_target.sh" in s.get("run", ""), "the runner's target/ upkeep"),
    (lambda s: re.search(r"runner_health\.sh\b", s.get("run", "")), "runner health (reads RUNNER_WORKSPACE, never fails)"),
]

# Steps CI runs on Linux that cannot pass on another OS; --all runs them anyway.
LINUX_ONLY = [
    (lambda s: "sweep_target_test.sh" in s.get("run", ""),
     "fails on Windows (NTFS reads do not move access times) and skips on macOS; CI runs it on Linux (w4510)"),
]

# Text replaced before a step runs locally, and why. Each keeps what the step checks.
REWRITES = [
    (re.compile(r"\s--depth=1\b"), "",
     "a --depth fetch would make the shared clone behind an ffu slot shallow"),
    (re.compile(r"--target-dir target\b"), '--target-dir "${CARGO_TARGET_DIR:-target}"',
     "CI's target/ is the job's own target dir; locally that is CARGO_TARGET_DIR (the slot's)"),
]

# Workflow env that changes how cargo builds, not what passes: kept out by default so a local run reuses the warm
# target your other cargo runs built (each flip rebuilds the workspace). --ci-cargo-env keeps them.
CARGO_BUILD_ENV = {"CARGO_INCREMENTAL", "CARGO_PROFILE_DEV_DEBUG"}

# Env every step gets unless the workflow sets it. CI's Linux runners write Python's stdout as UTF-8; Windows Python
# writes it in the ANSI code page (cp1252), and the robot emoji of every PR body's "Generated with Claude Code" line
# stopped the row-doc step with UnicodeEncodeError there (w4987).
LOCAL_ENV = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def runner_os() -> str:
    return {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")


def eval_if(expr: str, ctx: dict) -> bool:
    expr = expr.strip()
    if expr.startswith("${{") and expr.endswith("}}"):
        expr = expr[3:-2].strip()
    ok = True
    for term in expr.split("&&"):
        t = term.strip()
        if t in ("always()", "success()"):
            continue
        m = re.fullmatch(r"(runner\.os|github\.event_name)\s*(==|!=)\s*'([^']*)'", t)
        if not m:
            raise PlanError(f"an `if:` this script cannot evaluate: {expr!r} (teach eval_if in ci_local.py)")
        val = ctx["runner.os"] if m.group(1) == "runner.os" else ctx["github.event_name"]
        ok = ok and ((val == m.group(3)) == (m.group(2) == "=="))
    return ok


def substitute(text: str, ctx: dict, where: str) -> str:
    def one(m):
        k = m.group(1).strip()
        if k not in ctx:
            raise PlanError(f"{where}: `${{{{ {k} }}}}` is not known to ci_local.py; add it to its context")
        return ctx[k]() if callable(ctx[k]) else ctx[k]
    return re.sub(r"\$\{\{\s*([^}]*?)\s*\}\}", one, text)


def sh_quote(v: str) -> str:
    return "'" + v.replace("'", "'\\''") + "'"


def slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", s.lower()).strip("-")
    return s[:48].rstrip("-") or "step"


# github.token: never written into a step's script; the script reads it from gh (or GITHUB_TOKEN) when it runs.
TOKEN = "__CI_LOCAL_GITHUB_TOKEN__"
TOKEN_SHELL = '"${GITHUB_TOKEN:-$(gh auth token 2>/dev/null)}"'


def plan(args) -> int:
    repo = Path(args.repo).resolve()
    wf = repo / ".github" / "workflows" / "ci.yml"
    doc = load_yaml(wf.read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    runner_temp = out / "runner-temp"
    runner_temp.mkdir(exist_ok=True)

    body = ""
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    elif args.pr:
        r = subprocess.run(["gh", "pr", "view", str(args.pr), "--json", "body", "--jq", ".body"], cwd=repo,
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            raise PlanError(f"gh pr view {args.pr} failed: {r.stderr.strip()[:200]}")
        body = r.stdout
    event_path = runner_temp / "event.json"
    event_path.write_text(json.dumps({"pull_request": {"number": int(args.pr) if args.pr else None, "body": body}}),
                          encoding="utf-8")
    is_pr = bool(args.pr or args.body_file)
    ctx = {
        "runner.os": runner_os(),
        "github.event_name": "pull_request" if is_pr else "push",
        "github.base_ref": args.base,
        "github.event.pull_request.number": str(args.pr or ""),
        "github.token": TOKEN,
        "github.workspace": repo.as_posix(),
        "github.sha": lambda: subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                                             text=True).stdout.strip(),
        "github.ref": "refs/pull/%s/merge" % args.pr if args.pr else "refs/heads/local",
    }

    wf_env = dict(doc.get("env") or {})
    if not args.ci_cargo_env:
        for k in CARGO_BUILD_ENV:
            wf_env.pop(k, None)
    jobs = doc.get("jobs") or {}
    rows = []
    for job in args.jobs.split(","):
        if job not in jobs:
            raise PlanError(f"ci.yml has no job {job!r} (jobs: {', '.join(jobs)})")
        j = jobs[job]
        job_env = dict(j.get("env") or {})
        for n, step in enumerate(j.get("steps") or [], 1):
            if not isinstance(step, dict):
                raise PlanError(f"job {job} step {n} is not a map")
            extra = set(step) - STEP_KEYS
            if extra:
                raise PlanError(f"job {job} step {n} has keys ci_local.py does not know: {sorted(extra)}")
            name = step.get("name") or (step.get("run") or step.get("uses") or "").strip().splitlines()[0]
            slug = f"{job}-{n:02d}-{slugify(name)}"
            runs_here = eval_if(str(step["if"]), ctx) if "if" in step else True  # every if is read: drift stops here
            reason = next((why for test, why in SKIP if test(step)), None)
            if reason is None and not runs_here:
                reason = f"its `if: {step['if']}` is false on {ctx['runner.os']}"
            if reason is None and runner_os() != "Linux" and not args.all:
                reason = next((why for test, why in LINUX_ONLY if test(step)), None)
            if reason:
                rows.append(("SKIP", slug, reason, name, "-"))
                continue
            if "run" not in step:
                raise PlanError(f"job {job} step {n} ({name}) has neither run nor uses")
            shell = step.get("shell")
            if shell not in (None, "bash"):
                raise PlanError(f"job {job} step {n} ({name}) runs in shell {shell!r}; ci_local.py runs bash only")
            run = substitute(step["run"], ctx, f"job {job} step {n}")
            for pat, rep, _why in REWRITES:
                run = pat.sub(rep, run)
            env = {}
            for scope, d in (("workflow", wf_env), ("job", job_env), ("step", step.get("env") or {})):
                for k, v in d.items():
                    env[k] = substitute(str(v), ctx, f"job {job} step {n} {scope} env {k}")
            env["RUNNER_TEMP"] = runner_temp.as_posix()
            env["GITHUB_EVENT_PATH"] = event_path.as_posix()
            env["GITHUB_WORKSPACE"] = repo.as_posix()
            env["CI_LOCAL"] = "1"
            for k, v in LOCAL_ENV.items():
                env.setdefault(k, v)
            flags = "-eo pipefail" if shell == "bash" else "-e"
            script = out / f"{slug}.sh"
            lines = ["#!/usr/bin/env bash", f"set {flags}", f"cd {sh_quote(repo.as_posix())}"]
            lines += [f"export {k}={TOKEN_SHELL if v == TOKEN else sh_quote(v)}" for k, v in env.items()]
            if TOKEN in run or any(TOKEN in v and v != TOKEN for v in env.values()):
                raise PlanError(f"job {job} step {n} uses github.token inside text; only `KEY: ${{{{ github.token }}}}` "
                                "env lines are supported")
            lines.append(run.rstrip("\n"))
            script.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            mins = str(step.get("timeout-minutes", "")).strip()
            if mins and not re.fullmatch(r"\d+(\.\d+)?", mins):
                raise PlanError(f"job {job} step {n} ({name}): timeout-minutes {mins!r} is not a number")
            rows.append(("RUN", slug, script.as_posix(), name, mins or "-"))
    with open(out / "plan.tsv", "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write("\t".join(x.replace("\t", " ").replace("\n", " ") for x in r) + "\n")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("plan")
    q.add_argument("--repo", required=True)
    q.add_argument("--out", required=True)
    q.add_argument("--jobs", default="lint,check")
    q.add_argument("--pr", default="")
    q.add_argument("--body-file", default="")
    q.add_argument("--base", default="main")
    q.add_argument("--all", action="store_true", help="run the Linux-only steps on this OS too")
    q.add_argument("--ci-cargo-env", action="store_true", help="keep CARGO_INCREMENTAL and CARGO_PROFILE_DEV_DEBUG")
    args = p.parse_args(argv)
    try:
        return plan(args)
    except PlanError as e:
        print(f"ci_local: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
