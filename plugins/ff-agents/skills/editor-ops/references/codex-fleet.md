# Codex fleet operations

The main Codex task owns design, the queue, final verdicts, commits and pushes. Local native
children own bounded implementation or lookup legs. SSH runs commands on the other machines;
a native child is not a remote worker merely because its prompt names M3 or BEAST.

## Routing

| Work | Codex model / effort | Role |
|---|---|---|
| Orchestration and determinism decisions | gpt-6-astra / driver-selected | parent |
| Designed implementation | gpt-5.6-sol / medium | implementor |
| One focused lookup | gpt-5.6-luna / low | scout |
| Broad source exploration | gpt-5.6-terra / low | explore |
| Fully specified mechanical edits | gpt-5.6-terra / medium | mech-executor |
| Independent requested review angle | gpt-5.6-terra / high | reviewer |

Claude keeps its own role models. The game repo's `.codex/agents/*.toml` adapters carry Codex
settings; a plugin reload does not prove an already-running task has reloaded role definitions.
Inspect the callable role. If it is stale, give a native child a fresh bounded brief with explicit
model/effort and the role's full guardrails. Do not accept silent inheritance of the premium model.
Full-history forks may disallow model overrides in the active runtime; use a fresh brief then.

The repo's `Documentation/Crown-Jewel-Surfaces.md` remains binding. No remote shell, role choice,
or tool translation widens an implementor's ownership. Native workers are direct children. Remote CLI workers are separate processes owned directly
by the same driver and may not spawn children. The driver counts BOTH kinds against one fleet-wide
cap of four active agents including itself, records them in the queue, and reserves capacity before
launching. Only the driver commits or pushes.

## Fleet checked on 2026-09-05

| Machine | SSH route from M5 | Checkout | Use |
|---|---|---|---|
| M5 | local | `/Users/benryding/nevergames/FinalFactory` | driver; editor verification when idle |
| M3 | `ssh m3` (user benryding) | `/Users/benryding/nevergames/FinalFactory` | macOS peer and bounded workers |
| BEAST | `ssh beast` (user rydin) | `C:/Users/rydin/nevergames/FinalFactory` | Windows player builds and audit sweeps |

The M5 SSH configuration maps the older LAN addresses to these Tailscale names. Verify with
`ssh -o BatchMode=yes -o ConnectTimeout=10 <alias> hostname`; do not diagnose a sandbox DNS denial
as a dead machine. Follow the active host's approval policy for network access.
All three had Codex CLI 0.153.4 and ChatGPT login; M3 and BEAST completed explicit Sol-medium
read-only smoke requests. These are dated observations, not permanent availability guarantees.

Before each lane, read the machine's branch, HEAD, working changes, existing job state and editor
state. One writer/build/editor owner per checkout. Never sync C# into a checkout while another
job owns its editor. Use an isolated checkout based explicitly on `origin/develop` for concurrent
code work. Do not reset or clean shared state to manufacture parity.

`scripts/fleet-sync.sh` in the game repo fast-forwards the fleet and checks exact HEAD parity.
Read it before use; verify each remote command's exit status, not just its final printed SHA.
BEAST normally receives a Git bundle because its game-repo GitHub credentials are unavailable.
M3 commands need `zsh -lc` for the Node/Codex PATH. Windows commands with quotes should be written
to a task-specific `.ps1` or `.sh` and transferred with scp; nested SSH quoting is fragile.

## Remote Codex workers

Prefer native local roles unless remote compute or an OS-specific task justifies a remote agent.
For a remote worker, stage a bounded prompt on that machine, then use Codex's own CLI. A typical
Git Bash/macOS command is:

```sh
codex exec -C /absolute/checkout -m gpt-5.6-sol \
  -c model_reasoning_effort=medium --json \
  -o /absolute/job/final.txt - < /absolute/job/prompt.md > /absolute/job/events.jsonl 2>&1
```

Use native Windows paths under PowerShell and file-based input instead of complex inline prompts.
The prompt must include the implementor policy, owned files, design, required evidence, no child
spawns, no commit/push, preservation of other workers' changes, and editor ownership. `codex exec`
does not select the `implementor` role just because the model is Sol. Explicit model and effort are
mandatory; the remote user's default may still be Sol/xhigh. Do not reuse the old
`~/ff-worker/run-leg-local.sh`: it invokes `claude -p` and reads Claude credentials.

Keep a foreground job attached to a tool session that the driver can poll. Record job ID, PID,
HEAD, model, log path, output path and exit code. Retain `thread.started.thread_id` for a deliberate
`codex exec resume <id>` if needed; never resume an arbitrary latest task. Bounded status waits
must expose failure, completion and required input. A scheduled monitor is appropriate only when
continued monitoring was requested; use Codex's automation tool, not a Claude `Monitor` command.
A child cannot finish by promising to watch a job later. The parent owns collection and reporting.

## Unity and proof

Unity MCP works in Codex. Discover `mcpforunity://instances`, match the exact checkout path and
pin it; then run editor preflight. Tool availability is session-specific. On M5, the 2026-09-05
session successfully pinned `FinalFactory@d91200fa` at the expected Assets path and queried idle
state. Do not copy that instance ID into other checkouts. The preflight found Burst disabled on
M5; it was enabled before further verification. M3 preflight passed with Burst enabled and idle.

Register the local stdio server with `codex mcp add UnityMCP -- <absolute-uvx> --from
mcpforunityserver==10.0.0 mcp-for-unity` only if no matching server is configured. Match the
installed Unity package version and verify the real editor connection. Machine-specific executable
paths belong in local configuration, not a shared Mac path committed for Windows.

For a remote editor use its local worker's MCP connection, or the project-scoped
`scripts/unity-cli.sh ... --project-path <absolute-checkout>` over SSH when the driver has no remote
MCP tool connection. Explain the channel choice. Keep its structured recompile/test result and
verify a fresh compilation, Burst drain and imports. Never infer compilation from a green test or
clear dirty verification state on a failed refresh. The editor-ops skill has the full ritual.

No play-mode automation on M5 while Ben is using it unless he authorizes that run. Read
`pmset -g batt` before a long lane; on battery below 25%, checkpoint and follow the low-battery
workflow. Do not replace a failed or unrun witness with a previous sweep's success.
