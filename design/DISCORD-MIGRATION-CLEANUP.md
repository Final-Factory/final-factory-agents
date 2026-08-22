# Discord migration: cleaning up FinalFactory's develop branch

The Discord CLI, the Gateway listener, their offline tests, and the Max voice definition now
live in this repo, in the `ff-discord` plugin. The copies on FinalFactory's `develop` branch are
still there and still work, so nothing is broken while both exist.

This is the runbook for removing them. **Do not start until Ben confirms the migration works on
every machine that runs a Discord loop.** Section 2 is how you establish that.

Long-term end state: the Discord code and skills live here. FinalFactory keeps only what
genuinely belongs to the game (the in-game bug reporter), what Codex cannot load from a plugin
(the `.codex/agents/*.toml` role adapters), and feature 059, which is a separate decision.

## 1. What moved, and where it went

| Was, on `develop` | Is now |
|---|---|
| `scripts/discord/ffdiscord.py` | `plugins/ff-discord/skills/discord-cli/ffdiscord.py` |
| `scripts/discord/ffdiscord_listener.py` | `plugins/ff-discord/skills/discord-cli/ffdiscord_listener.py` |
| `scripts/discord/test_ffdiscord.py` | `plugins/ff-discord/skills/discord-cli/test_ffdiscord.py` |
| `scripts/discord/test_ffdiscord_listener.py` | `plugins/ff-discord/skills/discord-cli/test_ffdiscord_listener.py` |
| `Documentation/Max-Voice.md` | `plugins/ff-discord/skills/max-voice/SKILL.md` |

The Python is byte-for-byte what was on `develop`. Max-Voice gained skill frontmatter and lost a
broken table header that had been sitting in its "bound surfaces" section; the voice rules
themselves are unchanged.

Callers no longer use a path. `registerAgents.sh` installs an `ffdiscord` launcher (and an
`ffdiscord-listener` twin) into `~/.local/bin` when the `ff-discord` plugin is installed, and
every skill and role now says `ffdiscord post ...` instead of
`python3 scripts/discord/ffdiscord.py post ...`. The launcher resolves the newest installed
plugin copy at run time, so version bumps need no reinstall. `FFDISCORD_CLI` overrides it.

## 2. Prove it before you delete anything

All of this has to pass on **every machine that runs a Discord loop**, which today means this
Linux box and BEAST. Deleting from `develop` while one machine is still serving the old copy is
how you get a silent split brain, where two machines answer with different rules.

1. `ff-discord` 1.2.0 or later is committed, pushed, and installed:
   ```
   sh registerAgents.sh --plugin ff-discord
   ```
2. The launcher is on PATH and resolves:
   ```
   command -v ffdiscord
   ffdiscord doctor
   ffdiscord-listener --once-ready
   ```
   `doctor` must exit zero. If `command -v` finds nothing, `~/.local/bin` is not on PATH and the
   script will have said so.
3. The offline suites pass from the installed copy, not from a checkout:
   ```
   cd ~/.claude/plugins/cache/final-factory-agents/ff-discord/*/skills/discord-cli
   python3 test_ffdiscord.py
   python3 test_ffdiscord_listener.py
   ```
4. One real pass of each loop, watched by a human: `/ask-claude` answers a question, and
   `/discord-triage` reads a thread and its attachments. Confirm the posts land as Max and read
   the way they did before.
5. A Codex session in some other repo sees the skills: `$ff-discord:discord-cli` resolves, and
   `ffdiscord doctor` works from inside it.
6. On BEAST specifically, the `.cmd` launcher works from `cmd` or PowerShell, not only git-bash.
   This is the least-tested path in the whole migration.

Only when all six hold on all machines does Ben's confirmation mean anything.

## 3. Update the things that stay but point at the old paths

Do this **before** the deletions in section 4, as its own commit, so the tree is never broken.

**`.codex/agents/discord-answerer.toml` and `.codex/agents/discord-triager.toml`.** These stay
in the game repo permanently: Codex plugins carry skills but not subagent roles, so these
adapters have nowhere else to live. Replace `the CLI scripts/discord/ffdiscord.py` with
`the CLI ffdiscord`, and every `ffdiscord.py <cmd>` with `ffdiscord <cmd>`. Add a line telling
Codex what to do when the launcher is missing: install the plugin with
`sh registerAgents.sh --plugin ff-discord`. There is no `discord-dev-agent.toml`; that role is
Claude-only.

