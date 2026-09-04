---
name: wire-surface-adds-have-three-mirrors
description: Adding a fingerprint surface to the determinism wire touches THREE mirrors, not two — missing the JSON verification projection passes every text-channel check while the strict cross-machine verdict rejects the artifact
metadata:
  type: project
---

Adding a fingerprint surface to the wire has THREE mirrors, not two: (a)
`DeterminismStateFingerprint.WireSurfaceNames` + the text Fingerprint line, (b)
`scripts/determinism_audit_verdict.py` `FINGERPRINT_ORDER`, and (c) the JSON verification
projection `NetworkDeterminismAuditVerificationSample.ToAuditRecordLines` / `FingerprintFields`
— the record the 045 strict cross-machine verdict actually reads.

055 T055 (movers/vision, wire v17) updated (a) and (b) only, so every verification-profile
report written from 2026-08-29 to 2026-09-04 lacked the two fields and the strict verdict
rejected the artifact ("Fingerprint field shape differs … missing=[movers, vision]"); the BEAST
mode-2 sweeps never noticed because `compare_determinism_reports.sh` reads the text channel.
Fixed `8927ce94c` with a mirror test
(`NetworkDeterminismAuditReportTest.VerificationSample_FingerprintRecord_CarriesEveryVerdictFieldInWireOrder`).

**How to apply:** after ANY wire-fingerprint change, run the cross-machine leg — it is the only
consumer of the JSON projection, and a green mode-2 sweep says nothing about it.
