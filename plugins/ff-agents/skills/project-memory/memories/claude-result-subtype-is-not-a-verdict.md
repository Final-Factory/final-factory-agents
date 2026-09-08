# A Claude Code result envelope says `subtype: success` on a run that failed

Found on 2026-09-08, working out why an ffbox review turn told pull request 505 "the run
failed: success".

**The mechanism.** The last `{"type":"result"}` record of `--output-format stream-json` is the
run envelope, and `subtype` there describes how the CLI's own agent loop ended, not whether the
run worked. It stays at its default `"success"` on a run the SAME envelope flags as an error.
The real ending is spread across three other fields:

```json
{"is_error": true, "terminal_reason": "api_error", "api_error_status": 429,
 "subtype": "success", "result": "You've hit your session limit · resets 2:50am (UTC)"}
```

`result` also stops being an answer on such a run and becomes the error text, which is the
matching trap on the other side of the same object: anything that posts `result` as the agent's
reply will publish "You've hit your session limit" as though the agent had said it.

**Why it bites.** Every reasonable-looking reading is wrong. `subtype or error` returns
"success". `if subtype == "success"` says the run was fine. Nothing raises, nothing logs, and
the exit code — which is nonzero and correct — sits right next to the contradiction, so what
reaches a person is a sentence in two halves that disagree. In ffbox it reached both the reply
posted to the pull request and `turn.error`, the column `ffwatch status` and the box page
print, because two call sites made the same reading independently.

**What to read instead.** `is_error` first, then `terminal_reason` (`api_error` and friends)
with `api_error_status` for the HTTP status, and only then `subtype` — and treat a `subtype` of
`"success"` as the ABSENCE of a detail rather than as one. In ffbox that is
`result_failure_detail()` in `ffbox/ffwatch.py`, which both readers now share; put a new reader
through it rather than reaching into the dict again.

**How to spot it fast.** The run's own `out/result.json` is kept next to the stream:
`~/ffbox-state/conversations/<id>/runs/<run>/result.json`. A failure whose text names a limit,
a 429, or an API error, sitting under `"subtype": "success"`, is this. A session limit hit
mid-run is a normal ending on a busy box, not an exotic one — plan the words for it.

Related: [[ffbox-installs-as-one-service]], [[feedback-publish-harness-changes-to-ff-agents]].
