---
name: discord-triage
description: Triage new Final Factory bug reports from the Discord #bug-reports forum. Classifies each report, auto-fixes obvious low-risk bugs end-to-end through the speckit flow, and files a GitHub issue + pings the team in #dev-chat for anything unclear or risky. Invoke when the user asks to check/triage Discord bug reports, to run a pass by hand, or to triage on a machine that has no ffbox.
---

# Discord bug triage

Process **new** bug reports from the Discord bug-reports forum. One pass per invocation:
read what's new, classify each report, act, advance the cursor. Idempotent — the cursor only
advances after a report is fully handled.

## Who normally runs this

On a machine with ffbox, **ffwatch does**, exactly as it does for `ask-claude`. A bug thread
becomes one multi-turn conversation with a resumed session rather than a series of unrelated
one-shots; the triage turn is launched read-only, with no write tools at all; and a verdict of
AUTOFIX enqueues a separate `fix` turn, re-based onto `develop`, whose work the harness
verifies, pushes and turns into a pull request. Nothing in this file changes for that —
ffwatch loads these same skills and roles through `--plugin-dir`, so this is the policy its
containers follow. What does change is who acts on the verdict: see "On the build server" in
`reference.md` §AUTOFIX flow.

Running a pass by hand is the fallback, for a machine with no ffbox (BEAST, Windows) or a box
where ffwatch is stopped. `/loop 15m /discord-triage` still works and is the same thing on a
timer, but it is a convenience rather than the design: it re-queries Discord on a fixed
interval whether or not anything happened, and every pass starts cold. Check whether ffwatch
is already running first — `python3 ffbox/ffwatch.py status`, or
`systemctl --user status ffwatch` — because two things triaging the same forum will both
triage every report.

The CLI is `ffdiscord` (zero deps, Python 3 stdlib); its full command reference, the cursor
rules, and setup live in the `discord-cli` skill beside this one. Discord-side configuration
(the bot, intents, channel permissions) is the game repo's
`Documentation/Discord-Agent-Integration.md`. If the CLI
reports no token or `doctor` fails, STOP and tell the user — do not improvise another channel.

**Templates, the full AUTOFIX gate list, and the forbidden zones live in `reference.md` next
to this file** — read the relevant section before acting on a verdict; this file is the flow.

## 0. Preflight (every run)

```bash
ffdiscord doctor
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
ffdiscord unseen bug_reports --key bugs --limit 10
```

Do **not** pass `--mark` yet. For each thread listed, read it end to end and pull the
attachments (the log usually contains the stack trace that decides the whole triage):

```bash
ffdiscord thread <thread_id>
ffdiscord download <thread_id> <message_id> --dir <scratch>/ffbug-<thread_id>
```

`<scratch>` is any writable temp dir — `$TMPDIR` on macOS/Linux, `%TEMP%` on Windows.

Read the log for exceptions, and note the game version — a bug against an old version may
already be fixed on `develop`. Check that with `git log`, and path-trace the claim.

If more than ~5 new reports are waiting, handle the oldest 5 this pass and say so; the next
pass picks up the rest. Never batch-skim a backlog into snap verdicts.

## 2. Classify

Assign exactly one verdict per report. When torn between two, take the more conservative one
(escalate rather than auto-fix; ask rather than assume).

| Verdict | Meaning | Action |
|---|---|---|
| **AUTOFIX** | Genuine bug, root cause found in source, fix is low-risk *and* passes every gate in `reference.md` §AUTOFIX gates | §3 |
| **ESCALATE** | Genuine or probable bug that is unclear, risky, or wide-reaching | §4 |
| **NEEDS-INFO** | Plausible but not actionable — no repro, no log, ambiguous description | §5 |
| **NOT-A-BUG** | Working as designed, user error, or a feature request | §5 |
| **DUPLICATE** | Same root cause as an open issue or an earlier thread | §5 |
| **ALREADY-FIXED** | Reproduced against the reported version, fixed on `develop` since | §5 |

Ground every verdict in source. Per `CLAUDE.md`, cite `file.cs:line` for every claim about
what the code does — including "this isn't a bug because X". A verdict from memory or from a
subagent summary you did not verify is not a verdict.

## 3. AUTOFIX

**First check every gate and forbidden zone in `reference.md` — if ANY gate fails, the
verdict is ESCALATE.** No exceptions, no "it's probably fine". Hard preconditions: the Unity
MCP bridge must be live and pinned (bridge down → ESCALATE and say so), and **max 3 autofixes
per pass** — bounded blast radius matters more than throughput.

Spawn **one agent per bug** with `isolation: "worktree"` so parallel fixes cannot collide —
the `discord-triager` agent for the investigation, then an implementing agent for the fix. If
the Agent tool isn't available in this session, do the same work inline in a worktree
(`EnterWorktree`), one bug at a time — never in the shared checkout. The agent runs the
speckit flow, implements fix + regression test, verifies through the bridge, and opens a PR
targeting `develop` — full step list and the close-the-loop message templates:
`reference.md` §AUTOFIX flow. **Never merge to `master`** — `develop` is the integration
branch; `master` is release-controlled and reaching it is always Ben's call (`CLAUDE.md`).

If the agent's verification fails, or it discovers the fix is larger than believed, it must
STOP and hand back — the verdict silently becomes ESCALATE, and you file the issue in §4
including what was attempted and why it was abandoned.

**Voice for all posts: read [the `max-voice` skill](../max-voice/SKILL.md) first.** Both the player-facing
thread reply (plain language, warm, dry but never at the reporter's expense) and the
`#dev-chat` note (dev register: terse, technical) post as Max. No em dashes, none of the LLM
house phrases that file bans.

## 4. ESCALATE

File a GitHub issue with everything a human needs to not re-do your work — the exact template
is `reference.md` §Issue template. Then alert both humans in #dev-chat and acknowledge the
reporter (commands + templates: `reference.md` §Escalation messages).

## 5. Reply-only verdicts

No issue, no code. Reply in the thread as Max, per [the `max-voice` skill](../max-voice/SKILL.md). Keep it brief
and warm; these are players, and the reply is the entire experience they get from reporting.
Per-verdict content guidance + the react commands: `reference.md` §Reply-only verdicts. Add a
👀 reaction when you start on a report and ✅ when it's resolved.

## 6. Advance the cursor and report

Only after every report in the batch has been acted on:

```bash
ffdiscord mark-seen bugs <high_water_id>
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
