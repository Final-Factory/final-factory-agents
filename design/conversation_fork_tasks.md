# Conversation forking: implementation tasks

Derived from `design/conversation_fork_design.txt` (revision 2, 2026-09-08) after reading the
paths it touches: `ffwatch.py` (`ADDED_COLUMNS`/`init_schema`, `ingest_channel_message`,
`ingest_thread`, `insert_message`, `take_branch_directive`, `adopt_branch`, `pending_messages`,
`create_turn`, `build_job`, `render_summary`, `render_prompt`, `is_direct_conversation`,
`transcript_path`, `_index_transcript`, `record_outbound`, the CLI) and `ffweb.py` (the
conversation page and list).

Effort: **S** under an hour, **M** an afternoon, **L** a day or more.

## Status: IMPLEMENTED (A-K), offline suites green, L open

A through K are in. `test_ffwatch.py` and `test_ffweb.py` both pass, including eleven new fork
tests and one new ffweb one. L is the part offline tests cannot reach — a real Claude Code, a
real container, a real origin — and is open. **Tier A does not depend on L passing**: if the
graft turns out not to resume, every fork falls back to the summary seed, which is the path the
daemon already takes for a lost transcript.

The design's four section-15 decisions were taken as it proposed them: nothing is posted in the
source thread, a branch gone from origin warns rather than refuses, public-into-public is
allowed, and the directive is `!conv` with `!conversation` on the same rule.

**What changed while building it**, all recorded in the design's revision 2:

- **B1's signature is `fork_conversation(fork_id, source_id, by)`.** The destination row already
  exists on every ingress path, so five arguments describing where to make one were re-deriving
  what one row answers. It also makes the refusal cheap in Discord: an ordinary conversation
  holding a gated message, exactly as a refused `!branch` leaves one.
- **H1 lost `--into`.** `ffwatch fork` is local only. A Discord destination has a door already,
  and a second one would re-derive a watch alias to apply the venue rule — the one rule that
  must not be wrong.
- **C2 also titles the conversation**, from the first line under the directive, or from the
  source when there is none. `!conv 85` as a name in the conversation list is a command sitting
  where every other row has a subject.
- **The in-flight check reads three signals**, not the turn table alone: `conversation.state`, a
  queued or running turn, and an unclaimed message. They disagree for a moment during a launch.
  `branch_in_flight` was factored out of `adopt_branch` so the branch race has one query.
- **I moved into Tier A.** The page is being edited for the fork control anyway, and that
  control lands the operator on a page that would otherwise not say what it forked.
- **The local fork mints its id through `local_message_key`.** `submit`'s old recipe was
  milliseconds plus the pid, which is not unique inside one millisecond; that was found and
  fixed upstream (b7f55a8) while this was being built, and H2 uses it rather than repeating it.
- **The ffbox stub's transcript records now carry `sessionId`**, which the real ones always have
  on every line. Without it the graft's rewrite could not be asserted through the real path.

**Where the tests live.** `test_ffwatch.py`: the end-to-end fork (branch, session, history, ack,
turn, re-read), resume at seq 1 and the summary fallback, the history watermark, the operator
rule, the directive alone, the venue rule both ways, the in-flight refusal and the retry after
it, the channel anchoring, `fenced_history`, the local rollback, the cheap refusals, and the v18
migration. `test_ffweb.py`: the link both ways, the button and its absence mid-run, and the POST
route's argv.

## What already exists

Worth knowing before estimating, because most of the machinery is built.

- **`!branch` is the template for the whole ingress.** `BRANCH_DIRECTIVE_RE`
  (ffwatch.py:2065), `take_branch_directive` (4459), `adopt_branch` (8338) as the one writer for
  two doors, the `gate='branch_directive'` rule, the one-post-either-way ack, and the
  operators-only-and-silent policy. Copy the shape; do not copy the hook site (design 5.2).
- **`adopt_branch` already does the branch half.** Its five refusals are the right ones, it
  tolerates several conversations on one branch, and `record_branch_pull_request` gives the fork
  the source's pull request. Call it; do not write `conversation.branch`.
