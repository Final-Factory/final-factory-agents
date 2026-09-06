# Branch adoption: implementation tasks

Derived from `design/branch_adoption_design.txt` (revision 2, 2026-09-06) after reading the
current publish path: `ffwatch.py` (`ADDED_COLUMNS`/`init_schema`, `insert_message`,
`pending_messages`, `schedule`, `run_ref`, `mirror_carries`/`mirror_take`, `launch`, `publish`,
`push_bundle`, `record_outbound`, the CLI), `ffbox` (the env lists and `harvest_from_out`),
`harvest-workspace.sh`, `restore-workspace.sh`, `discord-task.sh` (the preambles) and
`ffweb.py` (`_branch_note`).

Effort: **S** under an hour, **M** an afternoon, **L** a day or more.

## Status: IMPLEMENTED, offline suites green, not yet verified on live traffic

A through K are implemented across three commits. `test_ffwatch.py` and `test_ffweb.py` both
pass. L is the part offline tests cannot reach — a real origin, a real mirror, a real
container — and is open.

**What changed from the design while building it**, all recorded in the design's revision 3:

- **F belongs to Tier A as well.** The design filed the mirror sync under Tier B because the
  fence is drawn around the prefix. The fence is not what fails first: `mirror_take` fills the
  mirror from `refs/ffbox/<branch>` IN THE HOST CHECKOUT, and that ref exists only for a branch
  this box pushed. An adopted `ffbox/` branch has no copy there either, so the sync keys on
  ADOPTED rather than on the name, and Tier A needs it. Caught by the Tier A end-to-end test
  failing at launch with BranchUnavailable.
- **F1 fetches into the mirror rather than pushing out of the checkout**, which is the shape
  `mirror_take` already has: the credential stays in the checkout and the mirror is never given
  a network.
- **E3 is dropped.** Re-checking the claimed container's branch in `launch` means another
  `docker ps` to re-derive what `pool_claim_for` decided a line earlier. The rule is pinned by
  test instead (E4).
- **D3 changed push_bundle's return** to `(ok, error, existed)`. Two call sites, both updated.
- **H5's local_id** is `adopt:<conv>:<message>`, not `adopt:<conv>`: the dedupe that matters is
  `insert_message`'s rowcount check, which is what makes a sweep's re-read of the thread post
  nothing, and a per-message id keeps two directives in one thread distinguishable in the queue.
- **D1 asks the remote, not a tracking ref.** Revision 2 of the design said to read
  `refs/remotes/origin/<branch>`. That ref outlives a branch DELETED on the remote — the
  publish path's fetch has no `--prune`, and adding one would be this daemon rewriting refs in
  a checkout it shares — so it would have said yes for exactly the case the rule refuses. One
  `ls-remote --heads` per publish, which also answers `run.branch_existed`. There is a test
  that deletes the branch between two pushes of the same bundle.

**Where the tests live.** `test_ffwatch.py`: the end-to-end adoption (Tier B, both turns), the
refusals, the prefix rule including the deletion, the mirror sync's own fence, the scheduler and
the pool, the `!branch` ingress (operator, player, directive-only, directive-plus-prompt,
re-read), the preamble, the harvest range through `run_harvest`, and the v16 migration.
`test_ffweb.py`: the branch note. Tier A is covered by the same machinery as Tier B — the
end-to-end test uses a foreign name because it is the stricter case.

## What already exists

Worth knowing before estimating, because most of this feature is already built for a different
reason.

- **`conversation.branch` is the whole mechanism.** Schema v12. Six readers act on it and none
  of them asks how it got there: `run_ref` (ffwatch.py:6714), `launch`'s branch block
  (7019-7046) and its `--branch-prefix` withholding (7199-7201), `publish`'s second-branch
  refusal (8208-8213) and its `WHERE branch IS NULL` claim (8244),
  `reconcile_publication` (8517-8528), and `preamble_branch` in the container
  (discord-task.sh:545). Adoption is a pre-seed of that column plus the four things that
  assumed a push wrote it.
- **`ADDED_COLUMNS` is how a column lands.** Append a tuple; `init_schema` runs
  `ALTER TABLE ... ADD COLUMN` (ffwatch.py:316, 2224). A bare `TEXT` leaves existing rows NULL,
  which is what A1 wants. `SCHEMA_VERSION` is 15 and the migration block ends at 2302-2306.
- **The gate is the existing "read, not answered" door.** `pending_messages`
  (ffwatch.py:4951) selects `gate IS NULL`, and `create_turn` reads only that; the idle-close
  count at 4416-4418 skips gated messages too, so a thread whose last message is a directive
  still closes on schedule. `insert_message` already writes `gate='none'` for a pre-attach
  message (3712-3725), which is the shape H2 copies.
