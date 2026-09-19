---
name: bridge-drops-main-instance-during-editmode-runs
description: "The Unity MCP bridge loses this project's editor instance for ~30-45 s at the start of EVERY EditMode test run and after every play-mode exit (the domain reload); `get_test_job`/`refresh_unity` then error 'instance not found' while the run continues -- the job survives, so wait ~45 s, re-read `mcpforunity://instances` (the port can flip 6401 <-> 6400) and poll the SAME job id. With two editors open, this project's log is `Editor-prev.log` when the clone launched later (the newer editor takes the `Editor.log` name); verify compiles from the right file."
---

# The bridge drops the main instance on every EditMode run (2026-09-16)

**Signature.** `run_tests` returns a job id, then the next `get_test_job` (or any tool call) answers
`Unity instance 'FinalFactory@…' not found. Available instances: ['FinalFactory_clone_0@…']`. The
editor is fine (pid alive, tests running); the test-run domain reload disconnects the bridge for
~30–45 s. The same happens after `manage_editor stop` and after a forced recompile.

**Rule.** Never treat "instance not found" right after a run/reload as a wedge. `sleep 45` (background),
re-read `mcpforunity://instances`, re-pin if the port flipped (6401 → 6400 seen), then poll the SAME
`job_id` — the server-side job persists and reports the finished result (a 4,258-test suite polled
this way five times in one session). Only escalate to editor recovery
([[unity-mcp-registration-check]], editor-ops) if the instance is still absent after ~2 minutes AND
the editor process is not advancing its log.

**Which log.** Unity names the log by launch order: the LATER-launched editor writes `Editor.log` and
the earlier one keeps its renamed handle, `Editor-prev.log`. With the ParrelSync clone launched after
the main editor, this project's compile results (`Reloading assemblies after…`, `error CS…`,
`===== LOAD PROFILE`) are in `~/Library/Logs/Unity/Editor-prev.log`; `Editor.log` is the clone's.
Check the file's mtime against the action you just took before trusting either
([[verify-compile-dll-string-check]]).

**During a LONG suite it drops repeatedly, and a blip can even answer `Unknown job_id` (2026-09-19,
074).** A 4,288-test run (~4 min of runner time, ~6 min wall) dropped the instance three times; one
`get_test_job` in the middle answered `Unknown job_id`, yet the SAME job id answered `succeeded` with
full counts a minute later — the blip was the bridge, not the job. Readiness signal that works:
`~/.unity-mcp/unity-mcp-status-d91200fa.json` freshly written with `"reloading": false` AND its
`unity_port` accepting a TCP connect (python socket), then `set_active_instance("<port>")`. Batch the
readiness wait and the MCP poll in SEPARATE turns — a poll issued in the same batch as the wait fires
before the port is back. `execute_code` also times out ("Timeout receiving Unity response") on any
call longer than ~2 min (a Mac player build); the call keeps running inside the editor — judge it by
its marker file, never by the timeout ([[judge-a-build-by-marker-and-children-not-editor-cpu]]).
