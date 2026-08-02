---
name: publish-skills
description: Add, edit, or fix a Claude skill / subagent role, or record a durable project lesson into project memory — and publish it so every machine, clone, worktree, and branch gets it. Use whenever the user asks to change how a skill behaves, add a new skill or role, "remember this", "capture this lesson", or fix something a skill got wrong. Also use PROACTIVELY at the end of a session that produced a hard-won, reusable lesson. Skills do NOT live in the game repo — they live in the final-factory-agents marketplace repo, and edits there require a version bump to reach live sessions.
---

# Publishing skills, roles, and project memory

Skills and subagent roles are NOT in the game repo. They live in the
**final-factory-agents** marketplace repo (`https://github.com/Final-Factory/final-factory-agents`)
and are installed as Claude Code plugins at user scope. Editing anything under a game-repo
`.claude/` directory does nothing — those copies were removed on purpose.

Live sessions read from Claude Code's own clone plus a per-version cache, **not** from any
working checkout. So an edit only reaches anybody after a version bump + push + update.

## 1. Locate the working checkout — STOP if it cannot be verified

The checkout can be anywhere — its location differs per machine, so never assume a path.
`registerClaude.sh` records where it lives when it runs. Read that marker:

```sh
cat ~/.claude/final-factory-agents-checkout
```

It must hold one absolute path (native form, e.g. `D:/work/final-factory-agents` or
`/home/ben/src/final-factory-agents`), usable by both shell and file tools. Check ALL of:

1. The marker file exists and is non-empty.
2. It contains exactly one path — not multiple lines, not a comment, not stray text.
3. That path exists and is a directory.
4. That directory contains `.claude-plugin/marketplace.json`.
5. That directory is a git repo (`git -C <path> rev-parse --show-toplevel` succeeds).

### If ANY check fails: STOP and do nothing else

Report to the user, in plain language: which check failed, the exact value found in the
marker (or that it was missing), and how to fix it —

> Run `sh registerClaude.sh` from your final-factory-agents checkout to re-record the path.
> If there is no checkout on this machine, clone one first:
> `git clone https://github.com/Final-Factory/final-factory-agents`

Then **end your turn**. Do not work around it. Specifically, do NOT:

- clone the repo yourself to "fix" it, or write the marker file yourself
- guess or search for a checkout in other directories
- edit `~/.claude/plugins/marketplaces/final-factory-agents/` (Claude Code's managed clone —
  marketplace updates reset it, so edits there are silently lost)
- edit any `.claude/skills/` or `.claude/agents/` directory in the game repo (those copies
  were deliberately removed; edits there reach nobody)
- make the requested change anywhere else, or hold it "for later"

A broken marker means the machine's setup is wrong, and the user is the one who should decide
where their checkout lives. Fixing it silently hides a setup problem that will recur; leaving
the edit unpublished but unreported is worse than not starting.

### If every check passes

`git -C <checkout> pull` before editing so you are not branching off stale content, then
continue to step 2.

## 2. Make the change

| Change | Where |
|---|---|
| Edit/add a skill | `plugins/<plugin>/skills/<name>/SKILL.md` (+ supporting files beside it) |
| Edit/add a subagent role | `plugins/<plugin>/agents/<name>.md` |
| Record a durable lesson | `plugins/ff-agents/skills/project-memory/memories/<slug>.md` **plus** one index line in that skill's `SKILL.md` |

Plugins: `ff-agents` (core roles + workflow skills), `ff-speckit` (speckit-*),
`ff-discord` (Discord roles + skills). Skill frontmatter needs `name:` and `description:`;
role frontmatter needs `name:`, `description:`, `model:`, `tools:`.

Skills are shared by Claude Code AND Codex (same `skills/<name>/SKILL.md` layout), so keep ONE
copy per skill — never fork a body per tool. Subagent roles under `agents/` are Claude-only;
Codex loads its roles from the game repo's `.codex/agents/*.toml` instead.

**Never** write durable lessons to `~/.claude/projects/*/memory/` — those are machine-local,
keyed on checkout path, and never propagate. That fragmentation is why this repo exists.

## 3. Bump the version — MANDATORY, in ALL THREE files

They must stay equal, or the publish silently no-ops:

- `plugins/<plugin>/.claude-plugin/plugin.json` → `version`
- `plugins/<plugin>/.codex-plugin/plugin.json` → `version`
- `.claude-plugin/marketplace.json` → that plugin's entry → `version`

(`.agents/plugins/marketplace.json` — the Codex marketplace — carries no versions.)

Patch bump for a fix or a new memory; minor for a new skill or role.

> Skipping this is the classic failure: `registerClaude.sh` reports "already at the latest
> version" and keeps serving the OLD content, with no error anywhere.

## 4. Validate, commit, push

```sh
claude plugin validate .        # checks the manifests
git add -A && git commit -m "<what changed>" && git push
```

Both manifests are UTF-8 with literal em-dashes — edit them with Edit/Write, never with
scripted JSON re-serialization, which mangles the encoding.

## 5. Install it here, and tell the user

```sh
sh registerClaude.sh            # in the marketplace checkout: pulls + installs the new version
```

Then tell the user plainly: **open Claude Code sessions must be restarted** to pick up the
change — plugins are discovered only at session start, so the edit is not live in the current
conversation. Other machines get it when someone runs `registerClaude.sh` there.

## Reporting

Say which plugin changed, the old → new version, and that a restart is needed. If you only
edited the working checkout without bumping/pushing, say so explicitly — a half-published
change looks identical to a working one until someone notices stale behavior.
