# final-factory-agents

A [Claude Code plugin marketplace](https://docs.claude.com/en/docs/claude-code/plugins) holding
the agent tooling for Final Factory: skills and subagent roles.

These used to live in `.claude/` inside the game repo, which made them **branch-scoped** — an
older branch got older skills, and every worktree carried its own copy. Installed as plugins they
live at the user level instead, so one checkout of this repo serves every clone, worktree, and
branch of FinalFactory.

## Install

Once per machine (installs and later also updates — safe to re-run any time):

```
sh registerClaude.sh
```

Or by hand:

```
/plugin marketplace add Final-Factory/final-factory-agents
/plugin install ff-agents@final-factory-agents
/plugin install ff-speckit@final-factory-agents     # optional: Spec Kit workflow
/plugin install ff-discord@final-factory-agents     # optional: needs ffdiscord bot credentials
```

### Codex

The same repo is also a Codex marketplace — both tools read the same `skills/` directories.

```
/plugin marketplace add Final-Factory/final-factory-agents
/plugin install ff-agents@final-factory-agents
/reload-plugins
```

Codex plugins cannot carry subagent roles, so Codex still loads those from the game repo's
`.codex/agents/*.toml`. The Codex manifests have not been tested yet.

## Update

```
/plugin marketplace update final-factory-agents
```

That is a `git pull` in `~/.claude/plugins/marketplaces/final-factory-agents/`. Every project and
branch picks up the new version at once — nothing to commit in the game repo.

## Plugins

| Plugin | Contents |
|---|---|
| `ff-agents` | 7 delegation roles (`implementor`, `mech-executor`, `scout`, `Explore`, `build-verifier`, `deep-thinker`, `game-driver`) + 11 skills: `deep-think`, `determinism-audit`, `drive-game`, `handoff`, `learnToPlay`, `massdriver-visual-e2e`, `playtest`, `project-memory`, `publish-skills`, `resumeFromHandoff`, `update-docs` |
| `ff-speckit` | 10 `speckit-*` skills. Operates on the `.specify/` machinery in whichever project you invoke it from — that stays in the game repo. |
| `ff-discord` | 3 roles (`discord-answerer`, `discord-dev-agent`, `discord-triager`) + 3 skills: `ask-claude`, `ask-dev`, `discord-triage`. Requires the bot token in `~/.config/ffdiscord/`. |

## Authoring

Skills live at `plugins/<plugin>/skills/<name>/SKILL.md` and need YAML frontmatter with `name:`
and `description:`. Subagent roles live at `plugins/<plugin>/agents/<name>.md` with `name:`,
`description:`, `model:`, and `tools:`.

Edit, commit, push. Collaborators pick it up with `/plugin marketplace update`. Restart open
Claude Code sessions to re-discover changed skills.

## Project memory

`plugins/ff-agents/skills/project-memory/` carries the durable lessons that used to live in the
per-worktree `~/.claude/projects/*/memory/` dirs (which are machine-local, keyed on checkout
path, and never propagate). The imported set is the union of the develop and master worktree
memories. New lessons worth keeping get promoted here — one file under `memories/`, one index
line in `SKILL.md`, commit, push.

## What deliberately stays in the game repo

- **`CLAUDE.md`** — most of it describes the code (ECS layout, build commands, file paths) and
  *should* track the branch it belongs to.
- **`.specify/`** — Spec Kit machinery is coupled to `specs/` in the repo.
- **`.codex/`** — Codex does not read Claude Code plugins; it loads roles from the repo.
