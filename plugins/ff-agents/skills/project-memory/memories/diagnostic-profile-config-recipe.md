---
name: diagnostic-profile-config-recipe
description: "The .ff-local-automation.json shape for a DIAGNOSTIC capture (PlayerCombatDetail etc.): verification-v2 schema, ushort heartbeat window, positive event/byte limits, finite dwell timeout, ≥1 surface — each omission is a distinct 'audit-config-invalid' phase error. Detail rows are plain [DeterminismAudit] lines; diagnostic reports carry a Fingerprint record EVERY heartbeat; the continuous verdict script rejects any window containing the host's recovery record — diff Fingerprint fields directly."
---

# Diagnostic-profile capture: the config that actually launches (2026-09-12, 069)

Four launches failed one field at a time (`.ff-local-automation-status.json` → `"Phase": "error"`,
`audit-config-invalid … error=…`; the player process stays alive in that state — kill it before
relaunching). The shape that works, on top of a verification config:

```
"AuditCaptureProfile": "diagnostic",
"AuditVerificationSchema": "verification-v2",      // continuous v3 is verification-only
"AuditDiagnosticEpoch": 0,                          // 0 = any epoch
"AuditDiagnosticStartHeartbeat": 0, "AuditDiagnosticEndHeartbeat": 65535,   // ushort, end >= start
"AuditDiagnosticSurfaces": ["PlayerCombatDetail"],  // >= 1, valid NetworkDeterminismAuditSurface names
"AuditMaxEventsPerSurface": 200000, "AuditMaxBytesPerSurface": 134217728, "AuditMaxDiagnosticBytes": 536870912,  // all > 0
"AuditDwellReleaseTimeoutSeconds": 7200             // unlimited (0) is allowed only with v3-continuous
```
(`NetworkDeterminismAuditCapturePolicy.cs:300-370`.) Surface names: the `NetworkDeterminismAuditSurface`
enum (`…Detail`); `PlayerCombatDetail` is change-triggered + hb%60 cadence
(`DeterminismFingerprintSystem.cs:263-272`); `ProjectilePipelineDetail`/`ShipCombatPipelineDetail`
record only hb ≤ 16 after a load.

**Reading the reports.** Detail rows are plain `[DeterminismAudit][Heartbeat N][Epoch E][role] … ->
PlayerCombatDetail … details=…` lines, NOT `# audit-record-v1` JSON — grep them. A diagnostic report
has a `Fingerprint` audit-record EVERY heartbeat (the runtime detector samples every 8), so the first
differing heartbeat is exact. `scripts/continuous_determinism_verdict.py` (and `cpcompare.py` on top
of it) returns `evidence-invalid` for ANY window that contains the host's `ContinuousCritical`
DesyncRecoveryAttempt record, even when the window ends at the verdict heartbeat — to find the forking
surface, load both reports' `Fingerprint` records and diff their `fields` dict per (epoch, heartbeat)
directly (the r9 `combatdiff.py` pattern). A kicked client writes its report automatically under
`…/Never Games/finalfactory/DeterminismAudit/network-determinism-audit-<runId>-<legId>-client.log`;
`ffauto:audit.write` is refused once the client is back in the menu.
