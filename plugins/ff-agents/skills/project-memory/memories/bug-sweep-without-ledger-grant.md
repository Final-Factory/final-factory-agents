---
name: bug-sweep-without-ledger-grant
description: How a bug-sweep worker maps every #bug-reports thread to its request and every FFBox desync report to its cause without a ledger-read grant or ffbox_activity
metadata:
  type: reference
---

# A bug sweep without a ledger grant (w1907, 2026-10-23)

A sweep worker ("triage the reports since X and fix every clear bug") often has no
ledger-read grant (`read_work all` is refused) and no `list_work` or `ffbox_activity` tool.
It can still cover the whole window:

**Discord threads → requests.** The intake's hourly coverage pass (w1783) writes each result to
the portal journal. `mcp__machine__portal_logs` with `source: journal`, `grep: "bug thread"` and
`since: <window start>` returns:

- `bug threads: coverage since <date>: N thread(s), M owned, K unowned`, one per pass;
- one line per thread that was unowned on that pass, with the channel, thread id, title,
  opened and last-active times, and `filed as wNNN` when the intake filed it.

The threads between two passes are the new ones. On 2026-10-23 that gave all ten threads in w1907's
window (w1876–w1882, w1896–w1898) and the one still unowned (a design question Ben had answered
"Leave it"). A request your brief names can be read with `read_work id`; one it does not name
cannot, so match it to a PR with `gh pr list --search "wNNN OR <thread id>"`.

**Crash, desync and hang reports.** `mcp__machine__list_ffbox_files` with `what: reports` and
`since` lists them with their session, correlation id and the FFBox conversation that diagnosed
each. Read one diagnosis per session (`fetch_ffbox_report` with `diagnosis: summary.md`) rather than
one per report: a single co-op session sends dozens of reports. Before you treat an undiagnosed
fork as a game bug, check the `[mods]` section of that report's `.txt` (`fetch_ffbox_report` with
`file`). On 2026-10-23 every one of about 85 desync reports came from players running the
third-party "Cruiser combat expansion" mod, the late forks with `forkedSinceLoad=False` included,
so none of them was a game bug. Reports that came from the lab (`nightly-solo`, `-ffDebugHang`,
`[LocalMultiplayerAutomation]`) say so in their logs.

**Unmerged `ffbox/*` branches.** Look each one up on master
(`git merge-base --is-ancestor`, `git log --grep`): a worker often lands the same fix through its
own PR (FFBox d1210 → #2313, d1202/d1207 → #2267).

**FFBox "busy".** `fetch_ffbox_report` can answer `busy` for several minutes, even for a 500-byte
file. Wait about three minutes (`python3 -c "import time; time.sleep(180)"`) and try again. Don't
poll it in a tight loop.

**Ships in.** The last build's commit is the newest `bundleVersion` change in
`ProjectSettings/ProjectSettings.asset` (`git log -G bundleVersion`). Test each fix's merge commit
against it with `git merge-base --is-ancestor`.
