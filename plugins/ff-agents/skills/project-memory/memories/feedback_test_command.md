---
name: Use standard test commands
description: Run tests via the MCP bridge (run_tests/get_test_job, pinned instance); the file-trigger channel is retired as a routine path
type: feedback
originSessionId: a8d2c0b7-ad63-4462-9b55-1fc0db52e2a7
---
Run tests through the **MCP bridge**: pin this project's instance (`set_active_instance` on the
`Name@hash` whose `path` is under the working dir — see `mcpforunity://instances`), start with
`run_tests` (EditMode `FFEditorTests` by default), and poll `get_test_job`. Trust ONLY that
job's result. Do NOT invent custom shell polling loops.

**Why:** As of 2026-07-08 CLAUDE.md makes MCP the required path and RETIRES the
`touch run-tests-fast.trigger && bash wait_for_test_results.sh` file-watch channel for routine
test runs (it's superseded by `run_tests` and was masking MCP-bridge outages). The old lesson
still holds in spirit: a test path that hangs/times out usually means the editor or bridge is
wrong, not that the tooling needs replacing — surface it, don't paper over it.

**How to apply:** Use `run_tests`/`get_test_job`. If the MCP bridge isn't up, STOP and tell the
user (see [[feedback-mcp-bridge-down-stop]]) rather than falling back to the trigger. The
file-trigger channel survives only inside the paired determinism-audit scripts; the clone
recompile in those flows now goes through the bridge too (pin the clone instance, `refresh_unity`).
