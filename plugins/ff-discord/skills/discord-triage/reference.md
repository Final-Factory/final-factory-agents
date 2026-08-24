# Discord triage reference — gates, zones, templates

Companion to `SKILL.md` (the flow). Consult the section the flow points you at.
## TOC

- [AUTOFIX gates](#autofix-gates)
- [Forbidden zones](#forbidden-zones)
- [Hard preconditions](#hard-preconditions)
- [AUTOFIX flow (agent steps + close-the-loop templates)](#autofix-flow)
- [Issue template](#issue-template)
- [Escalation messages](#escalation-messages)
- [Reply-only verdicts](#reply-only-verdicts)

## AUTOFIX gates — ALL must hold {#autofix-gates}

If **any** gate fails, the verdict is ESCALATE. No exceptions, no "it's probably fine".

1. **Root cause identified in source**, path-traced to `file.cs:line` — not inferred from
   the symptom.
2. **Localized**: roughly ≤3 files, no new public API, no data-format or save-layout change,
   no change to a system's execution group or ordering.
3. **Outside every forbidden zone** (below).
4. **Verifiable**: the fast EditMode suite (`FFEditorTests`) passes AND the change is
   confirmed compiled — through **the Unity MCP bridge or ffbox batchmode**, named explicitly
   because those are the only two channels that prove it. A regression test covering the bug is
   strongly preferred; if the bug cannot be covered by a test, that is a signal to ESCALATE.
5. **No design or balance judgement** — if fixing it means deciding how the game *should*
   behave, that is Ben's call, not yours.
6. **Not a duplicate** of an open PR or issue.

## Forbidden zones — always ESCALATE, never auto-fix {#forbidden-zones}

Two groups. First, every determinism crown-jewel surface — the canonical list is the game
repo's `Documentation/Crown-Jewel-Surfaces.md` (read it; a wrong call there is a silent
cross-peer desync, not a compile error; your tier is inspect-and-cite, never auto-fix).
Second, triage-specific zones:

- Build, release, Steamworks, or anything touching webhooks/secrets
- Binary assets — shaders, materials, prefabs, scenes (cannot be reviewed as a diff)
- Localization **table** structure (adding a `Messages`/`Labels` constant is fine; the table
  rows are batched deliberately — see `CLAUDE.md`)

## Hard preconditions for any autofix {#hard-preconditions}

- **One of the two verification channels must be available.** There is no third, and "I read
  the code carefully" is not one of them.
  - **The Unity MCP bridge**, live and pinned to an instance whose `path` is under this working
    directory (`set_active_instance`). This is the channel on a developer desktop. Without it
    you cannot confirm the code compiled, and a green test run proves nothing on its own — the
    editor keeps the last good assembly.
  - **ffbox batchmode**, which is the channel when the run is a Discord `fix`/`dev` turn on the
    build server. There is no editor and no bridge there. The harness runs
    `unity-editor -runTests -testPlatform EditMode` in the container after the agent exits — a
    cold compile in a fresh container, so the stale-assembly trap cannot occur — and records
    the result where the agent cannot write it. You can run the same thing yourself with
    `ffverify`; it is the only Unity command the lane has, and it writes to its own
    per-invocation results path.
  - Neither available → ESCALATE, and say which channel was missing.
- **Never read Unity's shared results file.** The Performance Testing package writes
  `TestResults.xml` and `PerformanceTestResults.json` into a companyName/productName path that
  every copy of the project shares — `…/AppData/LocalLow/Never Games/finalfactory/` on Windows,
  `~/.config/unity3d/Never Games/finalfactory/` on Linux. Whichever copy ran last clobbers it.
  Trust the MCP job result, or the results file `ffverify` was told to write, and nothing else.
- **Max 3 autofixes per pass.** Beyond that, ESCALATE the remainder. Bounded blast radius
  matters more than throughput. On the build server this is enforced rather than advised:
  ffwatch caps the `fix` lane at three turns per rolling day and blocks the fourth with a
  reason on the record.

## AUTOFIX flow — agent steps + close-the-loop templates {#autofix-flow}

Give the agent the complete report text, the log excerpt, your root-cause analysis with
`file.cs:line` citations, and the thread id. The agent must:

1. Claim a spec number per `CLAUDE.md` (fetch `origin/develop` first; take the next number
   not present on origin and not reserved in the newest handoff commits).
2. Run the speckit flow, kept proportionate to a bug fix:
   `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`.
   The spec is short: the report, the root cause, the fix, the regression test.
3. Implement the fix plus a regression test.
4. **Verify** through whichever channel this run has:
   - *MCP bridge*: confirm the recompile (`refresh_unity`, poll `editor/state` until
     `is_compiling` is false and the domain reload is newer than the edit, then `read_console`
     for `error CS`), then run `FFEditorTests` and require green. A `PASSED` result without a
     confirmed fresh domain reload is worthless — see `CLAUDE.md`.
   - *ffbox batchmode*: run `ffverify` and read its JSON report. The container is fresh, so the
     compile is cold and a `PASSED` cannot be stale. The harness re-runs it after you exit
     regardless, and its result — not your claim — is what gates the PR.
5. Commit, push the branch, open a PR against the branch you based the work on: `develop` for
   anything that can wait for the next version, `master` only when the bug is in the build
   players are running and the fix is small and low-risk. An AUTOFIX reached this point because
   a stranger's bug report said so, so when the call is not obvious it is `develop`.
6. Merge the PR to `develop` once tests are green. A PR into `master` is never yours to merge.

**On the build server, steps 5 and 6 are not yours.** A Discord `fix` or `dev` turn holds no
GitHub token and no push credential, and the image has no `gh` — so `git push` and `gh pr
create` fail for want of a credential rather than for want of permission. Leave the change in
the working tree and describe it. ffbox commits it on `ffbox/<run-id>`, ffwatch pushes it and
opens the PR against whichever branch you based the work on, and the branch, base and PR
recorded come from git and the GitHub API response rather than from anything you write. Nothing merges automatically, ever.

Then close the loop with the reporter and the team. The templates below are *content*
checklists, not wording to copy — the voice is [the `max-voice` skill](../max-voice/SKILL.md):

```bash
ffdiscord post <thread_id> --text "Fixed and merged to develop, so this one's done. <what was wrong, in one plain sentence>. It'll be in the next build. (PR #123)"
ffdiscord post dev_chat --text "🤖 Auto-fixed a bug report: <title> → PR #123 merged to develop. Root cause: <one line>. Thread: <link>"
```

Post the dev-chat note **without** a ping for autofixes — it is an FYI, not an escalation.

## Issue template {#issue-template}

```bash
gh issue create --repo Final-Factory/FinalFactory \
  --title "<concise symptom>" \
  --body "$(cat <<'EOF'
Reported on Discord: <thread link>
Reporter: <discord name>  |  Version: <x.y.z>  |  Platform: <...>

## What the player reported
<verbatim description>

## Log evidence
<the relevant stack trace / error lines, fenced>

## Analysis
<what you established, with file.cs:line citations>

## Why this was not auto-fixed
<which gate in the triage rubric it failed — e.g. "touches NetworkOperationQueues ordering">

## Suggested next step
<the most promising lead, or the specific question that needs a human decision>
EOF
)"
```

Attach the save file to the issue if it is small enough and the bug is state-dependent;
otherwise note where it is in the thread.

## Escalation messages {#escalation-messages}

Alert both humans in #dev-chat, and acknowledge the reporter:

```bash
ffdiscord post dev_chat --text "🐛 @ben @lothsahn new bug needs a look: <title>. <one-line why it's risky/unclear>. Issue #<n>: <url> | Thread: <link>"
ffdiscord post <thread_id> --text "Logged this as issue #<n> and flagged it to the devs. Thanks for writing it up."
```

`@ben` and `@lothsahn` in the message body expand to real pings automatically.

## Reply-only verdicts {#reply-only-verdicts}

NOT-A-BUG in particular is where the sarcasm rule bites: the joke may point at the game's
weirdness, never at the person who misread it.

- **NEEDS-INFO** — say exactly what would make it actionable (repro steps, whether it
  survives a restart, a save from just before it happens).
- **NOT-A-BUG** — explain the intended behaviour, and where it's explained in game if
  relevant. If it is really a *feature request* worth having, say you've passed it on, and
  mention it in #dev-chat without a ping. Never dismiss curtly.
- **DUPLICATE** — link the existing issue or thread and say it's already tracked.
- **ALREADY-FIXED** — say which version/build carries the fix.

React so players can see a report was picked up (👀 on start, ✅ on resolve):

```bash
ffdiscord react <thread_id> <thread_id> 👀
```
