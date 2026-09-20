---
name: continuous-capture-for-long-acceptance
description: "Use verification-v3-continuous from startup for long acceptance: v2 stops after 16384 samples and appends legacy rows that the strict parser rejects."
---

# Long acceptance needs continuous capture from startup

Use `AuditCaptureProfile: verification` with
`AuditVerificationSchema: verification-v3-continuous` symmetrically on all peers.
Remove diagnostic-only fields when switching profiles. Configure before the first retained
record; `NetworkDeterminismAudit.ConfigureCapture` rejects switching an active capture to
continuous. Preserve a live baseline and require the strict comparator to accept the actual
Unity reports before a long run.

`NetworkDeterminismAudit.RecordVerificationSample` caps non-continuous capture at 16384 samples
or 120 MiB. Checkpoints do not reset it. In 074 t9 this lost all fingerprints around printer
placement while runtime desync verdicts continued. Continuous mode appends to a disk journal
and bypasses that memory cap; check storageFaulted and overflow metadata in every checkpoint.

`BuildReportSnapshot` appends the legacy RecentEvents ring only for non-continuous reports.
The strict `continuous_determinism_verdict.py.records` rejects any non-typed line, including
legitimate load diagnostics from that ring. Do not weaken the parser or call an invalid report
a pass. Diagnostic captures still use verification-v2 and require their dedicated row diff.

Existing tests cover 16385 retained records in
`NetworkDeterminismAuditReportTest.ContinuousVerificationProfile_RetainsRecordsBeyondLegacyLimits`
and the parser's `test_streams_more_than_legacy_16384_sample_cap`. Synthetic parser tests do
not replace the live Unity-report-to-parser baseline.
