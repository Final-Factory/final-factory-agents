# Pull request feedback: implementation tasks

Derived from `design/pr_feedback_design.txt` (2026-09-09) after reading the paths it extends:
`ffwatch.py` (`poll_github`, `take_review_trigger`, `review_held`, `read_github_cursor`,
`start_github_poll`, `upsert_conversation`, `insert_message`, `pending_messages`, `claim_turns`,
`create_turn`, `mark_working`, `claim_ack`, `clear_ack`, `ack_payload`, `send_github`,
`build_job`, `job_message`, `render_prompt`, `render_review_prompt`, `run_classifier`,
`claude_hold`, `adopt_branch`, `demote_for_stranger`, `select_for_turn`, the `GitHub` client),
`ffwatch_schema.sql`, and `test_ffwatch.py` (the `#codereview` block and `MockGitHub`).

Effort: **S** under an hour, **M** an afternoon, **L** a day or more.

## Status: A through H implemented; I not run. The gate (E1, E2) was removed on 2026-09-10.

`design/github_pr_review_design.txt` is the sibling this reuses; where a task says "the same as
the trigger does", the trigger's own code is the reference, not this file's summary of it.

**A through H are implemented.** The whole `test_ffwatch.py` suite passes, including thirteen new
feedback tests covering H2-H15. **I is the live run and has not happened.** The trigger's first
live run reviewed master because two threads disagreed about a branch; assume this one has an
equivalent waiting and read the run's own `job.json` rather than its reply.

**The content gate is gone.** E1 and E2 shipped and were removed the same day, on Lothsahn's
call: every comment an operator leaves is now acted on. Design section 4 carries the reasoning --
the gate's two mistakes are different sizes, and the invisible one is dropping an instruction.
E3 step 5 went with it, along with `FEEDBACK_NONE_GATE`, `feedback_verdicts`, the prompt and
schema, and tests H5 and H6; `test_every_comment_an_operator_leaves_is_acted_on` replaces them and
asserts that nothing even asks a classifier. The operator check in E3 step 1 is NOT that gate and
stays: it is the fence, not a cost control.

What implementation changed, beyond the design:

- **The prompt sorts its comments by GitHub's timestamp.** The namespaced ids make the table's
  order group by source rather than by time -- a prefixed id casts to 0, so every comment left on
  the diff comes back ahead of every comment left in the conversation -- and "and the same in the
  other file" has to follow the comment it is about. One sort, in the renderer, rather than a
  different ORDER BY for one kind of conversation. The design says so now.
- **`render_feedback_prompt` is two methods, not one.** `render_github_prompt` decides what the
  turn is (a review, a batch of comments, or both) and does the render-time operator check;
  `feedback_prompt_parts` renders the comments. `render_review_prompt` split the same way, into
  `review_prompt_parts` plus a wrapper, so a mixed turn can carry both bodies with the harness
  note and the resume summary once, at the end. That tail is now `prompt_tail()`.
- **`dispatch_feedback` is the guarded caller, in one place.** E6 said "wrapped by its caller",
  and there are three callers. One method wraps `take_feedback`, logs, and settles the staged
  rows, so the three pollers cannot come to disagree about what a raised ingest leaves behind.
- **`iso_secs()`.** The quiet period compares GitHub's stamp against the clock, and this file had
  no ISO parser to do it with. It spells out the trailing `Z` rather than leaving it to
  `fromisoformat`, which only learned it in 3.11.
- **The worker-shape test had to move.** `test_the_merge_poller_is_not_the_review_pollers_passenger`
  asserted `except Exception` appeared exactly twice in `start_github_poll`. It is five now, and
  the test names all five steps and asserts the release runs after the three reads.

## A. Config

- **A1 (S). DONE.** Three keys under `github` in `DEFAULTS`: `feedback` (bool, default `true`),
  `feedback_quiet_secs` (`120`), `feedback_max_comments` (`25`). Comment each the way the block
  around them is commented -- what it is for, and what turning it off costs.
- **A2 (S). DONE.** `config.md`, a `### Pull request feedback` subsection beside `### #codereview`:
  what starts a run, whose comments count, the quiet period, the gate, what the 👀 means and
  which comments cannot carry one, and that there is deliberately no `feedback_pool`. CLAUDE.md
  requires this in the same commit as the shape change.
