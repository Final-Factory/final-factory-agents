---
name: live-baseline-before-lifecycle
description: Preserve both paired baseline reports before destructive reconnect/load tests, and inspect temporal capture framing.
---

On 2026-09-09, the live powered-mining .11 test remained in epoch 1 through HB6187,
but deliberate client disconnect destroyed the bootstrap before client report publication.
The host report survived; that alone could not establish full cross-peer agreement.
The corrected replay finalized and copied both baseline reports before reconnect: all 25
fields were retained across 3212 shared heartbeats, only the documented same-peer raw inventory
layout differed, and the reconnect then had its own durable restored/failure verdict.

Close and compare the baseline first, then exercise lifecycle transitions. Preserve the full
window and distinguish runtime no-desync evidence from full fingerprint comparison.
A valid 506-frame temporal episode in the earlier run captured inventory/background instead
of miners: passing timing gates does not prove the subject is framed or its motion reviewed.
Inspect the actual frames before making a visual claim. Do not bypass browser policy when a
local Watch page is blocked; static frame inspection cannot replace playback for smoothness.
