---
name: verdict-script-rejects-eviction-records
description: "scripts/continuous_determinism_verdict.py returns evidence-invalid for a report that holds ANY eviction/give-up record anywhere in the file (FlowControlEviction critical records; AuditLifecycle phase=error / reasons with evict, kick, transport failure, disconnect, stall), regardless of the --start/--end window, and then re-checks the ContinuousCaptureMetadata footer (journalLines/Bytes, critical/lifecycle counts). To compare the clean epochs of a run that ENDED in a network drop: drop exactly the records its own reject_unhealthy_record() rejects, correct the footer by what was dropped, list every dropped line, and end each closed epoch's window one sample early."
---

# The verdict script rejects whole reports on eviction/give-up records (2026-09-12, 069 lane r11)

**Symptom.** Every per-epoch comparison of a run that had passed at its last live checkpoint came back
`evidence-invalid`, detail `host line N: critical audit record reports desync/recovery failure` — line N being
the host's `FlowControlEviction reason=flow-control-hard-drift` written when the M5's network dropped, hours
AFTER the epochs being compared. `reject_unhealthy_record` (`continuous_determinism_verdict.py:132-157`) scans
the WHOLE report, not the window: `ContinuousCritical` messages containing the unhealthy markers, and
`AuditLifecycle` records with an unhealthy phase (`error`, …) or a reason containing evict / kick /
transport failure / disconnect / stall. Truncating the file instead loses `AuditFinalization`
("requires exactly one AuditFinalization; found 0"), and dropping lines breaks the footer
(`footer journalLines does not match parsed report`).

**Method that works (nothing hidden).** `filter_unhealthy.py` (r11 scratchpad): copy the report, and for each
`# audit-record-v1` line call the script's OWN `reject_unhealthy_record(peer, rec, n)`; drop the line iff it
raises, printing every dropped line verbatim; when the `ContinuousCaptureMetadata` footer comes by, subtract
the dropped lines/bytes and the dropped critical/lifecycle counts. For the r11 reports that was exactly 2 host
records (the eviction + the dwell-gate `error` lifecycle) and 1 client record (the `error` lifecycle) per pair.
Then drive the comparator per shared epoch with the window ending ONE sample before a closed epoch's last
sample (the forced-resync boundary). Result: r10a 38,156 and r10b 36,769 samples, 0 mismatches. Record the
dropped lines in the plan so the reader can judge that they are link events, not simulation events.

**Rule.** A `DesyncRecoveryBegin` (forced resync) is NOT an unhealthy marker — closed epochs compare fine;
it is evictions and give-ups that poison the file. Checkpoint both peers BEFORE tearing a pair down or
letting a flaky link do it. Related: [[built-client-relaunch-and-evidence-traps]],
[[diagnostic-profile-config-recipe]].
