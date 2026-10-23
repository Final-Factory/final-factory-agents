---
name: research-the-route-before-you-say-cant
description: "Before an agent (an orchestrator included) tells a person something can't be done, or asks them to do a step themselves, it researches the route (the tool's own docs, the harness's skills and briefs, the machines and the sessions already signed in on them, the tools it and the workers have) and then tries the work or files it for an agent that can. Only a concrete blocker reaches the person, with its evidence, together with the smallest step only they can take (a login, a password or 2FA code typed by them, an approval, a design decision). An orchestrator's own limits (no shell, no browser) are not the system's: it files the work instead of saying can't. Ben corrected this twice: w934/w935 (close Unity on his m5) and w1268/w1287 (the Factions design doc in Claude Design). A route on a person's computer drives only the windows the agent opened, never their Claude desktop app or other open apps (w1287: \"WHY IS IT POKING AROUND IN MY CLAUDE DESKTOP APP\")."
date: 2026-10-14
---

# Before you say "can't" or "you do it", research the route, then try it or file it

**Rule.** Before you tell a person that something can't be done, or ask them to do a step themselves:

1. **Research the route.** The tool's or product's own docs and its import, export and API paths; the harness's skills
   and your brief (editor-ops, the ops worker, the vault); the machines FF Factory runs on and what is already signed
   in there (a person's browser and desktop apps on their own computer, the vault's accounts, `gh`, Steam, FFBox); the
   tools you and the workers have (shell, ssh through the ops worker, browser or computer-use automation, the
   `mcp__machine__*` tools). Write down what you found and where.
2. **Then try it, or file it.** Do the step if your tools reach it. If they do not, file it as work for an agent whose
   tools do: a worker on the machine where the session is signed in (`request_work`, or a `decide_work` note to the
   requester's orchestrator for the ops worker). An orchestrator has no shell and no browser by design; that is the
   orchestrator's limit, not FF Factory's, and its answer is a filed request, never "I can't".
3. **Only a concrete blocker reaches the person**, after the try: what blocked (a login wall, a captcha, a permission
   prompt, a refusal), its evidence (the error text, a screenshot, the doc that says so), and the smallest step only
   they can take: type their own password or 2FA code, click a permission prompt on their own computer, approve, decide
   a design question, confirm money. Say what you will do once they have done it, and declare the wait
   (`waiting_on_person`; [a wait on a person is declared](a-person-wait-is-declared-not-polled.md)).

The limits that stand: never handle, type or ask for someone's password, 2FA code or token; publish, share or spend only
as the rules allow; the reserved acts (deleting, app settings and deploys, releases) stay the person's. A rule that
reserves a step is a reason to ask; "I have no tool for it in this chat" is not.

Never a person's step at all, whatever the research says: closing, opening or restarting Unity (a person's editor on a
main clone too), git commands, copying files or saves, installers and daemon updates
([a wait on a person, first section](a-person-wait-is-declared-not-polled.md), w855, w935).

**Why.** Ben corrected the same mistake twice.

1. **2026-10-10, w934/w935: "close Unity" handed to Ben.** Worker b384063a found Unity open on Ben's m5 main clone and
   stopped with "What Ben needs to do: close Unity... then tell me", git commands included. Ben: "Dude, why are you
   telling me to close Unity? You can close Unity. There's tons of instructions on how to manage Unity instances. I
   can't believe I'm still having to tell you this." The route was in editor-ops all along (save the scenes, quit the
   editor through the bridge or `osascript`, do the work, reopen it).
