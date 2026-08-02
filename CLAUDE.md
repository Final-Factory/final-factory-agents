# final-factory-agents

Claude Code **plugin marketplace** for Final Factory. Skills, subagent roles, and project
memory live here — NOT in the game repo — so one checkout serves every clone, worktree, and
branch of FinalFactory. See README.md for install instructions.

## Layout

```
.claude-plugin/marketplace.json     Claude Code marketplace — 3 entries, each with a version
.agents/plugins/marketplace.json    Codex marketplace — same 3 plugins, NO versions here
plugins/<name>/
  .claude-plugin/plugin.json        Claude plugin manifest — name + version
  .codex-plugin/plugin.json         Codex plugin manifest — name + version + skills globs
  skills/<skill>/SKILL.md           SHARED by both tools. YAML frontmatter: name + description
  agents/<role>.md                  Claude Code ONLY — Codex plugins cannot carry subagent roles
registerClaude.sh                   idempotent per-machine bootstrap (marketplace add + install);
                                    --reinstall (remove + re-add, for a stale clone),
                                    --remove, --help; also records this checkout's path to
                                    ~/.claude/final-factory-agents-checkout so publish-skills
                                    can find it on any machine, wherever it was cloned
```

Plugins: `ff-agents` (core roles + skills, incl. `project-memory`), `ff-speckit`
(speckit-* skills), `ff-discord` (Discord roles + skills).

## Updating skills — the publish workflow

Installed plugins are served from a **cache copy** under
`~/.claude/plugins/cache/final-factory-agents/<plugin>/<version>/`, NOT from this working
copy, and the cache refreshes **only on a version change**. Editing a file here does
nothing to live sessions until you publish:

1. Edit skills/agents under `plugins/<plugin>/`.
2. Bump the version in **ALL THREE** places (they must stay equal):
   - `plugins/<plugin>/.claude-plugin/plugin.json` → `version`
   - `plugins/<plugin>/.codex-plugin/plugin.json` → `version`
   - `.claude-plugin/marketplace.json` → that plugin's entry → `version`

   (`.agents/plugins/marketplace.json` carries no versions — nothing to bump there.)
3. Commit and push.
4. On each machine: `claude plugin update <plugin>@final-factory-agents`
   (if the marketplace was added from GitHub rather than a local path, run
   `claude plugin marketplace update final-factory-agents` first — that is the git pull).
5. Restart open Claude Code sessions — plugins are discovered at session start only.

Forgetting step 2 is the classic failure: `claude plugin update` reports "already at the
latest version" and silently serves the old content. No version bump = no publish.

The `publish-skills` skill in `ff-agents` carries this same workflow, so a Claude session in
ANY repo (the game repo included, where skills no longer exist locally) knows to come here
and how to publish. Keep the two in sync when the workflow changes.

## Adding a skill

Create `plugins/<plugin>/skills/<name>/SKILL.md` with `name:` and `description:` frontmatter
(supporting files live next to it in the same directory), then follow the publish workflow.
New durable project lessons go in `plugins/ff-agents/skills/project-memory/` — one file under
`memories/`, one index line in its SKILL.md — not in the machine-local
`~/.claude/projects/*/memory/` dirs, which never propagate.

## Adding a plugin

Create `plugins/<name>/.claude-plugin/plugin.json`, add a matching entry (same name, same
version) to `.claude-plugin/marketplace.json`, and add the plugin to the `PLUGINS` line in
`registerClaude.sh` if every machine should install it.

## Codex support

Codex has its own plugin marketplace with the SAME `skills/<name>/SKILL.md` layout, so both
tools read one shared `skills/` tree — no duplication, no symlink bridge (the old
`.agents/skills/` bridge in the game repo is retired; it never worked on Windows anyway).
Codex install: `/plugin marketplace add Final-Factory/final-factory-agents`,
`/plugin install ff-agents@final-factory-agents`, `/reload-plugins`.

Two asymmetries to keep in mind when editing:

- **Subagent roles are Claude-only.** Codex plugins carry skills, MCP servers, app connectors,
  and hooks — not agents. Codex roles stay repo-local in the game repo's `.codex/agents/*.toml`.
- **Skill bodies that delegate to Claude subagents degrade under Codex** (e.g. `deep-think`
  refers to the `deep-thinker` agent). Codex is expected to do the work inline instead. Do not
  fork skill bodies per tool — keep one copy and let it degrade gracefully.

The Codex manifests are UNVERIFIED — nobody on the Claude side runs Codex. Ben tests and fixes.

## Gotchas

- `marketplace.json` and `plugin.json` are UTF-8 with literal em-dashes; edit them with
  Edit/Write, not scripted re-serialization that can mangle the encoding.
- Machine registration is once per machine (`sh registerClaude.sh`), user scope — never
  per project. The marketplace is registered from GitHub (`Final-Factory/final-factory-agents`),
  so the machine needs git read access to the repo; Claude Code keeps its own clone under
  `~/.claude/plugins/marketplaces/` — this working copy is NOT what live sessions read.
- The game repo may still carry legacy copies of these skills in `.claude/skills/` on some
  branches; those shadow the plugin for bare `/name` invocations until removed there.
