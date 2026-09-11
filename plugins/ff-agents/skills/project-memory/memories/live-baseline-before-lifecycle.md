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

Manual checkpoints are not the final shutdown barrier. Release the owned dwell and teardown
gates on both machines, then confirm BOTH bootstraps have reached `report-written` and copy/hash
those automatic reports before stopping either player. In the September 10 tutorial, both manual
reports were safe, but the host was stopped after only its own automatic publication. The client
was still waiting at teardown and recorded `sessionEnded=disconnected from host`, making the
bootstrap-final verdict invalid. A worker being "capture ready" does not prove its bootstrap
finished. Keep the host alive until the client publication is positively observed.

A valid 506-frame temporal episode in the earlier run captured inventory/background instead
of miners: passing timing gates does not prove the subject is framed or its motion reviewed.
Inspect the actual frames before making a visual claim. Do not bypass browser policy when a
local Watch page is blocked; static frame inspection cannot replace playback for smoothness.

Check full-frame geometry too. `UnityVisualEpisodeCompositor` formerly passed a 960x540 target
straight to `CaptureScreenshotIntoRenderTexture` while the live view was 2560x1382; the episode
contained only the lower-left crop. Capture into the native viewport first, then bilinear-scale
into aspect-preserving review bounds, and encode using the returned texture's actual dimensions.
Game commit `7a7a0749f` corrects that path and tests source/output dimensions. Inspect a new built
player recording before accepting the visual fix; the old episode also failed cadence/overhead
gates, and correcting its crop does not prove those separate limits now pass.
