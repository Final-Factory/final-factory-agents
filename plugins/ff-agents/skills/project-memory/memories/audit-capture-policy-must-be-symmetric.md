---
name: audit-capture-policy-must-be-symmetric
description: "A diagnostic audit profile on the HOST config alone is refused at pairing ('Audit capture policies differ' — NetworkDeterminismAuditCapturePolicy.IsSymmetricWith): every peer's .ff-local-automation.json needs the identical diagnostic block. The block that launched three peers (074 t8), what it costs (~435 KB/s host log under CensusDetail, ~55 min to the byte cap, dwell expiry THROWS), why cp3.sh answers evidence-invalid on such a leg, and that the CensusDetail anchor closes at the FIRST recovery — so time the recovery you want detailed first."
---

# Audit capture policies must be symmetric across peers (074 t8, 2026-09-19)

**Refusal.** `NetworkDeterminismAuditCapturePolicy.IsSymmetricWith`
(`Assets/Scripts/FFCore/Network/NetworkDeterminismAuditCapturePolicy.cs:432-463`) compares the
canonical policy identity of host and joining client; a mismatch is the session error
`Audit capture policies differ ('…' vs '…')`. A diagnostic profile on the host config only never
pairs. Put the SAME diagnostic block on the host config AND every client config (BEAST, M3).

**The block that launched** (on top of a verification config; see
[[diagnostic-profile-config-recipe]] for the field rules):

```
"AuditCaptureProfile": "diagnostic", "AuditVerificationSchema": "verification-v2",
"AuditDiagnosticEpoch": 0, "AuditDiagnosticStartHeartbeat": 0, "AuditDiagnosticEndHeartbeat": 65535,
"AuditDiagnosticSurfaces": ["CensusDetail"],
"AuditMaxEventsPerSurface": 2000000, "AuditMaxBytesPerSurface": 1500000000, "AuditMaxDiagnosticBytes": 2000000000,
"AuditDwellReleaseTimeoutSeconds": 7200
```

**Costs and traps.**
- The host terminal log grew ~435 KB/s under `CensusDetail` (t8: 211 MB) — about 55 minutes to
  the 2 GB diagnostic byte cap. Plan the leg inside the dwell window: the dwell timeout EXPIRING
  throws in the bootstrap and ends the session with an error (2 h here).
- The diagnostic anchor latches on the first block after the LAST join and CLOSES at the first
  recovery. Every recovery after that has NO detail rows (t8's T111 fork at ep4/ep5 has none).
  Run the recovery whose detail you need FIRST; use the editor-pair hook
  ([[editor-pair-per-heartbeat-census-hook]]) for post-recovery epochs.
- On such a leg `cp3.sh`/`cpcompare.py` answers `evidence-invalid` ("line N is not a typed audit
  record") because the detail rows are plain lines, not typed records. That is not a verdict about
  the peers: `fielddiff.py` per epoch over the checkpoint reports is the evidence
  (every field equal on every shared heartbeat = clean).
