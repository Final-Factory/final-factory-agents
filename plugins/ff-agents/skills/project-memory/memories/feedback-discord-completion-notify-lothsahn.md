# Notify Lothsahn when a repository task finishes

Standing user feedback (Ben, 2026-08-02): when an agent finishes a Final Factory repository
development task, keep Lothsahn in the loop with an **extremely brief** Discord update.

## Completion rule

- After implementation and verification are successfully complete, post one single-sentence FYI
  in Discord `#dev-chat` and include `@lothsahn` so it expands to a real ping.
- Use the authenticated repository CLI from the FinalFactory checkout:
  `python3 scripts/discord/ffdiscord.py post dev_chat --text "@lothsahn <very brief description>"`.
- If commit, push, PR, merge, or deployment is part of the task's requested completion state, post
  only after that publication step succeeds. Otherwise post after the verified local result.
- Batch related implementation/test/documentation substeps into one task-completion note. Do not
  ping for every test leg, progress update, quick answer, partial result, failed run, or blocked
  attempt.
- Keep it genuinely terse: what finished and, when useful, one commit/PR identifier. No technical
  wall, status template, or request for action unless Ben separately asked for one.
- If the Discord CLI, credentials, channel access, or post fails, tell Ben the exact failure and do
  not claim Lothsahn was notified.

Ben's standing instruction above supplies the user authorization required by the Discord workflow
for this narrow completion-notification case. It does not authorize unrelated questions, replies,
announcements, or posts to other channels.
