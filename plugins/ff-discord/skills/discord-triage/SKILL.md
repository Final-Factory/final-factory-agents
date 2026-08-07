---
name: discord-triage
description: Triage new Final Factory bug reports from the Discord #bug-reports forum. Classifies each report, auto-fixes obvious low-risk bugs end-to-end through the speckit flow and merges them to develop, and files a GitHub issue + pings the team in #dev-chat for anything unclear or risky. Invoke when the user asks to check/triage Discord bug reports, or on a loop.
---

# Discord bug triage

Process **new** bug reports from the Discord bug-reports forum. One pass per invocation:
read what's new, classify each report, act, advance the cursor. Designed to be run on a
`/loop` — it is idempotent (the cursor only advances after a report is fully handled).

The CLI is `scripts/discord/ffdiscord.py` (zero deps, Python 3 stdlib). Setup and the
Discord-side configuration live in `Documentation/Discord-Agent-Integration.md`. If the CLI
reports no token or `doctor` fails, STOP and tell the user — do not improvise another channel.

## 0. Preflight (every run)

```bash
python3 scripts/discord/ffdiscord.py doctor
```

If it exits non-zero, report the problem to the user and stop. A half-configured bot that
can read but not reply will silently drop player-facing responses.

**Bug reports arrive as forum posts** from the in-game reporter webhook
(`Documentation/BugReportingSystem.md`): an embed carrying the title, the player's
description, game version, platform, and Unity version, plus attachments — a runtime log
(last 500 entries) and a save zip captured at report time. Player follow-up replies land in
the same thread.

## 1. Pull what's new

```bash
python3 scripts/discord/ffdiscord.py unseen bug_reports --key bugs --limit 10
```

Do **not** pass `--mark` yet. For each thread listed, read it end to end and pull the
attachments (the log usually contains the stack trace that decides the whole triage):

```bash
python3 scripts/discord/ffdiscord.py thread <thread_id>
python3 scripts/discord/ffdiscord.py download <thread_id> <message_id> --dir <scratch>/ffbug-<thread_id>
```

`<scratch>` is any writable temp dir — `$TMPDIR` on macOS/Linux, `%TEMP%` on Windows.

Read the log for exceptions, and note the game version — a bug against an old version may
already be fixed on `develop`. Check that with `git log`, and path-trace the claim.

If more than ~5 new reports are waiting, handle the oldest 5 this pass and say so; the next
loop iteration picks up the rest. Never batch-skim a backlog into snap verdicts.

## 2. Classify

Assign exactly one verdict per report. When torn between two, take the more conservative one
(escalate rather than auto-fix; ask rather than assume).

| Verdict | Meaning | Action |
|---|---|---|
| **AUTOFIX** | Genuine bug, root cause found in source, fix is low-risk *and* passes every gate in §3 | §4 |
| **ESCALATE** | Genuine or probable bug that is unclear, risky, or wide-reaching | §5 |
| **NEEDS-INFO** | Plausible but not actionable — no repro, no log, ambiguous description | §6 |
| **NOT-A-BUG** | Working as designed, user error, or a feature request | §6 |
| **DUPLICATE** | Same root cause as an open issue or an earlier thread | §6 |
| **ALREADY-FIXED** | Reproduced against the reported version, fixed on `develop` since | §6 |

Ground every verdict in source. Per `CLAUDE.md`, cite `file.cs:line` for every claim about
what the code does — including "this isn't a bug because X". A verdict from memory or from a
subagent summary you did not verify is not a verdict.

## 3. AUTOFIX gates — ALL must hold

If **any** gate fails, the verdict is ESCALATE. No exceptions, no "it's probably fine".

1. **Root cause identified in source**, path-traced to `file.cs:line` — not inferred from
   the symptom.
2. **Localized**: roughly ≤3 files, no new public API, no data-format or save-layout change,
   no change to a system's execution group or ordering.
3. **Outside every forbidden zone** (below).
4. **Verifiable**: the fast EditMode suite (`FFEditorTests`) passes AND the change is
   confirmed compiled via the MCP bridge. A regression test covering the bug is strongly
   preferred; if the bug cannot be covered by a test, that is a signal to ESCALATE.
5. **No design or balance judgement** — if fixing it means deciding how the game *should*
   behave, that is Ben's call, not yours.
6. **Not a duplicate** of an open PR or issue.

### Forbidden zones — always ESCALATE, never auto-fix

Two groups. First, every determinism crown-jewel surface — the canonical list is the game
repo's `Documentation/Crown-Jewel-Surfaces.md` (read it; a wrong call there is a silent
cross-peer desync, not a compile error; your tier is inspect-and-cite, never auto-fix).
Second, triage-specific zones:

- Build, release, Steamworks, or anything touching webhooks/secrets
- Binary assets — shaders, materials, prefabs, scenes (cannot be reviewed as a diff)
- Localization **table** structure (adding a `Messages`/`Labels` constant is fine; the table
  rows are batched deliberately — see `CLAUDE.md`)

### Hard preconditions for any autofix

- **The Unity MCP bridge must be live** (an instance whose `path` is under this working
  directory, pinned with `set_active_instance`). Without it you cannot confirm the code
  compiled, and a green test run proves nothing — the editor keeps the last good assembly.
  Bridge down → ESCALATE instead, and tell the user the bridge is down.
- **Max 3 autofixes per pass.** Beyond that, ESCALATE the remainder. Bounded blast radius
  matters more than throughput.

