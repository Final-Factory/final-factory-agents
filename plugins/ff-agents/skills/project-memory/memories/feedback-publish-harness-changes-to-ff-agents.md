# Publish harness changes and lessons to ff-agents proactively

Standing user feedback (Ben, 2026-08-04): "always update the ff agents repo whenever you feel
it necessary or are making changes to the harness."

## Rule

- Whenever a session changes how the shared harness works — a skill's procedure, a subagent
  role, a drive/probe recipe, an operational workflow — or produces a durable, reusable lesson
  (a gotcha, a refuted assumption, a recovery path that worked), publish it through the
  `publish-skills` workflow **in the same session**, without waiting to be asked.
- "Feel it necessary" is delegated to the agent's judgment: if the next session (on any
  machine) would benefit from knowing it, publish it. Err toward publishing.
- This strengthens the repo CLAUDE.md rule that all durable lessons go through
  `publish-skills` — it removes the need for a per-instance prompt from Ben. Machine-local
  memory and game-repo docs remain the wrong place for shared tooling knowledge.
- Batch the session's harness lessons into one publish (one version bump) when they land
  around the same time; don't leave any behind unpublished. If a publish is blocked (marker
  missing, push failure), report it explicitly — a silently unpublished lesson looks identical
  to a published one until another machine acts on stale behavior.
