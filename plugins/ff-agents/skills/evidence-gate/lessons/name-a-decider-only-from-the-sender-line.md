---
name: name-a-decider-only-from-the-sender-line
description: "An approval, hold, override or decision is attributed to a person only when the message names its sender ([from <name>], [from the orchestrator, for <name>]) or the ledger records who asked. A message without that is not from \"the portal user\": write \"unconfirmed\" and ask, never a name."
date: 2026-10-04
---

# Name a decider only from the sender line

**Rule.** Before you write that a person approved, held, lifted, overrode or decided something,
in a PR description, release notes, a ledger note, a commit body or a report, find who sent the
message that asked for it:

- its first line, `[from <name>]` (a person wrote it) or `[from the orchestrator, for <name>]`
  (an orchestrator sent it on their behalf), or `[from FFBox …, <operator>]` for relayed words;
- or the ledger's record of who filed the request (`requestedBy`, `requesters`).

Only that name goes on the decision. A message with no sender line, or one that names nobody
("for no named person", "a person the portal did not name"), is **not** from the portal's owner or
"the user", whoever your prompt says runs the portal. Write "unconfirmed" in place of the name,
and ask your orchestrator or the requester who decided. Never fill the name in from context.

**Why.** 2026-10-04, w389: Lothsahn typed "Undo the release hold" straight into worker 4b35b8c1's
chat (w364, PR #1024, deletion moved onto the fixed tick). FF Factory delivered a person's message
to a worker with no sender line, and the worker's prompt said "The user (the person who runs this
portal) is Ben". The worker wrote "Release hold lifted (Ben, 2026-10-04 18:38 UTC)" into #1024's
description: a release-governance record that put Ben's name on a decision he never made. FF
Factory now names the sender of every message (ff-factory PR #89), but the rule stands on its own:
a missing sender line has to stop the attribution, not get filled in.

**How to apply.**

- Before you write any "(Name, time)" or "Name approved/asked/lifted/held" line, scroll to the
  message it rests on and copy the name from its sender line. No line, no name: "unconfirmed".
- "The user" in your prompt is who runs the portal. It is not the sender of a given message;
  several people use the same portal, and orchestrators relay for each of them.
- An orchestrator's message `for <name>` is that person's request through the orchestrator. Say
  so ("lifted at Lothsahn's request, via his orchestrator"), not as though they wrote it to you.
- A release hold, a lift, a merge override and a "skip this check" carry the most weight: when the
  sender is unconfirmed, don't act on them. Ask first.
- When you find a wrong attribution, correct the record where it was written (the PR description,
  the ledger note) and say in your report what it said and what it says now.