2. **2026-10-14, w1268/w1287: "I can't create a Claude Design project".** On 2026-10-13 Ben asked w1268 (the
   Multiplayer Factions plan) to "make a Claude design that shows me the plan"; the worker made a self-contained HTML
   file instead. His orchestrator then told him twice that it could not (w1288's brief quotes it: "I can't create a
   Claude Design project ... You can upload the HTML file into it yourself"; w1287's brief: "no agent can sign in to
   claude.ai"). Nobody had looked at what was already there: Ben's m5 runs FF Factory workers, and his browser and
   Claude desktop app are signed in to claude.ai on it. Ben, 2026-10-14: "I want the html design doc in a Claude design
   document for ease of viewing and sharing. I already asked for this." Only then was it filed as w1287, to research
   Claude Design's import routes and try them on the m5 through its signed-in session, stopping with a screenshot at a
   login wall. **How it ended:** the w1287 worker first stopped at a locked screen and at "/design-login cannot run in
   this non-interactive session" and declared both as Ben's steps. Ben: "YOU CAN USE CLAUDE DESIGN FROM CLAUDE CODE".
   The route was a pty: an interactive `claude` under `expect`, `/design-login`, Authorize in a signed-in browser window
   the worker opened, then DesignSync wrote the HTML into a new project (project-memory
   `claude-design-from-a-headless-worker`). A tool's "needs an interactive session" means start one in a pty; it is
   not a person's step.

Both times the agent's own reach was taken for the system's reach, and the person got the work back. lothsahn's
correction of w847 (2026-10-10: "don't ask ben to run installers. Update your instructions. Stop doing that.") was the
same kind, for a machine step.

**How to apply.**

- **Scan before you send.** Any reply, report, brief or `still open:` line with "can't", "cannot", "no agent can",
  "not possible", "you can ... yourself", "you'll need to", "manually", "<Name> needs to" or "what <Name> needs to do":
  each one carries the route you researched (the sources, by name), the try or the filed request (its wNNN, with what
  it is), and, if a blocker is left, its evidence and the one smallest step. Without those, it does not go out:
  research, then try or file.
- **A brief for such work** says "research the route, then try it", names the machine and the signed-in session to use,
  the hard limits (credentials, sharing, money), and what to bring back if blocked: the blocker, a screenshot, the
  route found, the smallest step for the person (w1287's brief is the model).
- **An orchestrator** answers "can you put X into Y?" with a filed request, never with "I can't" from its own toolset.
  The request is cheap; the person asking twice is not.
- **A real "no"** (the product has no such feature, the docs say so) is a sourced claim: quote the doc and its date, and
  offer the nearest route that works.

The checklist lines: [done](../checklists/done.md) item 8, and "Reports and briefs" in [SKILL.md](../SKILL.md).

## Drive only the windows you opened (w1287, 2026-10-14)

**Rule.** On a person's own computer (Ben's m5, a lothsahn machine), computer-use and browser automation touch only:

- windows and tabs **you opened yourself** in this request (`open -a Safari <url>`, a browser you launched), and
- your own tools (Claude Code's DesignSync, `gh`, the `mcp__machine__*` tools, a pty session you started).

Never click, type or scroll in a window the person had open: their Claude desktop app (its chats, threads and
Code sessions), chat and mail apps, their editors, terminals, the FF Factory dashboard tab, a browser window they
were using. That holds when that app is the only one signed in to the service you need. Then you find another route
(a browser window you open, where the session also lives; Claude Code's own tool for the product), or you stop and ask
for the smallest step.

**Why.** w1287 (2026-10-14, putting the w1268 Multiplayer Factions design doc into Ben's Claude Design). Chrome on the m5 was
signed out of claude.ai, so the worker went to the Claude desktop app, which was signed in as Ben. Ben was using it at
the time, with a live thread running. The worker switched it from Code to Chat mode and opened the sidebar's
More menu twice, looking for Design. Ben: "WHY IS IT POKING AROUND IN MY CLAUDE DESKTOP APP". Two better routes were
there all along. Safari, in a window the worker had opened itself, turned out to be signed in to claude.ai. And Claude
Code reaches Claude Design directly (Ben: "YOU CAN USE CLAUDE DESIGN FROM CLAUDE CODE"; the recipe is project-memory
`claude-design-from-a-headless-worker`). The worker put the app back to Code mode with one click and reported each click.

**How to apply.**

- **Before the first click**, write down the app (bundle id) and the window id you opened, and pass that same
  `--window-id` to every `orca computer` call. `list-windows` first: a window that was there before you started is not yours.
- **A signed-in session in someone's app is not an invitation.** Try a browser window you open (`open -a Safari <url>`
  opens a new tab in a window you can then own; check each browser, since sign-in differs: on the m5 Chrome was signed
  out and Safari signed in), then the product's own CLI or Claude Code tool, then the smallest step for the person.
- **If you touched a person's window**, put it back as it was (compare against your first screenshot) and report
  every click and what it changed. Don't read or publish anything of theirs you saw (chat titles, threads).
- **At the end**, close what you opened except what the person should see (the project tab), and say which windows
  you closed and which you left open.

The checklist line: "Drive only the windows you opened" in [SKILL.md](../SKILL.md), "Reports and briefs".

## Drive only the player you launched (w1856, 2026-10-23)

**Rule.** A built player you send input to, screenshot or record is one **you** launched in this request, named by the
pid `player_slots.py launch --detach` printed. Its agent channel is that pid's own `AgentControl/session-<pid>.json`,
written after the launch: `python scripts/nightly/player_slots.py mine --one` (game repo) prints it, from your session's
leases. Never the newest file in `AgentControl/`, never "the newest FinalFactory process": every player on the computer,
any worker's, writes into that one folder, and the newest is whoever started last.

**Why.** Worker c28c5061 (w1767/w1768, BEAST, 2026-10-23) found "its" player by taking the newest agent session file and
sent its input to another worker's player on the same machine. Ben's request (w1856): "Make the drive-game /
agent-control tooling bind to the player the worker itself launched (by pid or slot), never the newest session file".
BEAST ran 7 workers at once that morning (portal journal, 09:56 UTC); two players starting minutes apart is the
normal case, not a corner. w1232 had
already lost runs to a stale file of a dead player whose pid Windows reused.

**How to apply.**

- Keep the pid from your launch's JSON (`{"pid", "slot", "agent_session"}`); pass it to everything: `ff-agent --pid`,
  `record_clip --pid` (or `--player`, which now asks `player_slots.py mine`), `read_os_cursor.ps1 -PlayerPid`.
- Lost it? `player_slots.py mine` lists yours (FF_SESSION_ID's leases) with each one's session file, or `stale_session_file`
  when the file there predates the player. Several: `--one --pid <n>`. None: launch one; do not borrow one.
- A player a person or another worker started is theirs, like a window they opened (the section above).