**`scripts/pipeline/pipeline_config.py`.** `DEFAULTS["ffdiscord"]` is
`os.path.join(REPO_ROOT, "scripts", "discord", "ffdiscord.py")`. It is the only hard-coded path
to the CLI in feature 059, and `report.py` shells out through it. Change the default to the
launcher name `"ffdiscord"` and let `subprocess` resolve it on PATH, or resolve the installed
plugin copy. Either way keep the config key overridable, which it already is, and re-run
`python3 scripts/pipeline/test_ffpipeline.py`. That suite fakes every external edge, so it will
tell you immediately if the seam moved.

**`Documentation/Discord-Agent-Integration.md`.** This stays: it documents the Discord server
side, which is not plugin content. Update its command examples to `ffdiscord`, replace the
"Windows: use `python` not `python3`" notes with the launcher, and add the install step
(`sh registerAgents.sh --plugin ff-discord`) to the per-machine setup list. Point its voice
references at the `max-voice` skill.

**`Documentation/Claude-Discord-Pipeline.md`.** Its Testing section lists
`python3 scripts/discord/test_ffdiscord.py`. Those tests are no longer in this repo; point at
the plugin, or drop those two lines and keep only the pipeline suite.

**`deploy/pipeline/README.md` and `deploy/pipeline/ffdiscord-listener.service`.** The unit runs
the listener by path. Point it at `ffdiscord-listener`, and note in the README that the box needs
the plugin installed for the user the unit runs as.

**`CLAUDE.md`.** The Documentation section calls `Max-Voice.md` the single binding definition of
how Max speaks and tells you to add new posting surfaces to its table. Rewrite that to point at
the `ff-discord` plugin's `max-voice` skill, keeping the "linked, never copied" instruction.

**`specs/059-claude-discord-pipeline/`.** Leave it alone. Spec artifacts record what was decided
at the time; rewriting paths in them makes them lie about their own history. If the churn
bothers you, add one line to `plan.md` noting the CLI moved and when.

## 4. Delete what moved

One commit, after section 3 has landed and section 2 has passed.

```
git rm -r scripts/discord
git rm Documentation/Max-Voice.md
```

Then confirm nothing still points at them:

```
git grep -n 'scripts/discord\|Max-Voice'
```

Expect hits only under `specs/059-claude-discord-pipeline/` (intentional, see above). Anything
else is a reference you missed in section 3.

No CI job runs the Discord tests, so nothing in `.github/workflows/` needs touching. Verified
against `develop` at the time of writing.

## 5. What stays, and why

**`.gitignore`'s ffdiscord entries** (`**/ffdiscord/config.json`, `**/ffdiscord/state.json`,
`**/ffdiscord/state.json.lock`, `.ffdiscord/`). Keep every one. The token and cursors still land
in `~/.config/ffdiscord/`, and the test harness still points `FFDISCORD_HOME` at a repo-relative
temp directory. Removing these is how a bot token eventually gets committed.

**The in-game bug reporter.** `Assets/Scripts/UI/Panels/DiscordBugReporter.cs` and
`Assets/Scriptables/DiscordBugForumsWebhook.asset` are game code that posts to the forum webhook.
They have nothing to do with the agent CLI and are not part of this migration.

**Feature 059** — `scripts/pipeline/`, `deploy/pipeline/`, `docs/appsscript/runs.gs`,
`scripts/ffresume.{sh,ps1}`, `specs/059-claude-discord-pipeline/`, and
`Documentation/Claude-Discord-Pipeline.md`. Code-complete and offline-tested as of 2026-08-02,
never deployed. It is a server daemon that overlaps the ffbox conversation design in
`discord_persistent_design.txt`, and what happens to it is a design decision, not a cleanup.
Section 3's one-line change to `pipeline_config.py` is all this migration asks of it.

**`.codex/agents/discord-*.toml`.** Permanent residents, per the runtime asymmetry in this
repo's `CLAUDE.md`: Codex plugins cannot carry subagent roles. They need the path update in
section 3 and nothing more.

## 6. If it goes wrong

The deletion commit is a plain revert. Before reverting, try the cheaper fix: set
`FFDISCORD_CLI` to a working `ffdiscord.py` on the affected machine. That bypasses launcher
resolution entirely and gets the loops running again while you diagnose.

If a machine is serving stale skills rather than a broken CLI, the cause is almost always the
publish workflow rather than this migration: no version bump means `claude plugin update`
reports "already at the latest version" and keeps serving the old content. Check the installed
version against `.claude-plugin/marketplace.json`, and remember that sessions discover plugins
only at start, so an open session needs restarting.
