---
name: a-fix-pr-names-its-discord-report
description: "A PR that fixes a Discord report carries the report's own link before it merges, `Discord: https://discord.com/channels/<guild>/<thread>` for a thread or `.../<guild>/<channel>/<message>` for a message in a channel; FFBox tells the reporter from that line and from nothing else. A request closed as already fixed by another PR names it: `RESOLVED: already fixed by PR #N`."
date: 2026-10-05
---

# A fix PR names its Discord report

**Rule.** Before a pull request that fixes a bug someone reported on Discord merges, its description
has one line per report, on a line of its own:

- a thread (#bug-reports, a forum): `Discord: https://discord.com/channels/<guild id>/<thread id>`
- a message in a channel (#ask-assistant, a chat): the original message's own link,
  `Discord: https://discord.com/channels/<guild id>/<channel id>/<message id>`

When you close an intake request because another, already merged PR fixed it, name that PR in the
marker: `RESOLVED: already fixed by PR #1076`.

**Why.** FFBox posts the "Fixed in PR #N, coming in version X and later." notice to the reporter,
and it finds who to tell in two ways only: the `Discord:` lines of the merged PR (ffbox
`scripts/ffwatch.py` `PR_DISCORD_LINE_RE`, `pr_discord_links`, anchored to a whole line) and FF
Factory's ledger answer for a thread Max escalated. On 2026-10-05 w436 (FFBox conversation 692, a
player in #ask-assistant whose range rings darkened the screen) was closed as already fixed by #1076,
which shipped in Build 78, and the player was never told: #1076 came from another request and had no
`Discord:` line for that message, and the ledger answer carried no PR (fixed in FF Factory by w480).
Lothsahn: put the original message link in the PR so FFBox can report it.

**How to apply.**

- Copy the link from the report itself (the request's source URL, the escalation brief's `Discord:`
  line), not a link to a reply or a later message.
- Several reports, several lines, at most ten. A link quoted mid-sentence is not read.
- Pushing straight to develop with no PR: put the line in the commit body.
- Never post the "fixed" notice yourself: FFBox does, once, from these lines.
- `RESOLVED: already fixed by PR #N` with exactly one PR number in the line: FF Factory looks up that
  PR's merge and release and the escalated thread hears "Fixed in PR #N, coming in version X".

The checklist line: [merges](../checklists/merge.md).
