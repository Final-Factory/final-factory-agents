---
name: capacity-is-never-a-question
description: "Never ask a person for capacity or a computer: to bring one online, wake or unpause it, say which one may run work, allow one that is allowed, or run its installer. Work that no online computer fits waits Queued and starts by itself on the first that fits. The one exception is a blocker only that person can clear (their own login, password or FileVault, a reboot of their own machine, an admin prompt)."
date: 2026-10-25
---

# Capacity is never a question for a person

**The rule.** Workers, dispatchers and orchestrators never ask a person for capacity or a computer. That means no
question to bring a computer online, wake or unpause one, say which computer may run or time the work, allow a computer
the rules already allow, or run an installer or an update on one. Computers come and go: work that no online computer
fits waits **Queued** and starts by itself on the first one that fits, in the timing order (smallest free computer
first, then pre-emption of movable work on a small one, then the queue; a big computer only for high or urgent work, or
when every smaller one is offline). The one exception is a concrete blocker only that person can clear: their own login,
password, FileVault or 2FA code, a reboot of their own machine, an admin prompt. Name that blocker and the smallest step.

lothsahn, 2026-10-25 (w2147, from w1958): "Stop asking to bring computers online. It's a cluster where computers are
sometimes online and sometimes paused. Use and schedule resources based on what you have. Don't ask for permission."

## Why: two cases

- **w1958 (2026-10-25).** The worker, on m5 (which takes no timed runs), queued a Windows frame-rate A/B for
  desktop-coosego, which was offline. `timed_place` then answered "no small computer takes w1958's timed leg: ask an
  operator", and the worker put a card in front of lothsahn: "bring desktop-coosego back online, or say which computer
  may time the shield frame-rate A/B". The portal itself suggested the question, so the fix (FF Factory w2147) went into
  the tool as well as the rule: `timed_place` now always files the leg Queued, and `waiting_on_person` and the
  dispatcher's `decide_work ask` refuse a wait whose only ask is a computer.
- **w847 (2026-10-10).** The dispatcher asked Ben to rerun biscuit's installer. lothsahn: "don't ask ben to run
  installers.  Update your instructions.  Stop doing that.  When we say update the machines, do the update, including
  installers if necessary". This lesson treats it as the first correction of the same kind (a machine's state handed
  to a person), so w1958 was the second, and the second gets a tool check
  ([a wait on a person is declared, not polled](a-person-wait-is-declared-not-polled.md)).

## How to apply

- **Timed work**: `timed_run` queues for its computer and goes out by itself when that computer is back; `timed_place`
  files the leg Queued even when nothing fitting is online. Never wait for one named computer when another that takes
  timed runs fits. The exclusions stand: m5 takes no timed runs.
- **A check on several computers**: `request_pair`, which waits for them by itself.
- **Anything else that needs a computer that is offline or busy**: commit and push, then end the turn with
  `wNNN: still open: queued for <the computer or kind of computer>`. The dispatcher queues it (`decide_work queue`
  with needs) and it starts when one fits.
- **Installers, daemon updates, reinstalls**: the ops worker (`ops_worker machine_update`) or ssh, never a person.
- **Before you call `waiting_on_person`**, read each question: if its only ask is a computer's availability or choice,
  it is a capacity wait, not a card. The portal refuses it (`shared/machineAsk.ts`), and the refusal costs you a turn.
