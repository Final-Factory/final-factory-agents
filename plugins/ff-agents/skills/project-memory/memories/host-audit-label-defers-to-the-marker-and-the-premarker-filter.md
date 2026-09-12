---
name: host-audit-label-defers-to-the-marker-and-the-premarker-filter
description: "The HOST's audit epoch label must advance only when its own SessionReset marker applies (c939c0858) — advancing it at AdvanceForReset put 'heartbeat 741 followed by 1' under one epoch and the comparator returned evidence-invalid; reports written by players built BEFORE the fix carry the old label, so drop the per-heartbeat records of an epoch that precede the counter's last backwards step (by record sequence, print every dropped line, correct the footer) before comparing."
---

# The host audit label defers to its marker; filter pre-marker records from pre-fix reports (2026-09-12, 069 lane r15)

- **The defect (found by the r15 join baseline, diagnostics only).** After `1bb8a9cb1` the host applies its
  session reset at its own `SessionReset` marker's stream position, but `SessionEpochTracker.AdvanceForReset()`
  still published the new label at once via `NetworkDeterminismAudit.SetSessionEpoch`. The host ran one more
  heartbeat (741) before the marker, so the report showed epoch 1 · hb 741 followed by epoch 1 · hb 1 and
  `continuous_determinism_verdict.py` said `evidence-invalid: host missing interior heartbeat after epoch 1
  heartbeat 741`. Fix `c939c0858`: `AdvanceForReset` only increments (`SessionEpochTracker.cs:22-26`); the
  label is set where the marker applies (`HeartbeatSystem.cs:552-568`, `SetSessionEpoch` at `:567`), exactly as
  `AdoptDeferringAuditLabel` (`SessionEpochTracker.cs:42-45`) already did for non-served clients. Pinned by
  `SessionEpochTrackerTest.AdvanceForReset_DefersTheAuditLabelToTheSessionResetMarker`.
- **Reports from players built before the fix are still comparable** — do not rebuild a live lane for a
  label defect. Per epoch, find the LAST backwards step of the Fingerprint heartbeat sequence; every
  per-heartbeat record of that epoch whose record `sequence` is lower than the restart group's is pre-marker
  → drop it (one host heartbeat per join). Print every dropped line in the report, and correct the footer's
  `journalLines` / `journalBytes` / `verificationSamples` so the verdict script's totals still reconcile
  (`r15/filter_premarker.py`, applied to the HOST copy only by `cp15.sh`; the client's label was already
  marker-driven). State the filter in any verdict you report — it is an identity-preserving edit, never a
  hidden one.
- The tell in general: a comparator "missing interior heartbeat" or "N followed by 1" inside ONE epoch label
  is a labelling fault, not a fork — check which peer's label moved before the marker.
- Related: [[session-reset-marker-and-the-three-peer-backlog-fork]], [[determinism-report-epoch-pairing]],
  [[verdict-script-rejects-eviction-records]].
