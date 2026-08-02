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

## 1. Find (or create) the working checkout

The checkout can be anywhere — its location differs per machine, so never assume a path.
`registerClaude.sh` records where it lives when it runs. Read that marker first:

```sh
cat ~/.claude/final-factory-agents-checkout
```

That file holds one absolute path (native form, e.g. `D:/work/final-factory-agents` or
`/home/ben/src/final-factory-agents`), usable by both shell and file tools. Verify it still
has `.claude-plugin/marketplace.json` before trusting it.

If the marker is missing or stale (the machine never ran the bootstrap, or the checkout moved),
clone a fresh one and record it so this never repeats:

```sh
git clone https://github.com/Final-Factory/final-factory-agents ~/final-factory-agents
sh ~/final-factory-agents/registerClaude.sh     # installs AND writes the marker
```

Do NOT edit `~/.claude/plugins/marketplaces/final-factory-agents/` — that is Claude Code's
managed clone, and marketplace updates reset it. Once you have the real checkout, `git pull`
before editing so you are not branching off stale content.

## 2. Make the change

| Change | Where |
|---|---|
| Edit/add a skill | `plugins/<plugin>/skills/<name>/SKILL.md` (+ supporting files beside it) |
| Edit/add a subagent role | `plugins/<plugin>/agents/<name>.md` |
| Record a durable lesson | `plugins/ff-agents/skills/project-memory/memories/<slug>.md` **plus** one index line in that skill's `SKILL.md` |

Plugins: `ff-agents` (core roles + workflow skills), `ff-speckit` (speckit-*),
`ff-discord` (Discord roles + skills). Skill frontmatter needs `name:` and `description:`;
role frontmatter needs `name:`, `description:`, `model:`, `tools:`.

**Never** write durable lessons to `~/.claude/projects/*/memory/` — those are machine-local,
keyed on checkout path, and never propagate. That fragmentation is why this repo exists.

## 3. Bump the version — MANDATORY, in BOTH files

They must stay equal, or the publish silently no-ops:

- `plugins/<plugin>/.claude-plugin/plugin.json` → `version`
- `.claude-plugin/marketplace.json` → that plugin's entry → `version`

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
