#!/usr/bin/env python3
"""Check that every ffu-* skill names FFU commands only (ffu PLAN.md row M0.8, w2895).

Two checks over the code of each `plugins/*/skills/ffu-*/SKILL.md` (fenced blocks and backticked spans; prose may say
"no Unity editor"):

1. Offline, always: no Unity or FF1 tool is named (the Unity MCP bridge, unity-bridge.py, player slots, ffauto, a game
   repo script, a C# file), and a skill named as `/ff-agents:<name>` is an ffu-* skill or one of a few shared ones.
2. The skill map (`skill-map.md` beside this file, when present): every ff-agents skill has a row, a replacement it
   names is an ffu-* skill that exists, and each replaced FF1 skill names its replacement in its own description.
3. With `--ffu <checkout>`: every ffu binary's subcommand and `--flag`, every `cargo -p <crate>` and `--features`,
   every `tools/<script>`, every agent API method (`"method":"x"`, `ffu_x`) and `set` op the skill names exists in
   that checkout's source.

    python3 check_ffu_skills.py [--root <final-factory-agents>] [--ffu <ffu checkout>]

Exit 0 when every skill passes, 1 with one line per problem. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DENY = [
    (r"mcp__UnityMCP|UnityMCP|mcpforunity", "the Unity MCP bridge"),
    (r"\b(set_active_instance|refresh_unity|run_tests|get_test_job|read_console|execute_code|manage_editor)\b",
     "a Unity MCP tool"),
    (r"unity-bridge|unity-slot|Unity\.exe|-batchmode|ParrelSync", "a Unity launcher"),
    (r"player_slots|ffauto|game_data\.py|test_select\.py|save_census|peer\.py", "an FF1 game-repo tool"),
    (r"\bscripts/[\w/.-]+\.py\b", "a game-repo script"),
    (r"\bAssets/|\.cs\b|\.unity\b|\.prefab\b", "a Unity project path"),
]
SHARED_SKILLS = {"watch-video", "evidence-gate", "publish-skills", "plain-writing"}
BINARIES = {
    "ffu": "ffu-client",
    "ffu-headless": "ffu-headless",
    "ffu-mcp": "ffu-mcp",
    "ffu-server": "ffu-server",
    "ffu-bench": "ffu-bench",
    "ffu-bake": "ffu-bake",
    "ffu-content": "ffu-content",
    "ffu-bots": "ffu-bots",
    "ffu-minidump": "ffu-crash",
}
SUBCOMMANDS = {"ffu-headless", "ffu-server", "ffu-bots", "ffu-bake", "ffu-content", "ffu-bench"}
MCP_EXTRA_TOOLS = {"engine"}


def code_of(text: str) -> list[str]:
    """Fenced blocks (each line) and inline backtick spans outside them."""
    out: list[str] = []
    rest: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        (out if fenced else rest).append(line)
    for line in rest:
        out.extend(re.findall(r"`([^`]+)`", line))
    return out


def deny_problems(code: list[str]) -> list[str]:
    bad = []
    for c in code:
        for pat, what in DENY:
            if re.search(pat, c):
                bad.append(f"names {what}: {c.strip()[:100]}")
        for name in re.findall(r"/ff-agents:([\w-]+)", c):
            if not name.startswith("ffu-") and name not in SHARED_SKILLS:
                bad.append(f"points at a non-FFU skill /ff-agents:{name}")
    return bad


class Ffu:
    """What an ffu checkout's source says exists."""

    def __init__(self, root: Path):
        self.root = root
        crates = root / "crates"
        self.crates = {p.name for p in crates.iterdir() if (p / "Cargo.toml").exists()}
        self.words: dict[str, set[str]] = {}
        for c in self.crates:
            text = "".join(p.read_text(encoding="utf-8", errors="replace") for p in (crates / c / "src").rglob("*.rs"))
            self.words[c] = set(re.findall(r'"(--[a-z0-9-]+)"', text)) | set(
                re.findall(r'"([a-z][a-z0-9_-]*)"\s*(?:\||=>)', text)) | set(
                re.findall(r'Some\("([a-z][a-z0-9_-]*)"\)', text))
            usage = re.findall(r"(?m)^\s*(?:\\x20\s*)?" + re.escape(c) + r" ([a-z]+)\b", text)
            self.words[c] |= set(usage)
        self.features = {}
        for c in self.crates:
            toml = (crates / c / "Cargo.toml").read_text(encoding="utf-8")
            m = re.search(r"(?ms)^\[features\]\n(.*?)(?:^\[|\Z)", toml)
            self.features[c] = set(re.findall(r"(?m)^([a-z0-9_-]+)\s*=", m.group(1))) if m else set()
        agent = crates / "ffu-agent" / "src"
        atext = "".join(p.read_text(encoding="utf-8", errors="replace") for p in agent.rglob("*.rs")) if agent.exists() else ""
        self.methods = set(re.findall(r'"([a-z_]+)"\s*=>', atext))

    def flags_of(self, binary: str) -> set[str]:
        words = set(self.words.get(BINARIES[binary], set()))
        if binary == "ffu":  # `ffu --headless <cmd>` forwards to ffu-headless
            words |= self.words.get("ffu-headless", set())
        words |= {"--help", "-h"}
        return words