- **The summary fallback is written.** build_job already bumps the generation and seeds a session
  from `render_summary` when a transcript is missing (ffwatch.py:7590-7605). The fork's fallback
  is that code with one more condition.
- **Merge notices already fan out by branch.** `conversations_for_pull_request` (12660) and
  `take_merge` (12628). A fork that inherits the branch makes the public source hear about the
  merge with no new code, in the right register, because `announce_merge` splits on the
  conversation's own venue.
- **Attachments need nothing.** Content-addressed blobs under `<state>/blobs`, staged into the
  conversation's mount at job time.

## Tasks

### A. Schema (S) — design §8

- **A1.** Six columns in `ADDED_COLUMNS`, with the comment block those entries carry:
  `forked_from`, `forked_at`, `forked_by`, `fork_source_watermark`, `fork_session`,
  `fenced_history`. `SCHEMA_VERSION` 17 -> 18. No index.
- **A2.** Add them to `ffwatch_schema.sql` too, so a database created fresh has them without the
  ALTER pass.
- **A3.** A `conversation_fork(conv)` reader guarded the way `conversation_branch` is, so a row
  read before the migration answers None instead of raising.

### B. `fork_conversation`, the one writer (M) — design §9, §6, §7

- **B1.** `fork_conversation(fork_id, source_id, by)` returning `(ok, reason)`, on a destination
  row the caller has already made. Refusals in the order design 5.5 gives them, each one a
  sentence. Class, kind, alias and venue are read off the row; forking chooses none of them
  (design §7.2).
- **B2.** Fill the fork columns, `base_sha` and a missing title in one UPDATE, guarded on
  `forked_from IS NULL` so two ingresses racing cannot both claim. `fenced_history` =
  `not is_direct_conversation(source)`.
- **B3.** Call `adopt_branch(fork_id, source_branch, by)` when the source has one, keep its
  reason for the ack, and do not fail the fork when the branch is merely gone from origin
  (design 6.1; decision 15b).
- **B4.** Call the graft (D), fall back to the summary seed, record `fork_session` or NULL.
- **B5.** Log one line naming source, fork, branch, class and whether the session came over.

### C. The two ingest hooks (M) — design §5.1-5.4

- **C1.** `FORK_DIRECTIVE_RE`, `fork_directive(content)` and `is_only_fork_directive(content)`
  beside the branch pair.
- **C2.** In `ingest_channel_message`, after the "already ours" check and before
  `select_conversation`: an operator's directive opens its own conversation and never joins a
  clustering window. Both sides of that placement have a test in K, because getting it wrong in
  one direction anchors the fork on the wrong conversation and in the other forks once per
  sweep.
- **C3.** In `ingest_thread`: a thread whose only message so far is the directive becomes the
  fork. A thread that already has a turn is refusal 5.5e.
- **C4.** The gate: `gate='fork_directive'` when the message is only the directive, or when the
  fork was refused. Lift it the way `take_branch_directive` lifts its own, guarded on our own
  gate value so it can never lift the engagement gate's decision.
- **C5.** Non-operators: no action, no reply, one host log line.
- **C6.** `addressed=1` on the message when the fork lands, so an `engage: mention` channel does
  not swallow the question attached to the directive.

### D. The transcript graft (M) — design §6.2

- **D1.** `graft_transcript(source_conv, fork_conv, fork_session_id)`: copy the JSONL, rewriting
  `sessionId` on every record, leaving uuids alone. Returns the source session id or None.
- **D2.** Refuse to run when the source has a turn in flight. That is refusal 5.5c and it is
  checked in B1, but assert it here too: this is the function that would copy a half-written
  file.
- **D3.** Create the fork's `claude/projects/<slug>/` directory the way the mount setup does.
- **D4.** Non-fatal on OSError or a malformed line: return None and let B4 fall back.

### E. Resume, history and summary (M) — design §6.2, §6.3

- **E1.** `resume` in `build_job` (ffwatch.py:7546) becomes true on seq 1 for a grafted fork.
- **E2.** The generation-bump fallback below it covers "grafted but the file is gone".
- **E3.** `history_conversations(conv)` -> `[conv]` or `[source, conv]`; the history query reads
  both, bounded by `fork_source_watermark` on the source's side and still capped by
  `history_messages`.
