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

### Exact fast-suite selection when the exposed `run_tests` is Unity Pipeline

The Unity Pipeline package's `run_tests` command accepts only `filter` and `filter_type`; it
collects matching test names by case-insensitive substring. `assembly_names` is not a command
argument there, and `filter: "FFEditorTests", filter_type: "assembly"` also selects
`FFEditorTestsSlow`. Do not treat that route as an exact fast-suite run or edit the package
(FinalFactory `Library/PackageCache/com.unity.pipeline@58c16695e488/Editor/Commands/TestCommands.cs:22-29`,
`Editor/Testing/PipelineTestRunner.cs:596-606`).

For an exact remote fast suite, use the project-scoped Unity CLI's `eval_file` to invoke the
public MCPForUnity API directly. The file calls
`MCPForUnity.Editor.Tools.RunTests.HandleCommand` with `mode: "EditMode"`, an
`assemblyNames` `JArray` containing only `"FFEditorTests"`, and an `initTimeout` appropriate
to the editor's startup; synchronously await the returned job-start payload. Extract its
`job_id`, then poll `MCPForUnity.Editor.Tools.GetTestJob.HandleCommand` with that `job_id` and
`includeFailedTests: true` until terminal. This path passes the exact `assemblyNames` array to
Unity's `Filter.assemblyNames` (FinalFactory
`Library/PackageCache/com.coplaydev.unity-mcp@7b7db7b31f4e/Editor/Tools/RunTests.cs:47,71-95`,
`Editor/Services/TestRunnerService.cs:188,226-234`).

Use the pinned MCP job result as the verdict. Never use the shared
`…/LocalLow/Never Games/finalfactory/TestResults.xml` to infer another editor's result.

**Why:** As of 2026-07-08 CLAUDE.md makes MCP the required path and RETIRES the
`touch run-tests-fast.trigger && bash wait_for_test_results.sh` file-watch channel for routine
test runs (it's superseded by `run_tests` and was masking MCP-bridge outages). The old lesson
still holds in spirit: a test path that hangs/times out usually means the editor or bridge is
wrong, not that the tooling needs replacing — surface it, don't paper over it.

**How to apply:** Use `run_tests`/`get_test_job`. If the MCP bridge is unavailable, report it and
perform the targeted recovery in [[feedback-mcp-bridge-down-recover]] and `editor-ops` rather than
falling back to the trigger. The file-trigger channel survives only inside the paired
determinism-audit scripts; the clone recompile in those flows now goes through the bridge too
(pin the clone instance, `refresh_unity`).
