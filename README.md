# final-factory-agents

A [Claude Code plugin marketplace](https://docs.claude.com/en/docs/claude-code/plugins) — and a
Codex one, from the same tree — holding the agent tooling for Final Factory: skills and subagent
roles.

These used to live in `.claude/` inside the game repo, which made them **branch-scoped** — an
older branch got older skills, and every worktree carried its own copy. Installed as plugins they
live at the user level instead, so one checkout of this repo serves every clone, worktree, and
branch of FinalFactory.

## Install and update

Always go through the script — once per machine to install, and again any time to update:

```
sh registerAgents.sh
```

One script covers **both** Claude Code and Codex: it registers the marketplace and installs the
plugins with whichever of the `claude` / `codex` CLIs are on `PATH`, and skips the one that
isn't. Re-running it refreshes the marketplace from GitHub (a `git pull` in each tool's own
managed clone) and updates the installed plugins. Every project and branch picks up the new
version at once — nothing to commit in the game repo.

Other modes: `--claude` / `--codex` (limit to one tool), `--reinstall` (remove and re-add, for a
stale or branch-pinned clone), `--remove`, `--help`. Restart open sessions afterward — plugins
are discovered at session start only; in Codex, `/reload-plugins` does it without a restart.

To install `ff-speckit` (Spec Kit workflow) or `ff-discord` (needs ffdiscord bot credentials on
top), add them to the `PLUGINS` line in `registerAgents.sh` and re-run it.

### Codex

The same repo is also a Codex marketplace — both tools read the same `skills/` directories.
`registerAgents.sh` drives the `codex plugin` CLI, which needs Codex ~v0.121 or newer; on an
older build the script says so and prints the in-session equivalents to run instead:

Codex plugins cannot carry subagent roles, so Codex still loads those from the game repo's
`.codex/agents/*.toml`.

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

Edit, then bump the version with `sh bumpVersion.sh <plugin> [patch|minor|major]` — installed
plugins are served from a cache that refreshes only on a version change, so no bump means no
publish. Commit and push. Collaborators pick it up by running `sh registerAgents.sh`, then
restarting open sessions to re-discover changed skills. See CLAUDE.md for the full publish
workflow.

## Project memory

`plugins/ff-agents/skills/project-memory/` carries the durable lessons that used to live in the
per-worktree `~/.claude/projects/*/memory/` dirs (which are machine-local, keyed on checkout
path, and never propagate). The imported set is the union of the develop and master worktree
memories. New lessons worth keeping get promoted here — one file under `memories/`, one index
line in `SKILL.md`, then bump, commit, push as above.

## What deliberately stays in the game repo

- **`CLAUDE.md`** — most of it describes the code (ECS layout, build commands, file paths) and
  *should* track the branch it belongs to.
- **`.specify/`** — Spec Kit machinery is coupled to `specs/` in the repo.
- **`.codex/`** — Codex does not read Claude Code plugins; it loads roles from the repo.