- **A3 (S). DONE.** Nothing to seed in `05-discord-setup.sh`. It seeds no `github` block at all --
  `trigger`, `review_pool` and `poll_secs` all come from `DEFAULTS` -- so these three do too.
  The task exists so the omission is a decision rather than a miss.

## B. Schema and message ordering

- **B1 (S). DONE.** `message.github_meta TEXT` in `ffwatch_schema.sql` and in `ADDED_COLUMNS`, so an
  existing database gains it on the next start. It holds a JSON object for a GitHub-sourced row
  and NULL for everything else: `{"kind", "path", "line", "hunk", "url", "review_id"}`, absent
  keys where the source does not carry them. Nothing else in `message` has anywhere to put a
  file and a line, and re-fetching them at prompt time would put a GitHub call inside
  `build_job`, which is synchronous and must work when GitHub is down.
- **B2 (M). DONE.** The ordering tiebreak. Add `MESSAGE_ORDER = "CAST(discord_id AS INTEGER), id"` and
  `MESSAGE_ORDER_DESC = "CAST(discord_id AS INTEGER) DESC, id DESC"` near the other message
  constants and use them at all ten `ORDER BY CAST(discord_id AS INTEGER)` sites
  (`resettle`, `pending_messages`, `build_job`, `render_summary`, and the six
  `DESC LIMIT` reads). A namespaced id casts to 0, so without this every inline comment in a
  conversation sorts equal and SQLite may hand them back in any order. It changes nothing for a
  Discord conversation, where the snowflakes are distinct.
- **B3 (S). DONE.** Update the `-- bug_report | suggestion | ask | mention` comment on
  `conversation.kind` and the `message.discord_id` comment in the schema file: that column now
  holds three shapes, and the UNIQUE index over it is why they are namespaced.

## C. The GitHub client

- **C1 (S). DONE.** `list_review_comments(since, per_page, max_pages, etag)` --
  `GET /repos/{repo}/pulls/comments?sort=updated&direction=desc&since=`. A direct sibling of
  `list_issue_comments`: same conditional GET on page one, same ceiling, same oldest-first
  return, same `NOT_MODIFIED`.
- **C2 (S). DONE.** Open pull requests. `list_closed_pulls` is already
  `GET /pulls?state=closed&sort=updated&direction=desc` with a client-side `since` watermark and
  a conditional GET; give it a `state` argument (default `"closed"`, so the merge poller is
  untouched) rather than writing a third copy. Its docstring says the `state=closed` choice is
  deliberate, so say there why `open` is now also asked for.
- **C3 (S). DONE.** `pull_reviews(number)` -- `GET /repos/{repo}/pulls/{n}/reviews`, returning
  `{id, user, state, body, submitted_at}` per review, shaped by a `review_facts`-style helper so
  a missing field comes back empty rather than absent. Drop `PENDING` and `DISMISSED` here, not
  at the caller.
- **C4 (S). DONE.** `react_to_comment(comment_id, content, kind="issue")`: `kind="review"` posts to
  `/repos/{repo}/pulls/comments/{id}/reactions` instead of `/issues/comments/{id}/reactions`.
  Keep it best-effort and keep the WARNING log -- a mark that cannot be placed must never cost
  the run it acknowledges.
- **C5 (S). DONE, then partly reversed 2026-09-10.** No merge and no approve method: the test
  asserts `merge` appears in no method name, and now that `approve` does not either. `resolve` was
  going to join them and did not — see J below. Resolving a thread is a claim about a
  conversation, not a change to the code or to whether it lands, and the two absences are about
  the latter.

## D. Ids, cursors and the pollers

- **D1 (S). DONE.** `github_message_id(kind, comment_id)` and `github_comment_ref(discord_id)`, one
  pair, module level. Bare digits for an issue comment, `rc:<id>` for an inline one, `rv:<id>`
  for a review summary. Every caller that needs to know which endpoint an id belongs to goes
  through the second one; nothing parses a prefix inline.
- **D2 (M). DONE.** `feedback_facts(kind, raw, number=None)`: one normaliser for the three payload
  shapes, answering `{id, number, author_id, login, body, stamp, path, line, hunk, url,
  review_id}`. The number comes from `issue_url` for a conversation comment, from
  `pull_request_url` for an inline one (both through `_issue_number_from_url`, which parses the
  last path segment and so serves both), and from the caller for a review summary. `hunk` is the
  tail of `diff_hunk`, capped -- a hunk is unbounded and the prompt is not. `in_reply_to_id` is
  deliberately NOT carried and the parent comment is never fetched: pulling it in would put a
  stranger's text into an operator's prompt through their reply to it (design section 3).
