---
name: say-what-an-id-is
description: "Every id in a message for a person (a request id like w293, a PR number, a commit, a session or worker id, a sandbox name) is followed by what it is, in plain English, every time it appears."
date: 2026-10-03
---

# Say what an id is, every time

**Rule.** When a report, TL;DR, summary or message meant for a person mentions a request id
(w293), a PR number (#972), a commit, a worker or session id or a sandbox name, say in plain
English what that thing is, beside it: "w293 (stopping people from chatting with the dispatcher)",
"PR #972 (the fix for lost saves on rejoin)". Every time it appears, not just the first.
The id stays: it is the label the person can search for. The words are what they read.

**Why.** Ben, 2026-10-03: "i am a human so i dont know what identifiers like w293 refer to, you
can say the label like that but also remind me in english what its referring to. remember this."
Reports from workers and orchestrators had become strings of w-numbers, PR numbers and short
shas that only the agents who filed them could decode.

**How to apply.**

- Request: id plus its goal in a few words. PR: number plus what it changes. Commit: short sha
  plus its subject, or "the merge of <PR>". Worker or session: its id plus what it works on.
  Sandbox: its name plus what is in it or who uses it.
- Repeat the words when the id comes back later in the same message. A reader who skips to the
  last paragraph still has to understand it.
- A list or table of ids gets a short description column or clause per row.
- Applies to anything a person reads: final reports, TL;DRs, PR descriptions, commit bodies,
  Discord posts, a relay of a `[dispatch]` or `[intake auto-closed]` message to its person.
  Agent-to-agent briefs may keep bare ids, as long as the receiving agent can look them up.
- Before sending, scan the text for every `w\d+`, `#\d+`, 7-40 hex chars and sandbox or worker
  names, and check each one has its words beside it.
