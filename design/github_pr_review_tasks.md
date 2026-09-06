# #codereview PR trigger: implementation tasks

Derived from `design/github_pr_review_design.txt` (2026-09-06) after reading the current ingest
and publish paths: `ffwatch.py` (`catchup_pass`, `sweep`, `ingest_event`, `upsert_conversation`,
`insert_message`, `create_turn`, `claim_turns`, `build_job`, `launch`, `publish`,
`record_outbound`, `record_reply`, `send_pending`, the `GitHub` client), `discord-task.sh` (the
argv builder), and `05-discord-setup.sh` for config seeding.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more.

## Status: NOT STARTED

## A. Config and credentials

- **A1 (S).** `github.trust.operators` in `DEFAULTS`, seeded empty in `05-discord-setup.sh`, and
  documented in `config.md`. Name to numeric GitHub user id. Empty means nobody can trigger,
  which is the right default for a box that has not been told who its operators are.
- **A2 (S).** `github.trigger` (default `"#codereview"`) and `github.review_pool` (default
  `"ffdev"`). The pool is named rather than hardcoded, for the same reason `discord.operator_pool`
  is: a box that wants to put this behind the fence should be able to say so and find out that it
  cannot push, rather than have the choice buried in code.
- **A3 (S).** ffdev `agent_secs` 1800 to 7200 in all four places: `DEFAULTS["agent_classes"]`
  in `ffwatch.py`, the `pools.ffdev` block in `05-discord-setup.sh`, `config.md` (the example
  *and* the per-class table row), and the live `~/.config/ffbox/config.json`. Leave ffagent at
  1800. CLAUDE.md requires `config.md` in the same commit.

## B. The GitHub client

- **B1 (S).** `list_issue_comments(since)` on `GitHub`, paginated, `sort=updated`.
- **B2 (S).** `pull_request(number)`, returning head ref, head repo full name, base ref and
  state. The head repo is what answers "is this a fork".
- **B3 (S).** `create_issue_comment(number, body)` and `react_to_comment(comment_id, content)`.
- **B4 (S).** No merge method, and a test asserting the string `"merge"` appears in no method
  name on the class. The absence is load-bearing and should be pinned where an edit trips it.

## C. Ingest

- **C1 (M).** `poll_github()`, called from `catchup_pass` beside the Discord sweep. Cursor file in
  `state_dir`. For each comment since the cursor: match the trigger, look the author id up in
  `github.trust.operators`, and drop everything else without a network call.
- **C2 (M).** The refusal set, each recording the comment against the cursor so it is decided
  once: author not an operator (silent), pull request closed, head in a fork, head branch in
  neither the mirror nor `git_dir`. The last three post a comment saying which; the first does
  not, because answering a stranger tells them the trigger exists.
- **C3 (M).** `github_pr` conversation kind. `thread_id` = `github:pr:<number>`,
  `agent_class` from `github.review_pool`, `branch` and `github_pr` filled in at creation from
  B2. It is not a `LOCAL_KIND` -- it has somewhere to post -- and it belongs in
  `GATE_BYPASS_KINDS` and `DIRECT_KINDS`. Schema comment on `conversation.kind` updated.
- **C4 (M).** The in-flight refusal: `conversation.state IN ('queued','running')` posts a comment
  naming the run and creates no turn. This is where `github_pr` deliberately differs from
  `follow_up()`, which queues.

  **It must not leave an unclaimed message row.** `claim_turns` selects every conversation
  holding a message with `turn_id IS NULL` whose kind is not in `LOCAL_KINDS`, so a refused
  trigger recorded as a message becomes a turn on the pass after the running one ends -- which
  is precisely the "silently start a second review when the first finishes" outcome the refusal
  exists to prevent. The refusal therefore takes the shape the DM autoreply already uses: an
  outbound row with `local_id` = `codereview-refused:<comment id>` and no conversation id and no
  message row. That id is what holds one comment to one refusal across a replayed sweep, since
  the `message.discord_id` dedupe is not available to a path that writes no message.
- **C5 (S).** `demote_for_stranger()` must not fire on a `github_pr` conversation. Exempt it the
  way local kinds are exempt, and put the reason in the code: the prompt carries no commenter
  text, so there is no stranger's words to fence.
- **C6 (S).** `turn_trust()` resolves a `github_pr` turn against `github.trust.operators`, not
  `discord.trust.operators`. As written it reads `operators(cfg)`, the Discord table, and a
  GitHub numeric id is never in it -- so every review turn would come back `player` tier and get
  the player-facing prompt framing and policy. Ingest has already proved the author is an
  operator, so the branch can short-circuit the way `is_local_conversation` does.
- **C7 (S).** `turn_venue()` returns `private` for `github_pr`. It falls through to
  `venue_for(cfg, None)` today, which answers `public` for a conversation that has no watch
  entry and never will.