- **D3 (S). DONE.** Generalise the cursor file. `_read_cursor(path)` / `_write_cursor(path, since,
  seen, etag, held)`, with `read_github_cursor` / `write_github_cursor` kept as the trigger's
  wrappers so their callers and the existing tests are untouched. Two new paths in `state_dir`:
  `github.reviewcomments.json` and `github.reviews.json`. Both record the moment the box started
  watching on their first poll and answer nothing older, exactly as the trigger cursor does.
- **D4 (M). DONE.** `poll_github` stops dropping a non-trigger comment. An operator's comment that
  carries no trigger word is collected per pull request number and handed to `take_feedback`
  (E3) at the end of the pass, instead of falling through to `seen` unread. Two consequences to
  get right:
  - the `if not triggers: return []` early return has to become "no triggers **and** no
    feedback", or a box that configures the trigger away loses feedback with it;
  - a comment that matched a trigger word is a review request and is NOT also feedback.
- **D5 (M). DONE.** `poll_review_comments()`: the same walk over C1's endpoint, grouped by pull request
  number, handed to `take_feedback`. No `review_held` equivalent -- the hold is applied at
  release (F1), and reading a comment costs nothing worth holding.
- **D6 (M). DONE.** `poll_review_summaries()`: one conditional read of open pull requests (C2); for each
  whose `updated_at` is past the cursor, `pull_reviews(number)` (C3), keep the reviews submitted
  since the cursor whose `body` is non-empty, hand them to `take_feedback`. The cursor does not
  advance past a pull request whose reviews could not be read, for the reason
  `poll_github_merges` does not: `since` is a stop-walking watermark here, not a server-side
  filter.
- **D7 (S). DONE.** `start_github_poll` runs five things, each under its own `try`/`except` so one
  failure cannot silently stop another: `poll_github`, `poll_review_comments`,
  `poll_review_summaries`, `release_feedback`, `poll_github_merges`. Order matters only in that
  the release runs after the three reads, so a comment that arrives and ripens in the same poll
  is not held over for a whole minute.

## E. Ingest and the gate

- **E1 (M). REMOVED 2026-09-10.** `FEEDBACK_GATE_PROMPT` and its schema: given the pull request's title and the new
  comments, answer `{"verdicts":[{"id","act","why"}]}`, one entry per comment id. It is its own
  prompt -- the Discord gate's is about a player in a forum and none of its reasoning transfers.
  Say what "act" means: the comment asks for a change, an investigation or an answer about this
  branch. Say what it does not mean: acknowledgement, agreement, a note to another human, a
  restatement, "merging this".
- **E2 (S). REMOVED 2026-09-10.** `feedback_verdicts(pull, comments, key)`: one `run_classifier` call per pull request
  per poll, on `pick_claude_key()`, **failing open** -- an unreachable or off-shape gate marks
  everything actionable, the same direction `should_engage` fails in, and for the same reason.
  A missing id in the answer is actionable too.
