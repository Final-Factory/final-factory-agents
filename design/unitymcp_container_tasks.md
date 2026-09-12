# UnityMCP in the container: implementation tasks

Derived from `design/unitymcp_container_design.txt` (2026-09-11) after measuring feasibility on
the build server rather than reasoning about it. Read design section 1 before starting: four of
these tasks exist only because of what that probe found, and two of them exist because the first
probe was WRONG in a way worth not repeating.

Phases are ordered so that each one is verifiable on its own. A phase that cannot be checked is a
phase that is not done.

**Status, 2026-09-11: A to E are DONE and the offline suite is green; F is outstanding and the
feature is OFF in config until it passes.** An adversarial review of the design and of this file ran
BEFORE implementation and found five wrong claims and three ordering errors; the fixes are folded in
below and marked REVIEW. Two of them changed the implementation rather than only the text — where
`ffmcp stop` goes (C6) and never trusting the state file's pid (B8).

## Phase A — the image

- **A1** DONE. Add the two layers to `ffbox/Dockerfile` **before the `COPY` of the shell
  scripts** — REVIEW corrected "at the end": the script COPY is the last content layer, those
  scripts change most weeks, and every layer after a changed one rebuilds, so "at the end" would
  re-download a python toolchain on every commit touching `entrypoint.sh`. After the Claude/`gh`
  layers and the action cache, before the COPY:
  `curl -LsSf https://astral.sh/uv/install.sh | sh` with `UV_INSTALL_DIR=/usr/local/bin`, then
  `uv tool install --python 3.12 "mcpforunityserver==10.0.0"`, with
  `UV_TOOL_BIN_DIR=/usr/local/bin`, `UV_TOOL_DIR=/opt/uv/tools`,
  `UV_PYTHON_INSTALL_DIR=/opt/uv/python`, then `chmod -R a+rX /opt/uv`. The shared paths are not
  optional: a run drops to the workspace uid and has no `$HOME` to install into (the same reason
  `install-claude.sh` parks its binary in `/usr/local/bin`).
- **A2** DONE. Pin the version next to a comment saying WHAT it must match — the
  `com.coplaydev.unity-mcp` version in the game repo's `Packages/manifest.json`, 10.0.0 today —
  in the same shape as the existing `UNITY_IMAGE`/`UNITY_VERSION` lockstep note in
  `03-build.sh`. Design section 9.3 is the failure this comment is trying to prevent.
- **A3** DONE, and measured: `docker run --rm --network none --entrypoint mcp-for-unity
  ffbox:latest --help` prints usage, and so does the same run as `--user 1000:1000` (the uid a run
  drops to). `--network none` is the point — it is what proves the fenced class needs no new
  allowlist entry. REVIEW note: the fence argument only ever applied to `ffagent`; `ffdev` is
  `network: full` and could have installed at run time, so baking is justified by reproducibility
  and by not having two classes behave differently, not by the fence alone.
- **A5** DONE. The server version is recorded as an image LABEL
  (`org.finalfactory.mcp-server-version`), beside the runner/unity/gh ones, so the baked version is
  readable without starting a container.
- **A4** DONE. `sh ffbox/03-build.sh` on the build server: **14s** wall with the base cached, the
  new layer adding uv plus a python 3.12 toolchain and 40-odd wheels. The updater runs this on every
  pass, and at this placement (A1) it is cached unless the pin moves.

## Phase B — `ffbox/ffmcp.sh`, the supervisor

