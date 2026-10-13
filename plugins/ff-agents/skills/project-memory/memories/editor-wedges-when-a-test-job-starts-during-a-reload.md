---
name: editor-wedges-when-a-test-job-starts-during-a-reload
description: "A sandbox editor stops answering (MCP 'Command TCS timed out' in a loop, ~0 CPU) when run_tests is called right after refresh_unity or while a script edit is reloading the domain; compile, wait until the state is ready, read the console, only then start the job; restart is the cure"
metadata:
  node_type: memory
  type: project
  modified: 2026-10-13T20:00:00Z
---

**Lesson (w1227, 2026-10-13, beast slot1, Unity 6000.3.19f1, MCP for Unity stdio).** Three times an editor stopped
answering for good: `refresh_unity ... wait_for_ready` returned, `run_tests` (or a Bash call that edited a `.cs` file the
editor then noticed) followed at once, and every later call timed out; `Logs/sandbox-editor.log` filled with
`Command TCS timed out (N consecutive)` and `Suppressed duplicate command resent on a new connection`. Waiting did not
help; `mcp__machine__unity restart` (force) did, and the next start was clean.

What worked, each time, in this order:
1. Finish every file edit first. An edit made after `refresh_unity` starts a second reload under the test job.
2. `refresh_unity` (force, scope all, compile request, wait_for_ready), then wait about 40 s and read
   `mcpforunity://editor/state` until `advice.ready_for_tools` is true and `compilation.is_compiling` is false.
3. `read_console` for `error CS`; fix and go back to 1 if there is one (a job started on a broken assembly is the usual
   wedge).
4. Only then `run_tests` with `test_names`, and `get_test_job` with a wait. The first call after a restart needs
   `set_active_instance` again.

A build (`build_player.sh`) needs the editor stopped, so end every editor session with `mcp__machine__unity stop` before
starting one, and a killed `build_player` leaves an orphan batch Unity for ~10 minutes (`unity clear_batch` says why it
waits; stop the parent bash first).
