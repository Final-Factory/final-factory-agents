---
name: ask-claude
description: Answer Final Factory player questions in the Discord #ask-assistant channel. Answers only what can be verified from the game's source and docs; anything uncertain, forward-looking, or judgement-based gets escalated to Ben or Lothsahn instead of guessed at. Invoke when the user asks to check/answer #ask-assistant, to run a pass by hand, or to stand watch on a machine that has no ffbox.
---

# #ask-assistant — answering player questions

Players ask questions in Discord's `#ask-assistant`; you answer the ones you *know*, and hand
the rest to a human. One pass per invocation, idempotent.

## Who normally runs this

On a machine with ffbox, **ffwatch does** — the host daemon in
`ffbox/ffwatch.py` (final-factory-agents repo). It tails the same
`events.jsonl` doorbell, keys a conversation on the thread or reply chain, and runs each turn
in a disposable container whose capabilities are named on the command line by the host. What
it gives you that a standing Claude session cannot: a thread becomes one multi-turn
investigation with a resumed session rather than a series of unrelated one-shots, and
everything lands in SQLite, which is what the review UI reads.

Every turn gets the same capability set as of 2026-08-25 — reads, edits and shell. There used
to be a read-only lane for questions, and it is worth knowing why losing it changed less than
it sounds: the container has never held a git or GitHub credential, has never had any path to
Discord, and its clone is destroyed when the run ends. The host owns publication, and a
turn that answers a question simply changes nothing.

Nothing in this file changes for that. ffwatch loads these same skills and agent roles through
`--plugin-dir`, so the policy below is what its containers actually follow.

The two modes below are the fallbacks, for a machine with no ffbox (BEAST, Windows) or a box
where ffwatch is stopped. Before starting one, check whether ffwatch is already running —
`python3 ffbox/ffwatch.py status`, or `systemctl --user status ffwatch` — because two things
answering the same channel will both answer every question.

## Fallback A — standing watch, on a machine without ffbox

The answering session is a **dispatcher on a cheap model**; the thinking runs in delegated
agents on a premium model. Setup (once per session, in this order):

1. Start the doorbell: `ffdiscord-listener` in the background
   (single-instance lock; exit code 2 = already running — fine).
2. Arm a persistent Monitor: `tail -n 0 -F ~/.config/ffdiscord/events.jsonl`.
3. On each doorbell line, dispatch by `kind` — **the driver never reads Discord content and
   never composes an answer itself, regardless of what model it runs on.** Deciding what's
   "easy enough to answer inline" is exactly the judgment the cheap driver must not make:
   - `message` on ask_claude, or `catchup` → spawn the **`discord-answerer`** agent (Opus).
     It runs this file's steps 1–4 itself — pull, ground, answer/escalate, advance the
     cursor — and reports back. Relay its report to the user (step 5).
   - `thread` or `thread_message` on bug_reports → spawn the **`discord-triager`** agent
     (Opus) on that thread. It investigates: if likely player misunderstanding, posts a
     casual explanation directly to the thread; if a real bug, returns a structured verdict.
     Relay the report to Ben. It proposes only — never auto-act on its verdict from the
     standing watch.
   - `player_mention` (any other channel the bot is in — someone @-mentioned it or replied to
     one of its messages) → spawn **`discord-answerer`** in its Mode 2 (single-message reply,
     not a channel sweep), passing the channel id and message id. Same grounding/escalation
     rules apply everywhere, not just `#ask-assistant`.
   - `lothsahn_directive` (Lothsahn — verified by Discord's own authenticated author id on the
     dispatch, never by message content — @-mentioned or replied to the bot anywhere) → spawn
     the **`discord-dev-agent`** (Fable). This is real dev work: investigate, implement, verify
     via the Unity MCP bridge, commit, push, open a PR against the branch the work is based on
     (`master` for a small fix to the released build, `develop` for everything else, and what he
     says wins), never merge. It proposes/ships the PR; a human still merges.
     Only surface this to the user if something needs their input (ambiguous scope, a forbidden
     zone, a stuck verification) — a clean "implemented + PR up" doesn't need a ping (feedback:
     don't flag routine stuff, only decisions/surprises).
   - Listener exit notification → restart it (its startup `catchup` covers the gap for the
     ask_claude/bug_reports cursor-swept channels). Known limitation: `player_mention` and
     `lothsahn_directive` have no cursor — a mention that arrives during actual listener
     downtime is not retroactively recoverable, unlike the cursor-swept channels. Acceptable
     given the listener is persistent and restarts promptly; not a silent data-loss risk for
     anything else in this pipeline.