- **`is_operator(cfg, author_id)` already exists** (ffwatch.py:1339) and reads
  `discord.trust.operators`. `discord_agent_class` (1371-1381) already puts an operator's
  thread on ffdev, so nothing about the lane needs changing for #agent-testing.
- **`record_outbound(run_id, conv_id, "post", payload)`** is the one door into the outbound
  queue (ffwatch.py:7615). `record_blocked_reply` (6129-6188) is the worked example of posting
  without a run: payload `{"channel": reply_channel(conv), "text": ..., "silent": True,
  "local_id": ..., "reply_to": <discord_id>}`, and it returns None for a local conversation on
  its own.
- **`pool_claim_for` already refuses a warm container on the wrong branch**
  (ffwatch.py:6011-6015), and a miss is an ordinary cold launch. The pool rule of design §10 is
  mostly already true; what is missing is the scheduler agreeing with it (E2).
- **The prefix is held by construction, not by a check.** `launch` coerces (7012-7013), the
  harvest rename builds the name out of the prefix (harvest-workspace.sh:134-141), and the only
  refusal is `mirror_take`'s, which guards the mirror (6799). `push_bundle` pushes whatever
  name it is handed. See design §5.6 and task D.
- **`ffbox` carries FFBOX_ variables on two paths** that must agree: the cold `-e` list
  (ffbox:1204-1215) and the dispatch env file (1387-1396).
- **`run_harvest(repo, out, *, branch, prefix, run_id, base_refs)`** in test_ffwatch.py:7187
  drives the real `harvest-workspace.sh` against a seeded repo (`seed_agent_repo`, 7223). Every
  harvest task below gets its test through it rather than through a fragment.

## A — the adoption record (S)

- **A1** Two entries in `ADDED_COLUMNS`, beside the v12 block:
  `("conversation", "branch_adopted_at", "TEXT")` and
  `("conversation", "branch_adopted_by", "TEXT")`. Bare TEXT: NULL on every existing row is the
  right answer, because every existing branch was claimed by a push.
- **A2** `SCHEMA_VERSION` 15 -> 16. No migration statement: there is nothing to backfill and
  nothing to correct. Add the v16 comment to the migration block anyway, saying that, so the
  next reader does not go looking for the rewrite.
- **A3** `conversation_adopted(conv)` beside `conversation_branch` (ffwatch.py:6678), guarded
  for a missing column the same way and for the same reason — a row read before the migration
  ran. Returns True only when `branch_adopted_at` is set AND `branch` is set.
- **A4** Test: a database created at v15 gains both columns and reports v16; `conversation_adopted`
  is False for every pre-existing conversation and for a row missing the column entirely.

## B — adopt_branch and its validation (M)

- **B1** `Watcher.adopt_branch(conv_id, branch, by)` -> `(ok, reason)`. One writer, called by
  both ingresses. Never raises for an ordinary refusal; the reason is a sentence a person reads.
- **B2** The five checks of design §5, in that order, each with its own message:
  ref format (`git check-ref-format --branch`); not protected and not a `publish_bases` key;
  `refs/remotes/<push_remote>/<name>` resolves in `git_dir` after a fetch; no other
  non-closed conversation owns the name; this conversation owns no branch and has no run with
  `pushed=1`.
- **B3** On success: one UPDATE writing `branch`, `branch_adopted_at=now_iso()`,
  `branch_adopted_by=by`, guarded `WHERE id=? AND branch IS NULL` so two ingresses racing
  cannot both claim. A rowcount of 0 is a refusal, not a success.
- **B4** After the write, call `mirror_sync_from_origin` (F) for EVERY adopted name — see the
  status block; the prefix is not the question. Report its failure in the reason with the row
  already written, so the operator can retry the sync rather than re-adopt.
- **B5** `PROTECTED_BRANCHES` in ffwatch: today the list lives in `ffbox`
  (`FFBOX_PROTECTED_BRANCHES`, defaulting to `develop master main`) and in
  `harvest-workspace.sh:56`. ffwatch needs the same names for B2. Read them from
  `cfg["publish_bases"]` plus a module constant `PROTECTED_BRANCHES = ("master", "develop",
  "main")` with a comment naming ffbox:PROTECTED_BRANCHES as the original, the way ffweb
  mirrors `LOCAL_KINDS`.
- **B6** Tests: each refusal in B2 individually; the happy path writing all three columns; a
  second adopt on the same conversation refused; two conversations adopting one branch, the
  second refused.

## C — ffwatch adopt (S)

- **C1** `sub.add_parser("adopt")` beside `close` (ffwatch.py:11343), with
  `--conversation ID` (required), `--branch NAME` (required) and `--json`.
- **C2** Dispatch: call `adopt_branch(..., by=getpass.getuser())`, print the reason, exit 1 on
  refusal so a script can tell. `--json` prints `{"ok": bool, "branch": ..., "reason": ...}`.
