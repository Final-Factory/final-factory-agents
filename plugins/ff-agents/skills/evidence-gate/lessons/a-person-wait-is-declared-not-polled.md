---
name: a-person-wait-is-declared-not-polled
description: "Never hand a person a step the harness's own tools (the ops worker, ssh to the machines) can do: an installer rerun or a daemon update is sent to the ops worker. A worker that needs a person to act (reboot, log in, decide, approve, hand over a secret) declares it with FF Factory's waiting_on_person tool, names who and what in its report and its 'wNNN: still open:' line, and ends its turn. It never polls for a person with wake_me: a pending check-in makes the ledger show the request Working."
date: 2026-10-08
---

# A wait on a person is declared, never polled

**First, check that a person is really needed (w855).** Never hand a person a step the harness's own
tools can do. A machine installer rerun (`--max-sandboxes N`), a daemon update, a reinstall or any
command on a machine goes through the ops worker (`ops_worker machine_update`, or `send`;
docs/ops-worker.md) or ssh, not to Ben or lothsahn. "Update the machines" means every machine's
daemon through it, installers included. lothsahn, 2026-10-10 (from w847, where the dispatcher asked
Ben to rerun biscuit's installer): "don't ask ben to run installers.  Update your instructions.
Stop doing that.  When we say update the machines, do the update, including installers if
necessary". A tool's refusal ("its sandbox count comes from its installer") points at the step to
send, not at a question. The dispatcher hands the step to the requester's orchestrator in a
`decide_work` note; an orchestrator calls the tool in any turn. A person is for what the rules
reserve (money, deleting, publishing, releases, app settings, a secret) or a physical act (reboot,
login). Only then declare the wait, below.

**Rule.** When only a person can move you on (they must reboot or log in to a computer, decide,
approve, hand over a secret), call `mcp__machine__waiting_on_person` with `who` and `what`, then end
your turn with a report that names the same person and action and carries a
`wNNN: still open: waiting on <Name> to <do what>` line. The ledger then shows the request
**Waiting on input (on <Name>)**. A `wake_me` check-in is for machines and jobs (CI, a build, an
import); you may set one as a fallback, but never instead of the declaration. Your next message
ends the declaration, so declare again if a person is still needed. A daemon too old to offer the
tool: say it in the still-open line ("(a person)", "waiting for Ben to …"); the ledger reads that
as a backstop.

**Why.** 2026-10-08 (w691, from w665, Ben's Mac GPU page fault): from 01:52 UTC worker d558ba14
needed Ben to reboot and log in to the m3 (FileVault). It set `wake_me` check-ins of 2 h and 6 h and
reported "w665: still open: m3 reboot and login (a person), …". The ledger counts a worker with a
pending check-in as Working, so w665 read Working for about 10 hours while nobody could act and Ben
did not know he was needed. Check-ins are Working on purpose (the worker comes back by itself); a
person does not come back because a timer fired.

**How to apply.**

- Before a `still open:` line that names a person, a computer's physical state or a login, the
  declaration comes first, then the report.
- Waiting on CI, a build, a lock or another request is not this: use the check-in or a
  dispatcher-set blocker (`decide_work block`). The test: would a timer change who must act next?
  If not, it is a person.
- Dispatcher and orchestrators: a worker's report with such a line and no declaration is a worker to
  correct, not a Working request to leave.
- FF Factory side: `docs/orchestrators.md`, "Waiting, Queued, Blocked" (`waiting_on_person`,
  `personWaitIn`).