def tokens(line: str) -> list[str]:
    return re.findall(r"[^\s\"'|;&()]+", line)


def ffu_problems(code: list[str], ffu: Ffu) -> list[str]:
    bad = []
    for c in code:
        toks = tokens(c)
        for i, t in enumerate(toks):
            base = t.rsplit("/", 1)[-1].removesuffix(".exe")
            if base in BINARIES and (i == 0 or t.startswith(("$", "./", "/", "~")) or toks[i - 1] in {"do", "then", "time", "timeout"}):
                known = ffu.flags_of(base)
                for a in toks[i + 1:]:
                    if a.startswith("#"):
                        break
                    if a.startswith("--") and re.fullmatch(r"--[a-z0-9-]+", a) and a not in known:
                        bad.append(f"{base}: no flag {a} in crates/{BINARIES[base]}: {c.strip()[:100]}")
                nxt = next((a for a in toks[i + 1:] if not a.startswith("-")), None)
                if (base in SUBCOMMANDS and nxt and re.fullmatch(r"[a-z]+", nxt)
                        and nxt not in known):
                    bad.append(f"{base}: no subcommand {nxt}: {c.strip()[:100]}")
            if t == "-p" and i + 1 < len(toks) and toks[i + 1].startswith("ffu"):
                crate = toks[i + 1]
                if crate not in ffu.crates:
                    bad.append(f"cargo: no crate {crate}")
                for j in range(i + 2, len(toks) - 1):
                    if toks[j] == "--features":
                        for f in toks[j + 1].split(","):
                            if f not in ffu.features.get(crate, set()):
                                bad.append(f"cargo: crate {crate} has no feature {f}")
        for script in re.findall(r"\btools/([\w.-]+\.sh)\b", c):
            if not (ffu.root / "tools" / script).exists():
                bad.append(f"no tools/{script} in ffu")
        for m in re.findall(r'"method"\s*:\s*"([a-z_]+)"', c):
            if m not in ffu.methods:
                bad.append(f"agent API has no method {m}")
        for m in re.findall(r'"op"\s*:\s*"([a-z_]+)"', c):
            if m not in ffu.methods:
                bad.append(f"agent API set has no op {m}")
        for m in re.findall(r"\bffu_([a-z_]+)\b", c):
            if m not in ffu.methods and m not in MCP_EXTRA_TOOLS and not c.lstrip().startswith(("ffu_par", "ffu_sim")):
                if m in {"par", "sim", "headless", "agent", "crash"}:
                    continue  # crate paths such as ffu_headless::stream
                bad.append(f"ffu-mcp has no tool ffu_{m}")
    return bad


def map_problems(root: Path) -> list[str]:
    """The skill map: one row per ff-agents skill, each replacement real and named by the skill it replaces."""
    path = root / "plugins" / "ff-agents" / "skills" / "ffu-build-test" / "skill-map.md"
    if not path.exists():
        return []
    skills_dir = path.parents[1]
    have = {p.parent.name for p in skills_dir.glob("*/SKILL.md")}
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.fullmatch(r"[A-Za-z][\w-]*", cells[0]) and cells[0] != "Skill":
            rows[cells[0]] = cells[1]
    bad = []
    for name in sorted(have - set(rows)):
        if not name.startswith("ffu-"):
            bad.append(f"skill-map: no row for {name}")
    for name, use in sorted(rows.items()):
        if name not in have:
            bad.append(f"skill-map: row for a skill that does not exist: {name}")
            continue
        if use in {"shared", "FF1 only"}:
            continue
        if not use.startswith("ffu-") or use not in have:
            bad.append(f"skill-map: {name} -> {use}: not an ffu-* skill here")
            continue
        head = (skills_dir / name / "SKILL.md").read_text(encoding="utf-8").split("\n---", 1)[0]
        if use not in head:
            bad.append(f"skill-map: {name}'s description does not name its FFU replacement {use}")
    return bad


def check(root: Path, ffu_root: Path | None) -> list[str]:
    skills = sorted(root.glob("plugins/*/skills/ffu-*/SKILL.md"))
    if not skills:
        return [f"no ffu-* skills under {root}/plugins"]
    ffu = Ffu(ffu_root) if ffu_root else None
    out = []
    for s in skills:
        code = code_of(s.read_text(encoding="utf-8"))
        probs = deny_problems(code) + (ffu_problems(code, ffu) if ffu else [])
        out += [f"{s.parent.name}: {p}" for p in probs]
    return out + map_problems(root)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    ap.add_argument("--ffu", type=Path, help="an ffu checkout, to check commands against its source")
    a = ap.parse_args(argv)
    probs = check(a.root, a.ffu)
    n = len(list(a.root.glob("plugins/*/skills/ffu-*/SKILL.md")))
    for p in probs:
        print(p)
    print(f"{n} ffu skills, {len(probs)} problems" + (" (checked against the ffu source)" if a.ffu else " (offline)"))
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