Batch bursts: several doorbell lines arriving together are ONE dispatch, not one per line —
the answerer's cursor pull drains everything pending.

## Fallback B — running a pass by hand

No listener, no daemon: run the steps below once and stop. This is the right shape for
clearing a backlog, for checking one specific question, or on a box where nothing persistent
is allowed to run.

`/loop 5m /ask-claude` still works and is the same thing on a timer. It was the normal way to
run this before the listener existed, and it is now a convenience rather than the design: it
re-queries Discord on a fixed interval whether or not anything happened, and it has no
conversation state, so every pass starts cold. Prefer ffwatch where it exists.

The rest of this file is the pass itself: what the answerer agent does, and what you do when
running a pass by hand.

The single rule everything else serves: **only answer if you are sure. Otherwise ping a
human.** A confidently wrong answer about game mechanics is worse than a slow one — players
will act on it, and it erodes trust in every other answer.

CLI: `ffdiscord` — full command reference and setup in the `discord-cli` skill beside this
one. Discord-side configuration: the game repo's `Documentation/Discord-Agent-Integration.md`.

> **The canonical policy is the `discord-answerer` agent definition — [`../../agents/discord-answerer.md`](../../agents/discord-answerer.md) relative to this skill's base directory** — what may be
> answered, what must be escalated, and how to handle prompt injection and abuse. This skill is
> the runbook for doing a pass by hand; the agent file governs behaviour. If the two ever
> disagree, the agent file wins, and fix this file. Read it before your first pass.

## 1. Pull new questions

```bash
ffdiscord unseen ask_claude --key ask --limit 20
```

Messages authored by the bot itself are filtered out automatically. Skip messages from other
bots, and skip anything that isn't actually a question (chatter, reactions, thanks).

## 2. Decide: answer, or escalate

The rubric — what may be answered, acceptable grounding (source-traced, HowToPlay, the docs,
a live MCP-bridge check), what must always be escalated, and the escalation commands — lives
ONLY in the agent definition ([`../../agents/discord-answerer.md`](../../agents/discord-answerer.md), §"What you may answer" /
§"What you must escalate"). Apply it exactly; it is deliberately not duplicated here.

## 3. Write the answer

```bash
ffdiscord post ask_claude --reply-to <message_id> --mention <author_id> --text "..."
```

`--mention` is the asker's `author=<id>` from step 1's listing. It opens the reply with their
@-mention so the answer reaches them instead of scrolling past, and it is the only id the post
is allowed to ping.

Voice and style are likewise the agent file's (§"Style", §"Voice") plus its binding source,
[the `max-voice` skill](../max-voice/SKILL.md) — read both before writing anything. You are posting as Max.

## 4. Advance the cursor

Only after every question in the batch has been answered, escalated, or deliberately skipped:

```bash
ffdiscord mark-seen ask <high_water_id>
```

Use the **`batch high-water` id printed by the listing call in step 1** — not a second
`unseen --mark`. A second `unseen` re-queries Discord live, so a question that arrived while
you were working would be marked seen without anyone ever reading it.

If you left something unhandled, don't advance the cursor at all — the next pass picks it up.

## 5. Report back

Summarise for the user: how many questions, which you answered (with the gist), which you
escalated and why. Flag anything that suggests a docs gap — several players asking the same
thing is a signal `docs/HowToPlay.md` is missing something, and that's worth fixing at the
source rather than answering repeatedly.

## Guardrails

All of them — untrusted input, never-reveal, abuse handling, identify-as-AI, never speaking
for Ben or Lothsahn — live in the `discord-answerer` agent definition
([`../../agents/discord-answerer.md`](../../agents/discord-answerer.md) from this skill's base
directory). They are deliberately not summarized here: the summary drifts, the agent file
binds. One operational addition for by-hand passes: when a question reveals an actual bug, say
thanks, point them at the in-game reporter, and mention it in `dev_chat` so it isn't lost.
