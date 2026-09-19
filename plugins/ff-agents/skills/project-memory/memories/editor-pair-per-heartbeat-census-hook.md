---
name: editor-pair-per-heartbeat-census-hook
description: "To see WHICH census row forks on a peer that gets kicked within ~13 heartbeats (a join or desync-recovery epoch), install an EditorApplication.update hook on BOTH editors of a ParrelSync pair before the client joins: it dumps CollectCensusRecords one TSV per heartbeat (hb ≤14 of every block, block = hb reset) and diffs pair by exact heartbeat. It survives play-mode entry because the project disables domain reload on play, needs no diagnostic profile, and captures post-recovery epochs the CensusDetail anchor never can. Named 074 T108 in one leg."
---

# Editor-pair per-heartbeat census hook (074 T108, 2026-09-19)

**When.** The `census` surface is red from hb 1 of a join or recovery epoch and the peer is kicked
by hb ~13, so no manual `execute_code` dump can land in time, and the CensusDetail diagnostic
window cannot capture a post-recovery epoch ([[census-fingerprint-surface-design]]). A solo
save→load probe ([[single-player-reset-probe-for-recovery-leftovers]]) is the cheaper first step
— run it first; the hook is for what solo cannot show (a client-shaped world).

**Recipe (main editor = host, clone = client, both `execute_code`, in EDIT mode, before writing
the client config).** One Roslyn script per editor: capture `role`, an output `dir`, `lastHb =
int.MaxValue`, `block = 0`; register `EditorApplication.update += hook` where `hook` (a) removes
itself when `dir/hook-stop` exists or after 40 min, (b) returns unless `Application.isPlaying`,
the default World exists, `GameMetaState.GameStarted` and the `Heartbeat` singleton is present,
(c) reads `CurrentHeartbeatFrame`, increments `block` when `hb < lastHb` (every join/recovery
resets hb to 0), (d) when `hb ≤ 14 || hb ∈ {40,100,300,1000} || hb % 500 == 0` reflects
`FFSystems.Multiplayer.DeterminismStateFingerprintJobs.CollectCensusRecords(em, true)` (internal
static; `CensusRecord` fields `Signature/Count/TypeNames` via NonPublic|Instance) and writes
`<role>-b<block>-hb<NNNN>.tsv` (`sig\tcount\ttypes`), all inside try/catch appended to
`<role>-hook.log`. Then: preflight both, host config (`SaveName` = the checkpoint, `Port 7777`,
verification profile, `ExitPlayModeOnComplete false`, long `PostConnectDelayMs`, empty
`PostReadyCommand`), wait for `waiting-host-peers-connected` with a fresh status mtime, drive the
host with `TryExecute`, write the client config, and force a recovery with `ffauto:desync.inject`
on the CLIENT (verdict at the next 8-hb sample, recovery ~1 s later). Diff `host-b<N+1>-hbXXXX`
against `client-b<N>-hbXXXX` per heartbeat (the host is one block ahead: its first block is the
pre-join load); a row-set diff that matches each one-sided signature to the signature sharing the
most types prints the leaking component by name.

**Why it works here.** `EditorSettings.enterPlayModeOptions = DisableDomainReload |
DisableSceneReload` in this project, so editor callbacks and statics survive play-mode entry
(that is also why the audit epoch counter continues across play sessions in one editor process).
The dumps are ~90 rows each; 14 per block costs nothing.

**What it found.** 074 T108: three injected recoveries with only BUILT stations were census-equal
on every dumped heartbeat, then a recovery served while a fresh Mining Station was UNDER
CONSTRUCTION differed from hb 1 by exactly one row: the `[OutOfPlay, ConstructionTaskData, …]`
site, +`KnnFleetEntity` on the client ([[loader-reinstantiates-prefab-baked-save-components-return]]).

**Traps.** The main editor's bridge port flips 6401↔6402 on every domain reload — re-pin by the
port in `~/.unity-mcp/unity-mcp-status-<hash>.json`, and never batch a `set_active_instance` with
an `execute_code` (the pin is session-global). Give every run its own `AuditLegId` (the auto-written
report cannot overwrite). A clone straight off a forced recompile forks on its COLD Burst cache even
after `preflight-pass` — see [[paired-leg-preflight-and-editor-wedges]].
