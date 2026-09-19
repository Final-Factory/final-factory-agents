---
name: stale-clone-editor-invalidates-pair-evidence
description: "A ParrelSync clone editor keeps running the assembly it last compiled; after a fix commit it showed a census fork that was purely its pre-fix code (074 T108, 2026-09-19). Before ANY editor-pair evidence after a code change, prove the fix TYPE exists on BOTH editors (Type.GetType != null via execute_code, ScriptAssemblies DLL mtime newer than the fix), force `refresh_unity scope=all mode=force compile=request` on the clone (scope=scripts answered refresh_triggered:false and rebuilt nothing), then preflight until the Burst queue drains."
---

# A stale clone editor invalidates pair evidence (074 T108, 2026-09-19)

**What happened.** The fix `ConstructionSiteKnnReconciliationSystem` landed at 07:16 UTC. A
per-heartbeat census-hook pair ([[editor-pair-per-heartbeat-census-hook]]) run at 07:57 showed the
clone (client) with `+KnnFleetEntity` on the loaded site on EVERY heartbeat of the join and both
recovery epochs — exactly the pre-fix symptom — and it was read as "the fix does not run on the
client path". It did not run because it did not EXIST there: the clone's
`Library/ScriptAssemblies/FFSpaghetti.dll` was compiled at 06:41 UTC, and
`System.Type.GetType("Serialization.ConstructionSiteKnnReconciliationSystem, FFSpaghetti")` from
`execute_code` on the clone returned null. The clone editor never recompiles on its own; it had
been idle since before the fix. Same family as the stale-assembly ops-hash check before a paired audit: `recompile_status` and a green suite say nothing about which build a peer runs.

**Rebuilding it.** `refresh_unity scope=scripts mode=force compile=request` (issued while the clone
was still leaving play mode) answered `refresh_triggered:false, compile_requested:true` and the
DLL mtime never moved. `scope=all mode=force compile=request` answered `refresh_triggered:true`
and rebuilt it within a minute. Right after the rebuild `editor-preflight.sh` fails with
`burst=True queue=1` — loop it until `preflight-pass`. The clone's bridge port flips on the
reload (6400 → 6401 seen); re-read `mcpforunity://instances`.

**Rule.** Before trusting ANY difference between the two editors of a pair after a code change:
1. `execute_code` on BOTH: `Type.GetType("<ns>.<FixType>, <Assembly>") != null` and print the
   assembly `Location` + `File.GetLastWriteTimeUtc` — it must be newer than the fix commit.
2. If not, `refresh_unity scope=all mode=force compile=request` on that editor, wait for the DLL
   mtime to move and `reloading=false`, re-check the type.
3. Preflight both until Burst is drained, THEN run the pair.

With the fresh clone the same join probe showed the loaded site with NO `KnnFleetEntity` — the
fix works on the client path; the earlier pair had measured the wrong build.