## 4. AUTOFIX — the full flow

Spawn **one agent per bug** with `isolation: "worktree"` so parallel fixes cannot collide —
the `discord-triager` agent for the investigation, then an implementing agent for the fix. If
the Agent tool isn't available in this session, do the same work inline in a worktree
(`EnterWorktree`), one bug at a time — never in the shared checkout.
Give the agent the complete report text, the log excerpt, your root-cause analysis with
`file.cs:line` citations, and the thread id. The agent must:

1. Claim a spec number per `CLAUDE.md` (fetch `origin/develop` first; take the next number
   not present on origin and not reserved in the newest handoff commits).
2. Run the speckit flow, kept proportionate to a bug fix:
   `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`.
   The spec is short: the report, the root cause, the fix, the regression test.
3. Implement the fix plus a regression test.
4. **Verify**: confirm the recompile through the MCP bridge (`refresh_unity`, poll
   `editor/state` until `is_compiling` is false and the domain reload is newer than the
   edit, then `read_console` for `error CS`), then run `FFEditorTests` and require green.
   A `PASSED` result without a confirmed fresh domain reload is worthless — see `CLAUDE.md`.
5. Commit, push the branch, open a PR **targeting `develop`** (never `master`).
6. Merge the PR to `develop` once tests are green.

**Never merge to `master`.** `develop` is the integration branch; `master` is release-
controlled and reaching it is always Ben's call (`CLAUDE.md`).

If the agent's verification fails, or it discovers the fix is larger than believed, it must
STOP and hand back — the verdict silently becomes ESCALATE, and you file the issue in §5
including what was attempted and why it was abandoned.

Then close the loop with the reporter and the team:

**Voice: read `Documentation/Max-Voice.md` before writing either message.** Both post as Max.
The thread reply is player-facing (plain language, warm, dry but never at the reporter's
expense); the `#dev-chat` note uses the dev register (terse, technical). No em dashes anywhere,
and none of the LLM house phrases that file bans. The templates below are *content* checklists,
not wording to copy.

```bash
python3 scripts/discord/ffdiscord.py post <thread_id> --text "Fixed and merged to develop, so this one's done. <what was wrong, in one plain sentence>. It'll be in the next build. (PR #123)"
python3 scripts/discord/ffdiscord.py post dev_chat --text "🤖 Auto-fixed a bug report: <title> → PR #123 merged to develop. Root cause: <one line>. Thread: <link>"
```

Post the dev-chat note **without** a ping for autofixes — it is an FYI, not an escalation.

## 5. ESCALATE — issue + alert

File a GitHub issue with everything a human needs to not re-do your work:

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

Then alert both humans in #dev-chat, and acknowledge the reporter:

```bash
python3 scripts/discord/ffdiscord.py post dev_chat --text "🐛 @ben @lothsahn new bug needs a look: <title>. <one-line why it's risky/unclear>. Issue #<n>: <url> | Thread: <link>"
python3 scripts/discord/ffdiscord.py post <thread_id> --text "Logged this as issue #<n> and flagged it to the devs. Thanks for writing it up."
```

`@ben` and `@lothsahn` in the message body expand to real pings automatically.

## 6. Reply-only verdicts

No issue, no code. Reply in the thread as Max, per `Documentation/Max-Voice.md`. Keep it brief
and warm; these are players, and the reply is the entire experience they get from reporting.
NOT-A-BUG in particular is where the sarcasm rule bites: the joke may point at the game's
weirdness, never at the person who misread it.

- **NEEDS-INFO** — say exactly what would make it actionable (repro steps, whether it
  survives a restart, a save from just before it happens).
- **NOT-A-BUG** — explain the intended behaviour, and where it's explained in game if
  relevant. If it is really a *feature request* worth having, say you've passed it on, and
  mention it in #dev-chat without a ping. Never dismiss curtly.
- **DUPLICATE** — link the existing issue or thread and say it's already tracked.
- **ALREADY-FIXED** — say which version/build carries the fix.

Add a 👀 reaction when you start on a report and ✅ when it's resolved, so players can see
it was picked up:

```bash
python3 scripts/discord/ffdiscord.py react <thread_id> <thread_id> 👀
```

## 7. Advance the cursor and report

Only after every report in the batch has been acted on:

```bash
python3 scripts/discord/ffdiscord.py mark-seen bugs <high_water_id>
```

Use the **`batch high-water` id printed by the listing call in §1** — not a second
`unseen --mark`. A second `unseen` re-queries Discord live, so a report filed while you were
mid-triage would be marked seen without ever being read.

If a report was left unhandled (e.g. you ran out of the autofix budget), do **not** advance
the cursor at all — let the next pass pick it up.

Finish with a short summary to the user: how many reports, the verdict for each with a
one-line reason, PR/issue numbers, and anything that needs their attention. Lead with a
plain-language TL;DR per `CLAUDE.md`.

## Judgement notes

- **Conservative by default.** A wrongly-escalated bug costs a human five minutes. A wrongly
  auto-merged fix can ship a regression to players or, in the determinism paths, a desync
  that takes days to find. The asymmetry is the whole point of the rubric.
- **A crash log is not a root cause.** A stack trace tells you where it surfaced, not why —
  the same lesson as the determinism work: the first-diverging site is usually where an
  invisible upstream cause finally became observable.
- **Never guess at the player's intent** in the reply. If the report is ambiguous, that is
  NEEDS-INFO, not an opportunity to interpret.