- **E4.** `render_summary` walks the same pair, so a summary-seeded fork renders the source's
  turns rather than an empty document.

### F. The fencing guard (S) — design §7.3

- **F1.** `is_direct_conversation` returns False when `fenced_history` is set, before it consults
  the kind. One caller passes a row (ffwatch.py:7635) and it is the one that matters; the
  bare-kind callers are unaffected and should stay that way.
- **F2.** A test that a fork of a bug report, taken into an operator DM and into a local
  conversation, is `direct: false` in job.json.

### G. The acknowledgement (S) — design §5.5, §5.6

- **G1.** One post either way, `local_id = f"fork:{source}:{message}"`, matching the shape
  `adopt:<conv>:<message>` uses and for the same reason: the dedupe that matters is
  `insert_message`'s rowcount check, and a per-message id keeps two directives distinguishable.
- **G2.** The three clauses of design 5.6, and the summary-fallback wording.
- **G3.** Nothing posted in the source thread (decision 15a).

### H. The other two ingresses (S) — design §11

- **H1.** `ffwatch fork --conversation ID [--agent CLASS]`, through `open_local_fork` and
  `fork_conversation` and nothing else. `--agent` defaults the way `submit`'s does.
- **H2.** It opens a `shell` conversation with no Discord side, and no prompt and no turn: a
  fork is a place to carry on from, and the question that carries on is a separate act.
  `fenced_history` is what keeps it safe. A refusal deletes the row it made.
- **H3.** Print the fork id and the same three facts the ack posts.
- **H4.** ffweb: a fork control on the conversation page next to the follow-up box, shelling out
  to `ffwatch fork --local` through `Actions` the way `submit` does (ffweb.py:1423-1445), with
  the agent selector the new-prompt form already has. It lands the operator on the new
  conversation's page.

### I. ffweb (S) — design §10

- **I1.** The conversation page says `fork of 85` with a link, and the source's says
  `forked into 91`.
- **I2.** The conversation list shows the marker so a fork is recognisable without opening it.

### J. Docs (S)

- **J1.** `ffbox/README.md`: the directive, the CLI, and the one-way venue rule.
- **J2.** No `ffbox/config.md` change. This feature adds no config key, which is worth stating in
  the commit message so the config rule in CLAUDE.md is visibly not being skipped.

### K. Tests, offline (M) — design §13, §14

In `test_ffwatch.py`, against the fake Discord the suite already has:

- the whole path end to end: a bug-report conversation with two turns and a branch, `!conv` in a
  private channel, and the fork's first turn resuming the grafted session;
- every refusal in 5.5, each asserting the sentence and that no conversation was created;
- the venue rule in all four directions;
- a non-operator's identical line: no fork, no reply, nothing in the outbound queue;
- directive alone (gated, no turn) and directive plus a question (one turn), and the same pair
  when the fork is refused;
- the graft: sessionId rewritten on every record, uuids unchanged, the two files independent,
  and `_index_transcript` indexing the fork without colliding with the source's rows;
- the resume fix: seq 1 with a graft resumes, seq 1 without one does not;
- history and summary reading across the pair, and stopping at `fork_source_watermark` when the
  source gains a message after the fork;
- `fenced_history` (F2);
- the ffweb route: the fork control produces the same rows the directive does, and the page it
  redirects to is the fork's;
- the v18 migration on a database created at v17.

### L. Live verification (M, cannot be done offline) — design §6.2

- **L1.** The graft against the real Claude Code in a container: `--resume` on a copied
  transcript with a rewritten `sessionId`, and a reply that demonstrably knows something only the
  source session's trace contains. Record the version and date in the design the way the
  /compact check is recorded (ffwatch.py:7563). **Everything else in Tier A can ship before this
  passes**, because the summary fallback is the same code the daemon already runs when a
  transcript goes missing.
- **L2.** One real fork of a real bug thread into #dev-chat, with an ffdev container, ending in a
  push to the inherited branch.
- **L3.** Confirm the merge notice reaches the public source when that push's pull request
  merges, and that it arrives in Max's register with no pull request link.