- **B1** DONE. `ffmcp start`: check the workspace has the package — REVIEW: in the real repo it is
  a GIT dependency resolved into `Library/PackageCache/com.coplaydev.unity-mcp@<hash>`, and
  `Packages/com.coplaydev.unity-mcp` does NOT exist (that was the probe project's embedded copy), so
  the glob is the case that matters and the test covers it — (design 9.4 —
  degrade instead of booting an editor that will never listen); `ensure_unity_license`; launch
  under `setsid`
  `unity-editor -projectPath "$WS" -executeMethod MCPForUnity.Editor.McpCiBoot.StartStdioForCi
  -logFile /dev/stdout` with `UNITY_MCP_ALLOW_BATCH=1` and all three telemetry kill switches
  (`DISABLE_TELEMETRY`, `UNITY_MCP_DISABLE_TELEMETRY`, `MCP_DISABLE_TELEMETRY`); **no `-quit`**.
  Idempotent: a second `start` while a bridge is up is a no-op that reports the existing port.
- **B2** DONE. Readiness is the log line `StdioBridgeHost started on port <N>` — **NOT** the
  `~/.unity-mcp/unity-mcp-port-*.json` registry file, which is written only when the default port
  is taken. Design section 1d: the first probe waited for that file and called a healthy bridge a
  failure after five minutes. Bounded by `ready_timeout_secs`; on timeout, stop what was started
  and report degraded.
- **B3** DONE. `ffmcp stop` kills the **process group** (`kill -- -PGID`), TERM then KILL, because
  `unity-editor` is an `xvfb-run` wrapper whose children survive a pid-targeted signal and go on
  holding the licence seat. `ffmcp status` / `ffmcp port` read the state file.
- **B4** PARTIAL, and left honest rather than guessed. `UnityLockfile` and the refusal string are
  both literals in `/opt/unity/Editor/Unity`, so `Temp/UnityLockfile` is very likely the path; the
  probe's failure to stat it proves little, because the workspace is a tmpfs inside the container.
  **Still to do in phase F**: `ls -la <projectPath>/Temp/` from INSIDE a container with an editor up.
- **B5** DONE as a conditional, per B4: `ffmcp stop` removes `Temp/UnityLockfile` only after it has
  killed the pid it started and that pid is gone — it removes the path if it is there and says
  nothing if it is not, rather than asserting the path exists. Never unconditionally: a lock whose
  owner is alive is telling the truth.
- **B6** DONE. State in `/ffbox/out/mcp/`: pid, pgid, port, phase, the editor log, and BOTH versions
  (editor package and server) so design 9.3's drift shows up in the spool rather than in somebody's
  memory.
- **B7** DONE. `ffmcp start` refuses unless `FFBOX_UNITY_MCP=1` is in the environment, which the
  task exports only for a class that enabled the bridge (design 13.2, now closed): an editor whose
  tools are not on the model's list is worse than no editor.
- **B8** DONE — REVIEW, and this one is a real hole the design had missed. `/ffbox/out` is a mount
  the AGENT can write, so `kill -- -PGID` read out of the state file there takes an editable file's
  word for what to signal. `ffmcp` now checks the recorded pid against `/proc/<pid>/cmdline` — it
  must be a Unity editor opened on THIS project — and refuses anything else. One pid, looked up
  because we were told about it: still no `pkill`, no `ps`, nothing hunted (which the E8 sweep
  forbids outright anyway).
- **B9** DONE — REVIEW. The port can MOVE: PortManager leaves 6400 only when something else holds
  it, which is what a domain reload can look like from the inside. `ffmcp` re-reads the LAST
  `StdioBridgeHost started on port N` line rather than trusting the recorded number, and rewrites
  the record when it has changed.

## Phase C — the harness

- **C1** DONE. `ffwatch.py`: `"ffmcp"` path in `DEFAULTS` beside `ffverify`/`ffplaytest`, the
  `FFWATCH_MCP` env override, the frozen-copy entry, and the mount at `/usr/local/bin/ffmcp` on
  **both** launch paths — REVIEW: those are **pool staging and cold launch**, not "staging and
  dispatch"; dispatch adds no mounts at all, which is exactly why a spare staged before this change
  never gets the mount and has to age out.
- **C2** DONE. `unity_mcp: {"enabled": false, "ready_timeout_secs": 600}` per agent class, with the
  per-class merge behaving like the existing clocks (`agent_secs` and friends) rather than as a
  flat box-wide key.
- **C3** DONE, and deliberately NOT by editing the box-wide constants — REVIEW caught that
  `CAPABILITY_TOOLS`/`CAPABILITY_ALLOWED` are box-wide and `capabilities_for` varied only by
  conversation KIND, so adding the tools there would have handed them to `ffagent` too.
  `capabilities_for(conv, ccfg)` now takes the class block and appends the MCP tools to **both**
  lists only when that class enabled the bridge. The `Workflow` precedent is the reason for "both",
  and it was measured: `--tools` alone leaves a `-p` run dying at a permission prompt it has nobody
  to answer.
  **A CURATED SUBSET, not all 46.** The server's full tool list was enumerated by asking the server
  itself (it lists tools with no editor attached). 16 are exposed — `execute_code`, `read_console`,
  `refresh_unity`, `run_tests`, `get_test_job`, `set_active_instance`, `manage_editor`,
  `manage_scene`, `manage_gameobject`, `manage_components`, `find_gameobjects`, `manage_asset`,
  `manage_prefabs`, `manage_camera`, `batch_execute`, `unity_reflect`. Left out: the
  script-mutation tools (Edit/Write are the channel a reviewer reads, and two ways to change one
  file makes a diff harder to account for) and the generation/import tools (they reach outside the
  fence, as a stall rather than an error). Enumerated rather than a server-wide wildcard, so the
  surface cannot grow silently when the package adds a tool.
- **C3b** DONE — REVIEW, the gap that made the whole thing inert: **the switch has to REACH the
  container.** `discord-task.sh` reads exactly one input, `job.json`, and nothing was putting the
  class decision in it. `build_job` now emits `"unity_mcp": {"enabled", "ready_timeout_secs"}`
  beside the capabilities, and the task exports `FFBOX_UNITY_MCP` / `FFMCP_READY_TIMEOUT` from it.
- **C4** DONE. Write the MCP config into the run's spool and pass `--mcp-config` plus
  `--strict-mcp-config` (so only ours loads). Server named **`UnityMCP`**, matching the
  `mcp__UnityMCP__*` names the ff-agents roles already use. Command: the baked
  `/usr/local/bin/mcp-for-unity --transport stdio`.
- **C5** DONE. `discord-task.sh`: `ffmcp start` **before the argv is built** — REVIEW sharpened
  this from "before `.agent-started`", which was true but not sufficient: the argv carries the tool
  list, `--mcp-config` and the prompt, and it is written BEFORE that marker. A boot after it would
  advertise tools with no server behind them, which is the opposite of the degraded-turn
  requirement. Being before the argv puts it before the marker too, so the boot is still inside
  `warmup_secs` and costs the model nothing. The workspace restore is already done by then on both
  routes — `entrypoint.sh` as root for a cold run, `pool-task.sh --resync` for a dispatched spare —
  which is exactly why the editor must not be booted any earlier (design section 3).
- **C5b** DONE. A degraded turn strips its own MCP tools: the container knows what the host could
  not, so when no bridge came up the argv builder drops every `mcp__` entry from both lists, skips
  `--mcp-config`, and the prompt says the bridge was requested and did not come up.
- **C6** DONE, and REVIEW moved it: `ffmcp stop` runs **the moment the agent's `wait` returns**,
  not merely before the harness's `ffverify`. Between those two points the task COMMITS THE TREE
  (`git add -A -- .`) and asks `run_changed_anything`; opening a Unity project reserializes assets
  (d133t5), so a live editor there would have its writes committed as the agent's work and would
  buy a fifteen-minute verification for a turn that changed nothing. Also in `_ffbox_finish` before
  the harvest, for a killed run, and once more in the verification block where it is now a no-op.
  Design 6a.
- **C7** DONE. The preamble tells the truth in both directions: whether the bridge is up (and on which
  port), that `run_tests` through the bridge is the test channel while it is up rather than
  `ffverify` (design 6c), that a degraded turn still has ffverify, and that **no GPU** means no
  timing claims.
- **C8** DONE. `ffverify` and `ffplaytest` check `ffmcp status` and exit 2 naming the fix when a bridge is
  live (design 6b). An error that says "run `ffmcp stop`, or use the MCP `run_tests` tool" beats a
  Unity log 4000 lines deep.

## Phase D — docs

- **D1** DONE. `ffbox/config.md`: both `unity_mcp` keys and the `ffmcp` path entry, in the same commit as
  the code — the project's standing rule for a change to the config's shape.
- **D2** DONE. `ffbox/README.md`: what the bridge is for, the serialisation rule, the degraded path, and
  the no-GPU limit, beside the ffverify/ffplaytest sections.
- **D3** DONE. `docs/docker-security-model.md`: design section 10's argument — that a container with bare
  `Bash` gains no reach from `execute_code`, that the bridge is localhost-only inside one namespace,
  and that the server makes no outbound calls — where the other measured non-boundaries live.
- **D4** The ff-agents skills that describe the container's Unity channels
  (`discord-dev-agent`, `discord-triage/reference.md`, `playtest`, `editor-ops`) learn that a
  container can now have a real bridge, and that the wrappers are preferred but not mandatory.
  Version bump, or interactive sessions keep reading the old text.

## Phase E — tests (`ffbox/test_ffwatch.py`, offline)

- **E1** Defaults: `unity_mcp` present, **off**, with the documented `ready_timeout_secs`.
- **E2** DONE. Off: no MCP tools in the recorded tool list and no `--mcp-config`. REVIEW: "no
  `ffmcp` invocation" was wrong and would have contradicted C6 — `ffmcp stop` is called
  unconditionally and is a no-op when nothing was started. The property is no `ffmcp start`.
- **E3** On: the config file is written with the baked command and the server named `UnityMCP`; the
  tools appear in **both** lists; `--strict-mcp-config` is passed.
- **E4** `ffmcp` against a **stub** editor: `start` gates on the log line and not the registry file;
  `status` reports the port; `stop` kills a recorded **grandchild**; a second `start` is idempotent.
- **E5** `ffverify`/`ffplaytest` exit 2 while a bridge is up, and the message names the fix.
- **E6** `discord-task.sh` stops the bridge before harness verification and logs it.
- **E7** A workspace with no MCP package degrades rather than booting an editor.
- **E8** `ffmcp.sh` joins the existing source-level sweeps: the named-container discipline check
  (no `docker kill`, no hunting for processes — `design/discord_persistent_design.txt` section 14
  rule 2) and the no-`/workspace` check.

All of phase E is DONE: 33 new checks across three suites, `sh ffbox/test.sh` green. E4 also
covers B8 (a forged pid in the state file is refused rather than signalled) and the real
`Library/PackageCache` glob from B1.

## Phase F — on the box (cannot be automated; record the evidence here)

- **F1** The **real FinalFactory boot time** to a live bridge. Design 2.1 — this is the number that
  decides whether `warmup_secs` is right, and nothing before this task knows it.
- **F2** A real tool call against a real world: `read_console`, then `execute_code` reading a
  singleton.
- **F3** A **recompile through the bridge** — does the domain reload keep the bridge, and does it
  keep the PORT (design 2.2 and 13.3)? If the port moves, the registry file becomes load-bearing
  after all and B2 needs a second signal.
- **F4** `run_tests` through the bridge on the real project, compared against `ffverify` on the
  same tree: same verdict, one editor instead of two.
- **F5** A turn that ends cleanly: no editor, no Xvfb, no licence seat held, no stale lock, and the
  harness's own verification ran normally afterwards.
- **F6** Memory with one editor per container held for a long turn (design 2.4).
- **F7** Only then: `unity_mcp.enabled` true for ffdev in the live config, and one real dev turn
  watched end to end. ffagent stays off.
- **F8** REVIEW, and the one that could still change the design's shape: **what does merely OPENING
  the real project dirty?** Boot FinalFactory through `ffmcp` on a clean tree, wait for idle, then
  `git status --porcelain`. C6 stops the editor before anything is staged, but if a boot dirties the
  tree every time, the turn's diff carries it anyway and the harvest needs a baseline taken after
  the boot rather than before the agent. Neither document has an answer for that yet.
- **F9** REVIEW: does the server need a writable `$HOME` when `claude` spawns it as the run user?
  `--help` does not exercise the `~/.unity-mcp` reads. Send it an `initialize` as uid 1000 with
  `HOME=/home/ffbox`.
- **F10** B4's leftover: `ls -la <projectPath>/Temp/` from inside a container with an editor up, to
  settle where the project lock actually lives.

## Not in scope

Two editors in one container (paired determinism work stays on real machines), replacing the
harness's own `ffverify` (design section 11), and any timing claim from a container with no GPU.