## D. The prompt and the container

- **D1 (M).** The turn prompt, built by the harness from B2 and the diff range. It names the pull
  request, the branch, the base, and instructs: run `/code-review-sonnet`, investigate what it
  returns, apply the findings that survive, commit onto the current branch. No level argument.
  No commenter text, and a test asserting the comment body appears nowhere in the built prompt.
- **D2 (S).** `Workflow` added to this lane's capability set in **both** places: the `--tools`
  set and the `--allowedTools` list. Measured 2026-09-06 on claude 2.1.263 -- `--tools` alone
  gets "Review dynamic workflow before running", which a `-p` run has nobody to answer, and the
  turn dies having done nothing. This lane only; the shared `CAPABILITY_TOOLS` and
  `CAPABILITY_ALLOWED` that every lane reads are untouched.
- **D3 (M).** `discord-task.sh` copies `.claude/workflows/code-review-sonnet.js` into
  `$CLAUDE_CONFIG_DIR/workflows/` **from the base ref**, via `git show <base>:<path>`, not from
  the checked-out head. Skip quietly if the file is absent on the base, the way a missing plugin
  directory is skipped.
- **D4 (S).** The verdict schema gains `fixed`, `left` and `review_summary`, so the comment in E2
  is composed from fields rather than prose.

## E. Saying something back

- **E1 (M).** A `github` destination in `send_pending`, dispatching `post` and `react` to B3.
  Same row shape, same nonce, same backoff, same kill switch, same `approve_before_send`.
- **E2 (M).** `record_reply` composes the pull request comment for a `github_pr` conversation:
  what was fixed, what was left and why, the verification result, the run id. `announce_publication`
  stays Discord-only -- there is nothing to announce when the branch was already under the pull
  request the comment is on.
- **E3 (M).** The acknowledging reaction, queued when the turn is created rather than when it
  starts, so a queued run is still visibly seen. This is a branch inside `mark_working()`, not a
  separate call: that method already owns the idempotency `local_id`, the send-now-rather-than-
  queue decision and the kill-switch path, and it currently builds a Discord payload
  (`reply_channel(conv)`, `message`, `emoji`) that means nothing to GitHub.

## F. Tests

- **F1 (M).** Offline coverage in `test_ffwatch.py` for every refusal in C2, the operator gate,
  comment-id dedupe across a replayed sweep, and the in-flight refusal.
- **F2 (S).** A test that a `github_pr` prompt contains no comment text (D1) and that
  `demote_for_stranger` leaves the conversation's class alone (C5).
- **F3 (S).** A test that the workflow copy reads from the base ref and not from the workspace
  head (D3).
- **F4 (S).** A test that the built argv carries `Workflow` in both the `--tools` value and an
  `--allowedTools` entry for this lane, and in neither for the Discord lanes.

## G. Live verification

- **G1.** `#codereview` from an operator on a real open pull request with an in-repo head.
  Confirm: reaction appears, run opens in ffdev, `job.json` shows `agent_class: ffdev` and a
  7200 agent clock, the workflow is found from `/ffbox/claude/workflows/` and runs without a
  permission refusal, its subagents are sonnet, commits land on the existing branch as a
  fast-forward, no second pull request, comment posted.
- **G2.** `#codereview` from a non-operator account: nothing happens, nothing is posted, cursor
  advances.
- **G3.** `#codereview` twice in quick succession: the second is refused with a comment naming
  the first run.
- **G4.** A fork pull request: refused with a comment, no container created.

## Confirmed sound while cross-checking

These were assumptions in the design and are now checked against the code, so nobody re-opens
them:

- `should_engage_for()` tests `GATE_BYPASS_KINDS` **first**, before the `gate` argument, so
  putting `github_pr` in that tuple is enough to keep the engagement classifier off a
  harness-built prompt. It does not also need `forced`.
- `record_outbound()` refuses only `is_local_conversation`, so a `github_pr` row enters the queue
  normally. `send_one()` is the single dispatch point that needs the GitHub branch.
- `restore-workspace.sh` fetches the mirror into `refs/remotes/origin/*`, so the container has
  `origin/<base>` locally. Both `git show origin/<base>:.claude/workflows/code-review-sonnet.js`
  (D3) and the diff range in the prompt (D1) resolve without a network call.
- `publish()` needs no change at all. `conv["github_pr"]` being set already short-circuits pull
  request creation, and `push_bundle()` is a non-forced fast-forward onto the existing head.

One cosmetic wart, deliberately left: `session_id_for()` builds `uuid5(ns, "discord:<thread>")`,
so a review conversation's session id is derived from the string `discord:github:pr:123`. It is
deterministic and unique, and renaming it would orphan every existing session.

## Open, from the design

- Whether the harvest should refuse changes under `.github/workflows/`. Not required by anything
  above; it is the change that would actually enforce "no unreviewed Actions edits".