- **C3** Works for a local conversation as well as a Discord one — this is the only ingress a
  `ffwatch submit` conversation has.
- **C4** Test: the CLI path adopts, and a refusal exits non-zero with the reason on stderr.

## D — the prefix rule at the push (S)

Design §5.6. Lands with A-C even though only Tier B can trip it.

- **D1** In `push_bundle` (ffwatch.py:8699), after the existing `git fetch <remote>` and before
  the push: when `branch` does not start with `cfg["branch_prefix"]`, require
  `refs/remotes/<remote>/<branch>` to resolve. Otherwise return
  `(False, "<branch> is outside <prefix> and is not on <remote>; ffbox does not create a
  branch outside its own prefix")`.
- **D2** Read it from the remote-tracking ref, not from the conversation row. A branch deleted
  since adoption is exactly the case this refuses.
- **D3** Record the answer: `run.branch_existed` is currently derived from whether the
  conversation already owned a name (8225-8231). Have `push_bundle` return what it looked up
  and record that instead, so the column answers its own question.
- **D4** Do NOT touch the coercion at 7012-7013. It applies to an option-supplied `--branch`
  and the adopted name overrides it afterwards at 7028-7029; that order is what lets adoption
  through. Add a comment saying so, because it reads like a bug otherwise.
- **D5** Tests: an unprefixed name origin does not have is refused and leaves no branch; the
  same name once origin has it is pushed; a prefixed name is unaffected in both cases.

## E — the ref ladder and the pool rule (M)

Design §10.

- **E1** One function answers "where does this turn start". `run_ref(turn, conv)` already is
  it; give it a form the scheduler can call, which holds a JOINed turn row and no conversation
  row (`conv_agent_class`, `conv_base_sha` and now `conv_branch` come along in the SELECT at
  ffwatch.py:6074-6079).
- **E2** The pre-check at 6095-6099 asks `pool_would_serve` about that ref instead of
  `turn_options.ref or conv_base_sha or base_ref`. This is a real fix, not a tidy: from turn 2
  a conversation's `base_sha` is a pinned sha, `looks_like_sha` is true, and the pre-check has
  been answering yes for any warm container of the class while `launch` cold-started on the
  conversation's branch. On a full box that is a run started past a ceiling with no room for it.
- **E3** DROPPED. Asking the question again in `launch` means another `docker ps` to
  re-derive what `pool_claim_for` decided a line earlier. E4 pins the rule instead.
- **E4** Tests: a conversation on a branch no pool is staged on is not offered a warm
  container; the scheduler's pre-check and `launch` are asked about the same ref for the same
  turn (assert on the argument, not on the outcome, so the test still means something when the
  pool is empty).

## F — mirror_sync_from_origin (M)

Design §8. Both tiers, not Tier B — see the status block.

- **F1** `mirror_sync_from_origin(branch)` -> bool, beside `mirror_take` (ffwatch.py:6771):
  `git -C <git_dir> fetch --quiet <push_remote>`, then
  `git -C <git_dir> push <mirror> +refs/remotes/<push_remote>/<branch>:refs/heads/<branch>`.
  Refuses a protected or `publish_bases` name. Logs what it did, like `mirror_take`.
- **F2** Its docstring carries the argument for why its fence differs from `mirror_take`'s: it
  can only write the value origin already has, so the worst it does is make the mirror agree
  with GitHub sooner than the runners' fetch would.
- **F3** Call it at adoption (B4), for every adopted name.
- **F4** Call it at EVERY launch of an adopted conversation, replacing the
  `if not mirror_carries(...) and not mirror_take(...)` guard for that case only
  (ffwatch.py:7028-7046). A conversation with `branch_adopted_at IS NULL` keeps `mirror_take`
  exactly as it is. A failed sync still raises `BranchUnavailable` with the existing message.
- **F5** Route the post-publish `mirror_take(branch)` at 8248 BY THE NAME — the one place the
  prefix is the right question, because a push has just happened and the commits are in both
  places. Same in `reconcile_publication`.
- **F6** Tests: refuses `master`; writes only origin's value; a launch of an adopted
  conversation syncs even when `mirror_carries` is already true.

## G — --range-from-start (M)

Design §9. Tier B.

- **G1** `ffbox --range-from-start`, default off, into `FFBOX_RANGE_FROM_START` on BOTH env
  paths (ffbox:1204-1215 and 1387-1396) and into `usage()`.
- **G2** `harvest-workspace.sh`: after the `--base-refs` scan sets `PUBLISH_BASE` and
  `PUBLISH_BASE_SHA`, when the flag is set replace `PUBLISH_BASE_SHA` with `$BASE_SHA` provided
  `git merge-base --is-ancestor "$BASE_SHA" HEAD` passes. Keep `PUBLISH_BASE` — the NAME still
  aims the pull request. If `$BASE_SHA` is empty or is not an ancestor, `harvest_failed` with
  the reason, rather than silently falling back to the base ref: falling back is what produces
  the "identity this run does not own" refusal the flag exists to prevent, three steps later
  and with a message about the wrong thing.
