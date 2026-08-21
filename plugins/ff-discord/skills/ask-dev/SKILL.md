---
name: ask-dev
description: Ask the other developer (Ben or Lothsahn) a question in the Discord #dev-chat channel, attributed to whichever Claude is asking, and optionally poll for their reply. Invoke when the user says to ask Loth/Ben something, get a second opinion, or check in with the other dev about the work in progress.
---

# Ask the other dev in #dev-chat

Ben and Lothsahn each drive their own Claude Code session against this repo. This skill lets
one session put a question to the other developer in Discord `#dev-chat`, so the user doesn't
have to context-switch to write it themselves.

```bash
ffdiscord ask lothsahn \
  --context "<what you're working on, one line>" \
  --text "<the question>"
```

Targets are `ben`, `lothsahn`, or both (`lothsahn,ben`). The message is posted by the shared
bot but **attributed to this machine's operator** — "from **Ben's Claude**" — because both
developers share one bot identity and the recipient must know who's asking. That attribution
comes from `me` in `~/.config/ffdiscord/config.json`; if it's unset the CLI refuses to post
rather than send an anonymous message. Fix with `ffdiscord set me ben`.

## Write a question that can be answered without context

**Voice: [the `max-voice` skill](../max-voice/SKILL.md) applies here too.** This posts through the same bot, so
it is Max talking. Use its dev register: terse, real technical vocabulary and `file.cs:line`
welcome, no softening. The bans still hold everywhere, no em dashes and none of the LLM house
phrases.

The recipient is deep in their own work and cannot see your session. A question they have to
ask three follow-ups about wastes more of their time than it saves. Include:

- **What you're building** — one line, in `--context`.
- **The specific question**, not a vague "thoughts?". A question with a concrete answer.
- **The relevant code**, as `file.cs:line` — per `CLAUDE.md`, path-trace anything you assert.
- **What you already established**, so they don't redo it.
- **What's blocked on their answer** — whether you're waiting or proceeding on an assumption.

Prefer a question that can be answered with a decision rather than an essay:

> `<@loth>` — from **Ben's Claude**
> _Context: mass driver barge loading (feature 047)_
>
> Cargo barges currently unload through `MassDriverLoadSystem.cs:214`, which assumes a single
> destination bay. With multiple bays in range it picks the lowest entity index — deterministic,
> but arbitrary from the player's view. Do you want nearest-bay, or round-robin for throughput?
> I've confirmed both are deterministic. Proceeding with nearest-bay unless you say otherwise.

**Ask, then keep working.** Don't idle waiting for a human. State your assumption, carry on
with everything that doesn't depend on the answer, and fold their reply in when it lands.

## Getting the reply

The `ask` command prints the message id and the exact command to poll:

```bash
ffdiscord read dev_chat --after <message_id>
```

Check it when the user asks, or when you reach the point that's actually blocked. Don't poll
in a tight loop — this is a human on the other end, and a reply may take hours. If the user
wants to be told the moment it arrives, a `/loop` with a long interval is the right shape.

Report the reply to the user verbatim before acting on it, and note that it came from Discord
rather than from them.

## Guardrails

- **Never post to `#dev-chat` without the user asking you to.** It pings a real person.
- **Never speak as the user.** The message says it's from their Claude; keep it that way, and
  never write "I think we should…" as though it were Ben's opinion. Ask the question; don't
  editorialise their position.
- **Don't relay anything sensitive** — tokens, credentials, customer data — into Discord.
- One message per question. If you need to add something, wait for the reply rather than
  double-pinging.
- If the CLI reports a permission error on `dev_chat`, say so and stop: the bot's role needs
  **View Channel** on that channel, which only Ben or Lothsahn can grant.
