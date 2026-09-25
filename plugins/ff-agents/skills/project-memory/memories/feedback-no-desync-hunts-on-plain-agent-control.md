---
name: feedback-no-desync-hunts-on-plain-agent-control
description: Lothsahn 2026-09-25 — never hunt, force or probe desyncs in a game launched with only plain -ffAgentControl; that is a player session and its desync/crash reports upload to ffintake on ffbox, so the desync would be triaged twice. Hunt through the harness (-ffAutomationRole), the editor, -ffAgentControlDev or honest play instead
metadata:
  type: feedback
---

**Rule (Lothsahn, 2026-09-25, binding):** when you go looking for desyncs — determinism probing,
forcing a fork (`desync.inject`), soak-playing to see if one appears — do it in a session the game
marks as ours. Never do it in a player launched with only plain `-ffAgentControl true`.

**Why:** since game commit `c6f88fa99` (develop, 2026-09-25) desync and crash reports upload to
ffintake whenever a person plays and has opted in, on ANY build (release, the Steam multiplayer
closed beta, a local dev build). The game cannot tell a player's own agent (the shipped agent kit,
plain `-ffAgentControl`) from one of ours, so that tier counts as a player and uploads. A desync our
agent is already investigating then lands in ffbox too and gets triaged a second time.

**Sessions that never upload** (`DiagnosticsConsentPrompt.IsUnattended`,
`ReportUploadQueue.UploadsSuppressed(bool, bool, bool)` in the game repo):
- the Unity editor (unless a test sets `AllowInEditor`)
- `-batchmode`
- play-mode test runs (`StartController.IsTesting`)
- harness peers: anything launched with `-ffAutomationRole` (every `run_*_audit.sh`, the playtest
  built-player recipe)
- `-ffAgentControlDev true`
- honest-play legs (`-ffHonestPlay true`, `HonestPlay.IsArmed`)

**How to apply:**
- Hunting desyncs: use the paired harness, the editor, or add `-ffAgentControlDev true` (or
  `-ffAutomationRole`) to the launch line. Honest-coop sittings are already covered by
  `-ffHonestPlay true`.
- Testing `-ffAgentControl` itself (the player tier) is fine. If a desync happens there by
  accident and uploads, a little overlap is acceptable; just don't make desync hunting the point of
  a plain `-ffAgentControl` session.
- Opt-in still applies: nothing uploads unless that machine's player agreed to share diagnostics.

Related: [[feedback-beast-work-goes-through-a-sandbox]].