- **G3** `launch` passes the flag when the conversation is adopted (A3).
- **G4** Tests through `run_harvest`: with the flag, a repo whose history below the run's start
  carries a foreign author publishes cleanly and `publish_base.txt` still names the base; with
  the flag, a commit the RUN made under a foreign identity is still refused; without the flag,
  behaviour is unchanged. Also that `test_every_task_script_harvests_its_own_workspace`
  (test_ffwatch.py:5790) still passes with the variable threaded through.

## H — the !branch directive (M)

Design §6.

- **H1** `branch_directive(content)` -> name or None: a line whose entire content, stripped, is
  `!branch <name>`. First match wins; a second directive line in one message is ignored and
  logged.
- **H2** Applied in `insert_message` (ffwatch.py:3692), after the `rowcount == 0` early return
  and before `demote_for_stranger`, so every ingress — doorbell, sweep, DM — gets it once and
  only for a message that is genuinely new. Guarded on the conversation NOT being local:
  `is_operator` reads a Discord snowflake table and a unix login that happens to be all digits
  must never be looked up in it (the warning `upsert_conversation` already carries at 3617).
- **H3** Operator only, from the stored `author_id`. For anybody else: no adopt, no reply, no
  gate — the line is ordinary text and reaches the model as prose. One host log line naming
  the conversation and the author, so the attempt is visible to an operator without telling the
  channel that a command exists.
- **H4** A message whose whole content is the directive gets `gate='branch_directive'` and
  `gate_reason` = the outcome, so `pending_messages` never turns it into a turn. A message that
  carries a directive AND a prompt is not gated.
- **H5** The acknowledgement: `record_outbound(None, conv_id, "post", ...)` in
  `record_blocked_reply`'s shape, with `local_id = f"adopt:{conv_id}:{message_id}"`. What stops
  a re-read posting twice is `insert_message`'s rowcount check, not the id. Both outcomes get
  one — the refusal reason is as useful as the confirmation.
- **H6** A directive that lands while a run is in flight adopts and says the branch takes
  effect on the NEXT turn. It does not try to move the running container.
- **H7** Tests: an operator's directive-only message adopts and creates no turn; an operator's
  directive plus prompt adopts and DOES create a turn; a non-operator's identical message
  adopts nothing, posts nothing, and becomes an ordinary turn; a directive in a local
  conversation is inert; a refused adoption still posts its reason once.

## I — what the agent is told (S)

Design §11.

- **I1** `build_job` adds `bases.branch_adopted` beside `bases.conversation_branch`
  (ffwatch.py:6420).
- **I2** `preamble_branch` (discord-task.sh:545) grows the adopted variant: the commits are
  somebody else's, read the branch before changing it, add commits on top, and do not branch,
  switch, rebase, revert or amend. Keep the existing continuation text for a branch the
  conversation made.
- **I3** Test: the adopted preamble appears for an adopted job and not for an ordinary
  continuation, and the ordinary one is unchanged.

## J — the page (S)

Design §12.4 and §9.4.

- **J1** `_branch_note` (ffweb.py:2725) says a branch was adopted and by whom.
- **J2** Its docstring's "each publishing run bundles its whole branch against the base, so the
  LAST one is the branch's total" is false for an adopted conversation, where the counts are
  per-run. Fix the docstring and label whichever is being shown.
- **J3** Test in test_ffweb.py: an adopted conversation renders the note; an ordinary one is
  unchanged.

## K — docs (S)

- **K1** `ffbox/README.md`: `ffwatch adopt` in the operator commands, and `!branch` with the
  operator-only rule.
- **K2** `ffbox/config.md` is NOT touched — no config key changes shape. If that stops being
  true it changes in the same commit (the standing rule in CLAUDE.md).
- **K3** This file's status block, and the design's revision note if anything below changed a
  decision rather than implementing it.

## L — live verification (M)

Offline tests cannot reach origin, the mirror or a container. On the build server, after
deploy:

- **L1** Tier A: adopt an `ffbox/` branch from a closed conversation into a new thread, add a
  commit, confirm the push lands on the same branch and the existing PR is reused.
- **L2** Tier B: adopt a foreign-named branch pushed from elsewhere, confirm the mirror gains
  it, the run starts on its head, and the publish carries only the run's own commits.
- **L3** The refusal: adopt a branch, delete it on origin, take a turn, and confirm the run
  refuses with D1's message rather than re-creating the branch.
- **L4** A non-operator posts `!branch` in a watched channel and nothing happens except the
  ordinary answer.
