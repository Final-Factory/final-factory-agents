---
name: never-hand-a-person-a-step-a-tool-can-do
description: "Never ask a person to run a step the harness's own tools can do: a machine installer rerun, a daemon update, a reinstall, a file copy or any command on a machine goes through the ops worker (ops_worker machine_update or send) or ssh, not to Ben or lothsahn. Before a question or a still-open line that tells a person to run something, check what the tools can do."
date: 2026-10-10
---

# Never hand a person a step a harness tool can do

**Rule.** Before you ask a person to run, copy, install, restart or check anything, look at what
the harness can do itself. On the machines that means the ops worker (FF Factory's `ops_worker`:
`machine_update` for a daemon update or an installer rerun such as `--max-sandboxes N`, `send` for
any other job it covers; docs/ops-worker.md) or ssh from a worker that has it. "Update the
machines" means update every machine's daemon through it, an installer rerun included. A person is
for what the rules reserve (money, deleting, publishing, releases, app settings, a secret, a
physical act such as a reboot or login), never for a command.

**Why.** lothsahn, 2026-10-10 (w855, from w847 raising biscuit to 3 sandboxes): the dispatcher set
the agent and editor limits, then asked Ben to rerun biscuit's installer with `--max-sandboxes 3`.
The ops worker (w597) could already ssh in and run it. lothsahn: "don't ask ben to run installers.
Update your instructions.  Stop doing that.  When we say update the machines, do the update,
including installers if necessary".

**How to apply.**

- A tool's refusal ("its sandbox count comes from its installer") is a pointer to the step, not a
  question: send the step to whoever can run it, with the exact command and flags.
- Dispatcher: hand the step to the requester's orchestrator in a `decide_work` note, naming
  `ops_worker machine_update` and its arguments. Orchestrators: call it, in any turn, for the
  person's own open request.
- Only when no tool can do it (a physical act, a login, a secret) declare the wait with
  `waiting_on_person` ([a person wait is declared](a-person-wait-is-declared-not-polled.md)).
