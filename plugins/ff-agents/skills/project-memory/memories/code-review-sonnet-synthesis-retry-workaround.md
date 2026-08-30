---
name: code-review-sonnet-synthesis-retry-workaround
description: code-review-sonnet's synthesis stage can fail 5/5 retries validating its own decisions schema — the generated workflow script lives per-session, not in final-factory-agents, so synthesize by hand from the journal instead
metadata:
  type: project
---

The `code-review-sonnet` workflow's synthesis stage was seen failing schema validation on its
`decisions` field 5/5 retries, 3× in one day. This is NOT a fixable file in this repo: the
workflow is a per-session generated script (under
`~/.claude/projects/<project>/<session>/workflows/scripts/code-review-sonnet-wf_*.js`), not a
source file under `final-factory-agents/`, and inspection of several generated instances shows
the schema DOES declare `required: ["summary", "decisions"]` with `decisions` as an array — so
the failure is the synthesis subagent not returning data that satisfies that schema (e.g. a bad
finding index), not a genuinely missing field.

**How to apply:** if a synthesis stage exhausts its retries this way, do not chase a "fix the
schema" dead end — read `<transcriptDir>/journal.jsonl` for the stage's actual finder/verifier
outputs and synthesize the ranked findings report by hand instead of relying on the synthesis
agent's structured output.