- **E3 (L). DONE.** `take_feedback(gh, number, comments, agent_class)`, the whole ingest for one pull
  request's batch, in this order:
  1. Drop every comment whose author is not in `github_operators(cfg)`. Logged, never answered,
     never written down. This is the first half of design section 3.
  2. `pull_request(number)`; drop the batch if it is not a pull request or is not open, and
     refuse it if the head is a fork's -- the same two checks `take_review_trigger` makes,
     silently here because nobody asked for a run.
  3. `upsert_conversation("github:pr:<n>", kind=GITHUB_KIND, agent_class=review_pool)` and the
     `github_pr` / `github_base` update, exactly as the trigger does. Reuse it rather than
     copying it.
  4. `insert_message` per comment, **born gated** with `FEEDBACK_WAITING_GATE`,
     `routed_by="github_feedback"`, `discord_id` from D1, and the D2 facts as `github_meta` --
     which means `insert_message` gains a `github_meta=None` argument written in the same
     INSERT, beside `gate`, and for the same reason: a second statement is a second window.
     Born gated for the reason the trigger's row is -- `claim_turns` runs on the loop and this
     runs on a worker.
  6. `adopt_branch(conv_id, head, by=<author id>)` if the conversation has no branch. On a
     refusal, gate the surviving rows `feedback_refused` and post `reason` verbatim once
     (`refuse_review`'s shape, its own wording).
  7. `mark_working` per surviving comment, which queues the 👀 and sends it (F4).
- **E4 (S). DONE.** `routed_by="github_trigger"` on the review trigger's own row. It is NULL today,
  which works only because `select_for_turn` returns early unless something is routed `recent`.
  Naming it is what lets `render_prompt` tell the two kinds of message apart (F3).
- **E6 (S). DONE.** A batch whose ingest raises leaves no invisible rows. `poll_github` already wraps
  each comment and calls `settle_a_staged_trigger`; `take_feedback` gets the same treatment --
  wrapped by its caller, and any row still wearing `FEEDBACK_WAITING_GATE` for that pull request
  re-gated to `feedback_failed` with the exception on it. A gated row is one nothing selects, on
  a comment the cursor has already recorded as handled, so an ingest that dies half way would
  otherwise be a run that silently never happens. Nothing is posted: nobody asked for this run.
- **E5 (S). DONE.** Leave `demote_for_stranger`'s `github_pr` exemption in place and rewrite its comment.
  The reason it gives -- "no comment text is carried, not even the operator's" -- stops being
  true with this change. The reason it keeps the exemption is that a stranger's text is never
  written down (E3.1) and never rendered (F3), so there is no chain for a stranger to get into.

## F. The turn

- **F1 (M). DONE.** `release_feedback()`: for each conversation holding `FEEDBACK_WAITING_GATE` rows
  whose newest `created_at` -- GitHub's stamp for the comment, not the moment the poll saw it --
  is older than `feedback_quiet_secs`, and which has a branch on it, ask
  `claude_hold("review", fresh=True)`. Held: leave the batch gated and say so once through
  `log_hold`. Clear: `ungate_message` each row, guarded on the gate value the way
  `ungate_message` already is, and leave the turn to `claim_turns` on the loop's next tick.
  Creating the turn here instead would duplicate the one place that knows how, and would race
  the loop for no gain -- the branch is already settled, which is the only thing the trigger's
  own `create_turn` call was buying.
- **F2 (S). DONE.** `feedback_max_comments` is applied by F1, at the release: it ungates the oldest
  `feedback_max_comments` rows of a ripe batch and leaves the rest gated. They ripen again on the
  poll after this turn ends and become the next turn on the same conversation. Nothing is
  truncated in the prompt and nothing is claimed by a turn that will not read it -- which is what
  rendering only the first N would do, since `create_turn` claims every ungated message whether
  the prompt quotes it or not.
- **F3 (M). DONE.** `render_feedback_prompt(job, review)` and the fork in `render_prompt`. A turn's
  messages are split by `routed_by`: `github_trigger` rows get `render_review_prompt`'s
  instruction, `github_feedback` rows get the feedback section, and a turn holding both gets both
  in that order. A message whose `author_id` is not in `github_operators(cfg)` **at render time**
  is dropped, which is the second half of design section 3 and the half that matters. A
  `github_pr` turn with neither kind of row (an old conversation, whose rows predate `routed_by`)
  falls back to `render_review_prompt`, so nothing already in the database changes behaviour.
- **F4 (S). DONE.** `job_message` carries the parsed `github_meta` for a row that has one, so the
  renderer reads the file, line and hunk off the job rather than going back to the database.
- **F5 (S). DONE.** Nothing changes in `record_reply`, `capabilities_for`, `turn_trust`, `turn_venue`
  or the ffdev clocks. A feedback run answers on the pull request through the `github_pr` branch
  `record_reply` already has, composed by `compose_head` out of the verdict. `github_pr` is already operator-tier, private-venue and carries the `Workflow` tool;
  a feedback turn that does not run the workflow simply does not use it.

## G. The acknowledgement and the sender

- **G1 (S). DONE.** `ack_payload` for a `github_pr` conversation reads `github_comment_ref` and puts the
  endpoint on the payload (`pr_comment_kind`). It answers **None** for an `rv:` id: GitHub has no
  reactions endpoint for a review, so a summary body cannot wear a mark.
- **G2 (S). DONE.** `mark_working` and `claim_ack` both check for that None and do nothing rather than
  queueing a row the sender would have to reject at the wire. `mark_working` is already
  idempotent per message (`ack_pending_local_id`), which is what makes E3.7 safe to re-run.
- **G3 (S). DONE.** `send_github` picks the reactions endpoint from `pr_comment_kind`, defaulting to
  `issue` so a row queued by an older ffwatch still lands.
- **G4 (S). DONE.** No change to `clear_ack`. It already returns 0 for a GitHub payload, because it
  needs `payload["message"]`, so the mark stays on -- which is what the design wants and what the
  trigger already does.

## H. Tests

All in `test_ffwatch.py`, beside the `#codereview` block, using its `Case`, `git_origin`,
`push_a_stranger_branch` and `review_cfg` helpers.

- **H1 (M). DONE.** `MockGitHub` gains three routes: `GET /pulls/comments` (with the `since`, `desc`
  and ETag behaviour the issue-comments route already has), `GET /pulls/{n}/reviews`, and
  `POST /pulls/comments/{id}/reactions`. `GH_STATE` gains `review_comments` and `reviews`, and
  `review_cfg` clears them. The reactions route records into the existing `GH_STATE["reactions"]`
  with the endpoint, so a test can assert which one was used.
- **H2 (M). DONE.** The happy path: an operator leaves two inline comments and one conversation comment
  on an open in-repo pull request; the gate says all three are actionable; the poll makes no turn
  yet; the 👀 is on all three when the poll returns, without a `send_pending` -- `mark_working`
  sends its own row, which is the difference from the trigger's mark and worth asserting; the
  batch ripens after `feedback_quiet_secs`; `claim_turns` makes one turn; the prompt names the
  pull request, the branch, each comment's file and line, and each comment's text.
- **H3 (S). DONE.** A stranger's comment on the same pull request produces no message row, no mark, no
  reply, and no turn -- and the operator's comment beside it still does. This is design section 3
  and it should fail loudly if anybody widens the ingest.
- **H4 (S). DONE.** A stranger's row planted directly in the database is dropped by
  `render_feedback_prompt`. The second gate has to be tested on its own, or it is only ever
  exercised through the first one and could be deleted without a test going red.
- **H5/H6 (S). REPLACED 2026-09-10.** The two gate tests are one test now: "nice, merging this"
  is ingested, marked, ungated and turned into a turn like anything else, and no classifier prompt
  is written, because nothing asks one.
- **H7 (S). DONE.** The quiet period: two comments a minute apart are one turn, not two, and the second
  one resets the clock.
- **H8 (S). DONE.** A comment arriving while a run is in flight is queued, not refused: no comment is
  posted, and the message is claimed by the next turn once the conversation goes idle. The
  contrast with `#codereview`'s refusal is the point, so assert both in one test.
- **H9 (S). DONE.** A review summary with a body and no inline comments starts a run and wears no
  reaction; nothing tries to POST one.
- **H10 (S). DONE.** Id namespacing: an inline comment and an issue comment with the same numeric id
  both survive ingest as separate messages, and both end up in the same turn in the order they
  arrived.
- **H11 (S). DONE.** The mixed batch: a `#codereview` trigger and two feedback comments in one turn
  produce a prompt carrying both the workflow instruction and the comment list.
- **H12 (S). DONE.** The hold: with the window spent, a ripe batch stays gated and no turn is made;
  when it refills, the same batch runs. Model it on
  `test_a_codereview_trigger_waits_in_the_cursor_and_runs_when_the_window_refills`, which fakes
  the usage read the same way.
- **H13 (S). DONE.** Closed, merged and fork-head pull requests: no turn, no row, no comment posted.
- **H14 (S). DONE.** The three cursors watch from now: a comment predating the first poll starts
  nothing.
- **H15 (S). DONE.** The release cap: with `feedback_max_comments` set to 2 and three ripe comments, the
  turn carries two and the third is still gated; it becomes the next turn once the first ends.

## J. Resolving what was addressed (2026-09-10)

Design section 8. Added after the lane shipped, on Lothsahn's ask: once the fix is on the branch,
the comment's thread should close.

- **J1 (S). DONE.** `GitHub.graphql()`, and the two callers that need it. Resolving has no REST
  endpoint — `resolveReviewThread` is a mutation and that is the only way in. A GraphQL error is
  an HTTP 200 with an `errors` array, so it is raised as a `GitHubError` here or a failure reads
  as an answer.
- **J2 (S). DONE.** `review_threads(number)` maps a comment's integer id to its thread's node id.
  They are different objects and a comment's `node_id` is not the thread's, so this query is the
  only tie between them. Read fresh every time: a thread's resolved state is GitHub's fact, not
  this box's.
- **J3 (S). DONE.** `resolve_review_thread(number, comment_id)`. Already resolved is a success;
  a comment with no thread answers False without an error, because a conversation comment and a
  review body have nothing to close.
- **J4 (S). DONE.** `addressed` in `VERDICT_SCHEMA` (`discord-task.sh`), and the feedback prompt
  puts each comment's id in its heading so the run can hand it back rather than invent it. The
  prompt says what the claim means: the reviewer stops looking, so a comment you argued against
  does not go in the list.
- **J5 (M). DONE.** `resolve_addressed()`, called from `record_reply` where both facts are in
  hand. Two conditions: the run named the comment, AND `publish_facts` says the commits reached
  the branch. `addressed` is filtered against the turn's own messages, so an invented id resolves
  nothing. One outbound row per comment, keyed `resolve:<id>` so a replayed finish pass queues
  nothing.
- **J6 (S). DONE.** `send_github` handles the `resolve` action — before the reaction branch,
  since a resolve row carries `pr_comment` too and reading the payload first would have put an
  emoji on the comment instead.
- **J7 (S). DONE.** `github.resolve_threads`, default true, in `DEFAULTS` and `config.md`.
- **J8 (S). DONE.** One test: the prompt carries the ids, an unpublished run resolves nothing,
  only the named diff comment is queued, the thread the run argued against stays open, a replay
  queues nothing, an invented id resolves nothing, and `record_reply` is the call site. The mock
  grew a `/graphql` route and `GH_STATE["threads"]`.
- **J9 (S). BLOCKED ON WHAT GITHUB WILL NOT LET A PAT DO.** Run live against pull request 512
  on 2026-09-10, whose comment had just been fixed and pushed. `review_threads` answered
  correctly -- `{"3972318844": ("PRRT_kwDOJSvcWs6gzn5c", False)}` -- and `resolveReviewThread`
  came back `FORBIDDEN: Resource not accessible by personal access token`.

  This took three passes to diagnose and the first two write-ups were wrong. What was measured
  in the end:

  | probe | accepts | result |
  | --- | --- | --- |
  | `GET /pulls/512` | `pull_requests=read; contents=read` | 200 |
  | `POST /pulls/comments/{id}/reactions` | `pull_requests=write` | 200 |
  | GraphQL `reviewThreads` query | — | 200 |
  | GraphQL `addReaction` mutation | `pull_requests=write` | 200 |
  | GraphQL `resolveReviewThread` | — | **FORBIDDEN** |
  | GraphQL `unresolveReviewThread` | — | **FORBIDDEN** |
  | `PUT /pulls/{n}/merge` (nonexistent repo) | `contents=write` | 404 |
  | `POST /repos/{repo}/merges` (nonexistent branches) | `contents=write` | **403** |

  Read down it: the token HAS `pull_requests=write`, GraphQL works, and another mutation under
  that same permission succeeds. So it is not the permission (first write-up), and not
  fine-grained GraphQL support in general (second). It is resolve/unresolve specifically, and
  GitHub's message names the credential class: a personal access token does not get them. A
  **GitHub App installation token** is the documented route. A classic PAT is untested and the
  message suggests it would be refused too.

  The last two rows are the separate finding that came out of the same session: merging accepts
  `contents=write`, not `pull_requests=write`, and this token does not hold it -- so it cannot
  merge or push, which is what `CREDENTIALS.md` intended.

  Nothing else waits on this. Every resolve fails safe: the fix lands, the run comments, the
  thread stays open for a person. **Re-run against a real thread the day an App token exists.**

## I. Live verification

- **I1 (M).** On the build server, comment on a real open pull request and watch
  `journalctl -u ffwatch`: the poll reads it, the gate answers, the mark appears within a poll,
  the batch ripens, the turn launches on the pull request's branch, the commits land on that
  branch, and the harness's comment says what was done. `#codereview`'s first live run reviewed
  master because two threads disagreed about a branch; assume this one has an equivalent and go
  looking for it in the run's own `job.json` rather than in the reply.
- **I2 (S).** Then a second comment on the same pull request while the first run is still going,
  to prove the queue behaviour end to end.
