# Per-operator Claude subscriptions: implementation tasks

Derived from `design/operator_subscriptions_design.txt` (2026-09-10) after reading the code it
lands in: `claude_keys.py` whole, `ffwatch.py`'s trust readers (`operator_ids`, `operators`,
`github_operators`, `turn_trust`), its hold path (`conversation_held`, `claude_hold`,
`work_hold`, `review_held`, `say_holding`, `log_hold`), its launch and staging paths
(`launch`'s run INSERT around 10460, `pool_stage`, `pool_claude_key`, `pool_claim_for`,
`pool_would_serve`, `keep_pool`), the classifier builder (`classifier_invocation`,
`active_claude_token`), `ffbox`'s token resolution (540-621) and its two `docker run` blocks,
`ffweb.py`'s `page_claude`, and the Claude tests already in `test_ffwatch.py` and
`test_ffweb.py`.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more.

## Status, 2026-09-10

**Implemented and green, offline.** `sh ffbox/test.sh` passes end to end — `test_ffwatch.py`,
`test_ffweb.py`, `test_container_credential.sh` (now in the runner, H15) and the four shell
suites. `bash -n` on ffbox, setup.sh, 05-discord-setup.sh and test.sh. Nothing here has run
against a real docker daemon or a real Anthropic key, so three things are covered by
construction only and want watching after the deploy:

- **Claude Code accepting `ANTHROPIC_API_KEY` from the container environment** without wanting
  the key approved. The deploy step below is the check; it is a claim about Claude Code rather
  than about this repository, and no offline test can make it.
- **A warm spare actually being claimed by key.** The matching rule, the recorded file and both
  callers are tested; a real dispatch into a real staged container is not.
- **The API-key probe against the live endpoint.** `x-api-key` with no OAuth beta, a 429 read as
  a live key: asserted against a stub.

Eight deviations from the phases below, all deliberate:

1. **`ffwatch pool stage` did not gain `--claude-key`** (E1). `pool_stage` defaults it to
   `pool_stage_key(class)`, which is the answer the flag would have been given; a flag with one
   possible useful value is a flag nobody types.
2. **`run_classifier` / `should_engage_for` had two call sites, not three** (C3). The third
   `pick_claude_key()` caller was the staging one, which became `pool_stage_key`.
3. **`claude_routes()` formats the refusal sentence** rather than passing `subscription_named`'s
   internal word through. Startup, `/claude` and a Discord refusal should not each teach the
   reader a different vocabulary for the same problem.
4. **`conversation_held` returns `(verdict, secs, why, key)`** — the shape D3 asked for, named.
5. **`pool_matches` is a new method** holding the one rule `pool_claim_for` and
   `pool_would_serve` share (E2). They disagreeing is what admits a turn on the promise of a
   container it cannot have.
6. **`schedule()` routes too** — not in the tasks. Its admission check asks `pool_would_serve`
   whether a dispatch would avoid needing a place, and without the credential that question
   answers about a spare this turn could not use. The turn row's JOIN gained `conversation.kind`
   for it.
7. **`_pool_stage_after`'s held-tier key is `(class, branch, credential)`** and the cooldown
   check MOVED below the credential lookup (E5). Keyed one way and checked another, the backoff
   would never have matched — the evictable tier keeps its own `(class, branch)` shape, and the
   field's comment now says why there are two.
8. **`max_budget_usd` per class is `null` = the box's number** (C6), resolved in `build_job`
   rather than in `_class_blocks`, so a box that sets one number at the top level is unchanged
   and neither lane has a hidden default of its own.

**One consequence the design implies and did not spell out**, found by rewriting the hold tests:
a player's work can no longer be held at all. The metered key has no rolling window, so every
hold case had to become an OPERATOR's conversation — which is the truth about the feature, not a
fixture detail, and the design now says so in section 4.

## What already exists

Most of this feature is deletion plus one lookup. Worth knowing before estimating.

- **The routing key is already computed and already stored.** `turn_trust(conv, msgs)`
  (ffwatch.py:6375) answers `(tier, actor, reason)` from config and an authenticated id, writes
  it to `turn.trust_tier` / `turn.trust_actor`, and already special-cases `github_pr` (GitHub
  ids) and the local kinds (the unix account). Nothing about how trust is decided changes.
- **One block already holds one entry per person with one id per service.** `operator_ids(cfg,
  service)` is the only reader, and it cannot hand a caller from one service an id from another.
  Routing is a third call to it.
- **A run already records which account paid.** `run.claude_key` (schema v15) holds a variable
  name, never a token, and `ffweb` already renders it.
- **A spare already records the account it was staged with.** `pool_stage` writes
  `<pool dir>/claude-key` and `pool_claude_key(pool_id)` reads it back at launch, because a
  pooled run has never been able to re-choose.
- **The credential already travels as a name.** `--claude-key` goes on ffbox's argv, ffbox
  resolves it out of secrets.env itself and refuses a name the pool did not produce
  (ffbox:576-618). Nothing in argv or in the database holds a token.
- **The deferral already exists end to end.** `conversation_held` → `work_hold` → `claude_hold`,
  the `_hold_decided` latch that stops a held conversation re-running the gate every tick,
  `say_holding`'s once-per-hold Discord notice keyed on `local_id`, `log_hold`'s
  once-per-reason journal line, and `review_held` on the GitHub side before a request is spent.
- **The readings are already shared between the two processes.** `<state-dir>/claude-usage.json`,
  mode 0600, merged rather than overwritten, so ffweb reads what the daemon last measured.

## Decisions taken while writing these tasks

Ten places where the design's prose and the code did not line up. Settled here, and the design
was edited to match.

1. **`fullest_window` and `usable` are kept.** Section 7 offered them up for deletion along with
   `availability` and `remaining_fraction`. The per-key hold is `fullest_window(record)` plus
   `usable(record)` plus `seconds_to_reset` — the same three `emptiest` used internally — so
   only `pick`, `_why`, `emptiest`, `availability` and `remaining_fraction` go.
2. **A Discord refusal is a hold that speaks, not a gate.** Section 5 sent unresolvable routes
   through `gate_message`. That is wrong for the one case it matters in: `gate` is permanent, so
   an operator who fixed their config would find the request they asked about never ran. It
   takes the `say_holding` shape instead — the messages stay unclaimed and ungated, one outbound
   post carries a durable `local_id` so it is said once, and the pass after the config is fixed
   runs the request. `#codereview` keeps `refuse_review` and the cursor's `seen` list, because
   that path already consumes its trigger for every other refusal and the operator can comment
   again.
3. **The route is computed twice, and the design now says so.** `conversation_held` runs before
   `resettle()`, which can move a message into another conversation, so the batch the hold routes
   on is provisional. The authoritative key is computed at launch from the turn row's
   `trust_tier` / `trust_actor`, after the batch is settled. They disagree only when a resettle
   moves a message across a trust boundary mid-pass, and the cost is a turn admitted against the
   wrong key's window — the same class of staleness the reading already carries.
4. **`create_turn` needs its `pending_messages` read moved up.** It reads them at 6882, below
   the hold at 6849. The hold now needs the authors, so the read moves above it and the existing
   call site takes the same list. `resettle()` sits between the two, so the list is re-read after
   it exactly as today.
5. **A local conversation with no opener routes to nothing, not to an operator called "shell".**
   `turn_trust` falls back to `conv["kind"]` when `opener_discord_id` is empty, so the actor can
   literally be the string `shell` or `web`. `claude_route` treats an actor equal to the kind as
   unresolvable rather than looking it up.
6. **`operator_ids` grows a per-service validation rule, and the digit rule stays where it is.**
   `shell` accepts a non-empty name; `discord` and `github` keep "digits only", because
   `is_operator` and `is_github_operator` are trust checks against a renameable handle and that
   argument is unchanged. One dict of validators, not one relaxed rule for everything.
7. **The API key is a row in `ClaudeKeys.read()`, not a separate probe.** The daemon builds one
   `ClaudeKeys` in `Watcher.__init__` (ffwatch.py:4381) from the `claude` block, and ffweb reads
   its answers out of the shared store. A key measured anywhere else would put the page and the
   daemon back to disagreeing, which is the thing `claude_keys.py` was extracted to stop.
8. **A shell or web prompt is refused at launch, not at a hold.** `conversation_held` reaches a
   Discord conversation and nothing else, on purpose: there is a person at a terminal and
   `claim_turns` never offers a local conversation twice. So the third venue in section 5 is a
   failed turn whose `error` carries the sentence, which is what the conversations page already
   renders.
9. **`secrets_ready()` is the preflight, and `test.sh` does not run the ffbox shell test.**
   The design asked for a preflight conditional on "any watch configured for player traffic",
   which stage 3 is in no position to read; `secrets_ready()` already answers the shape of that
   question in shell and gains one more variable. And `ffbox/test.sh` runs seven suites,
   `test_container_credential.sh` not among them — see H15.
10. **A box with no API key stages no ffagent spare.** Not in the design. `pool_stage_key`
   answers `None` rather than naming a variable ffbox would refuse to resolve, so the box logs
   once instead of failing a staging every pass and backing off.

## Phase A — what the keys are (M)

`claude_keys.py`.

- **A1.** `claude_subscriptions(env=None, secrets_path=None)` replaces `claude_token_pool`:
  the same numbered scan, returning `(name, token, rate, label, key_id)` per slot, where
  `key_id` is the declared `CLAUDE_CODE_NAME_TOKEN<n>` and falls back to the slot number as a
  string. Keep the unnumbered legacy spelling and keep "a gap is not the end of the list".
- **A2.** `default_api_key(env=None, secrets_path=None)` → `("ANTHROPIC_API_KEY", token)` or
  `None`. Same filtered read of secrets.env — add `ANTHROPIC_API_KEY` to the `wanted` set in
  `_claude_secrets_file`, and nothing else.
- **A3.** `subscription_named(key_id, subs)` → the variable name, `None` for no match, and a
  distinguishable answer for an ambiguous one (two slots declaring the same name). Case-folded
  and stripped on both sides; a numeric `key_id` also matches the slot number.
- **A4.** `ClaudeKeys.read` returns the API key as a record with `windows: []`,
  `source: "api key"` and a new `kind` field (`"subscription"` or `"api_key"`) on every record.
  Its probe is a one-token Haiku call with `x-api-key` rather than `Authorization: Bearer`, and
  no `anthropic-beta: oauth-2025-04-20`; it never asks `/api/oauth/usage` or `/api/oauth/profile`,
  which do not exist for it. Reachable, unreachable, and the error string are the whole of what
  it can say.
- **A5.** Delete `pick`, `_why`, `emptiest`, `availability`, `remaining_fraction`. Keep
  `window_of`, `seconds_to_reset`, `utilization`, `fullest_window`, `usable`, `claude_plan`,
  `token_fingerprint`, `_rough`, the store and the reset memory.
- **A6.** Rewrite the module header. It is called "The Claude subscription pool" and its first
  paragraph is about a decision that no longer happens.

## Phase B — the route (M)

`ffwatch.py`, beside `operator_ids`.

- **B1.** `operator_ids(cfg, service)` takes its validator from a per-service table:
  `discord` and `github` digits-only as today, `shell` a non-empty string. The
  `discord.trust.operators` fallback stays and stays Discord-only.
- **B2.** `operator_for(cfg, service, actor)` → the operator's name or `None`. The inverse of
  `operator_ids`, which `turn_trust` builds by hand today (`by_id`) and which routing needs.
- **B3.** `claude_key_id(cfg, name)` → what that operator wrote in `operators.<name>.claude`,
  stripped, or `""`.
- **B4.** `claude_route(cfg, tier, actor, kind, keys)` → `(variable_name, why)` or
  `(None, refusal_sentence)`. `keys` is `(subscriptions, api_key)` — A1's list and A2's answer,
  read once by the caller. The whole routing table in one function, with no database and no
  `Watcher`:
  - `kind` is `github_pr` → look the actor up in the GitHub ids.
  - `kind` is a local kind → look the actor up in the `shell` ids, unless the actor equals the
    kind (decision 5), which is unresolvable.
  - otherwise → look the actor up in the Discord ids.
  - a player, or an actor in no table → the API key, or a refusal when there is none.
  - an operator with no `claude` id, an id naming no slot, or an ambiguous id → a refusal whose
    sentence names the operator, the id they wrote and which of the three it was.
- **B5.** `Watcher.claude_route_for(conv, msgs)` and `Watcher.claude_route_for_turn(turn)`:
  the two call shapes, both resolving `turn_trust` (or the stored `trust_tier` / `trust_actor`)
  and then calling B4 with the pool read once per call.
- **B6.** Startup check: on the first pass, log one line per operator saying which variable their
  id resolved to, and a `WARNING` per operator whose id resolved to nothing. Latched like
  `_pool_squeeze_logged` so a misconfigured box says it once rather than once a tick.

## Phase C — spending it (M)

- **C1.** `launch`: replace `claude_key, claude_why = self.pick_claude_key()` with
  `claude_route_for_turn(turn)`. A `None` key normally reaches here only from a local
  conversation, which `conversation_held` does not cover — a Discord one was held and a review
  was refused before a turn existed. Anything else getting here means the config changed between
  the hold and the launch, which is the same answer. It raises rather than falling back, in the
  shape `BranchUnavailable` already uses for "this turn cannot start and nothing was run", so the
  sentence lands on `turn.error` where the terminal and the conversations page both read it.
- **C2.** The pooled branch keeps reading `pool_claude_key(pool_id)`, which is now guaranteed to
  equal the routed key because `pool_claim_for` matched on it (Phase E).
- **C3.** `classifier_invocation`: drop the `key` parameter, drop `active_claude_token`, and stop
  setting `CLAUDE_TOKEN_PREFIX` in the child environment. The existing `ANTHROPIC_API_KEY`
  passthrough (ffwatch.py:3527) already hands it the API key, because the daemon's unit reads
  secrets.env. Drop `key=` from `run_classifier` and `should_engage_for` and from their two call
  sites — the selector at 5937 and the gate at 6919. The third `pick_claude_key()` caller, the
  staging one at 7652, becomes `pool_stage_key` in Phase E rather than losing an argument.
- **C4.** `ffbox`: `ANTHROPIC_API_KEY` becomes a legal `--claude-key` value. The resolution loop
  keeps its allowlist shape — a name the loop did not produce is still refused with exit 78 —
  and exports `ANTHROPIC_API_KEY` for that value and `CLAUDE_CODE_OAUTH_TOKEN` for a slot,
  never both. `--claude-key ANTHROPIC_API_KEY` against an empty or absent variable exits 78; it
  must not fall through to "the first non-empty slot", which is a run silently billed to
  somebody's subscription.
- **C5.** `ffbox`: the container's `-e` list carries whichever of the two was resolved. Both
  `docker run` blocks — the cold one at 1305 and the staged one — take the same treatment, and
  the usage text for `--claude-key` says what the API key value means.
- **C6.** `max_budget_usd` moves into the class blocks (`_class_blocks`, defaulting to the
  top-level value so an existing config is unchanged), and ffagent's default drops. It is the
  only ceiling on a metered run now. Keep the top-level key readable so a box that sets it there
  still works.

## Phase D — the holds (M)

- **D1.** `claude_hold(what, key, fresh=False)`: find the record whose `name` is `key`, answer
  `(0, "")` when it is missing, unusable, or an API key (no window to be over), else
  `fullest_window` against the configured share and `seconds_to_reset` for the countdown. Delete
  the `emptiest` call and the "the emptiest account decides" paragraph in `DEFAULTS["claude"]`.
- **D2.** `work_hold(what, key, fresh=False)`: quiet hours first, unchanged, then D1.
- **D3.** `conversation_held(conv, msgs)` takes the messages, resolves the route, and returns
  `(verdict, secs, why, key)` where `verdict` is `run`, `hold` or `refused` — three outcomes
  where there were two, and a caller that reads only `secs` would not be able to tell the last
  two apart. The refusal case calls a new `say_route_refused(conv, msgs, why)`: `record_outbound`
  with `local_id = f"claudekey:{conv['id']}:{turns}"`, silent, replying to the last message, the
  same shape as `say_holding`, leaving the messages exactly where they are.
- **D4.** `create_turn`: read `pending_messages` above the hold (decision 4), pass them in, and
  keep the `_hold_decided` latch covering the refusal case too so a misconfigured operator does
  not re-run the gate on every tick.
- **D5.** `review_held(comment, triggers)` routes on the comment's author before it holds, and
  gains a third outcome: an unresolvable route refuses through `refuse_review` and the comment
  goes into `seen`, exactly as an unadoptable branch does today.
- **D6.** `claude_records(fresh=...)`'s "should this box read anything at all" test loses
  `claude_spreads()` and keeps `claude_holds()`. A box with the holds off and one API key makes
  no outbound reading at all, which is what a box with no subscriptions should do.

## Phase E — warm spares by key (M)

- **E1.** `pool_stage(agent_class, ref, tier, ttl_secs, claude_key)` takes the key rather than
  choosing one, and writes it to `<pool dir>/claude-key` as today. The `ffwatch pool stage` CLI
  path (ffwatch.py:16130) gains `--claude-key`, defaulting to E3's answer for that class.
- **E2.** `pool_claim_for(ref, agent_class, key)` and `pool_would_serve(ref, agent_class, key)`
  both match the staged key as well as the class and the branch. A miss is a cold launch, which
  is what a pool miss has always been.
- **E3.** `pool_stage_key(agent_class)`: for ffagent, `ANTHROPIC_API_KEY`, or `None` when that
  variable is not set — a box with no API key logs once instead of asking ffbox for a container
  it would refuse to create. For ffdev, the routed keys of that class's recent runs, most recent
  first, skipping any that already has a warm spare; the query is `run` joined to `turn` on
  `COALESCE(ended_at, started_at, queued_at)` inside a window, mirroring `pool_branch_activity`.
  `None` when no operator has a resolvable key, which means that class stages nothing.
- **E4.** `keep_pool` counts held warm spares per `(class, key)` and stages against E3's answer.
  A class whose key comes back `None` is skipped with a latched log line, the way
  `_pool_squeeze_logged` handles a memory squeeze.
- **E5.** `_pool_stage_after` is keyed `(class, branch, key)`, so one operator's failing staging
  does not stop another operator's spare being staged.

## Phase F — the page and the status line (S)

- **F1.** `page_claude`: one row per subscription headed by the operator who claims it, an
  API-key row that says "metered, no window" instead of two empty bars, an unclaimed
  subscription marked as such, and an operator whose id resolved to nothing listed with the id
  they wrote and the reason. Its docstring's "every key is spent, and ffwatch chooses per turn"
  paragraph is now wrong and is rewritten.
- **F2.** `claude_status`: drop the "next turn goes to X" line and the `OVER CAP` column; print
  one line per operator — who, which variable, both windows, whether it is over a hold — plus
  the API-key line and any unresolved id.
- **F3.** `ffweb`'s import list from `claude_keys` loses whatever Phase A deleted.

## Phase G — configuration and documentation (M)

- **G1.** `DEFAULTS["claude"]`: delete `spread` and `five_hour_cap` and their comment blocks;
  rewrite the block's header comment, which describes the chooser. On load, log once if either
  deleted key is still present in the file.
- **G2.** `05-discord-setup.sh`: seed `operators` entries with `shell` and `claude` fields in the
  template, so a fresh box shows the shape.
- **G3.** `ffbox/secrets.env.example`: `ANTHROPIC_API_KEY` with the paragraph saying what it pays
  for; the `CLAUDE_CODE_NAME_TOKEN<n>` comment says it is now the subscription id and not only a
  label; the `CLAUDE_CODE_RATE_TOKEN<n>` comment says the plan is now printed and not weighed.
- **G4.** `setup.sh`: prompt for the API key beside the `claude setup-token` prompt, and add
  `ANTHROPIC_API_KEY` to `secrets_ready()`, which today calls a file ready when any one slot is
  filled.
- **G5.** `ffbox/config.md`: `operators` gains `shell` and `claude`; the `claude` section loses
  two keys and rewrites what the holds ask; the routing table from the design goes in as the
  reference. **Required in the same commit** — CLAUDE.md says the config's shape and this file
  move together.
- **G6.** `ffbox/README.md`: "Spending the pool" is replaced rather than amended; the secrets
  table gains `ANTHROPIC_API_KEY` and re-describes the three `CLAUDE_CODE_*` families.
- **G7.** `ffbox/CREDENTIALS.md`: the API key is a fourth credential on the box, and its blast
  radius (metered spend, no repository access) is worth a paragraph beside the other three.

## Phase H — tests (L)

Offline. `test_ffwatch.py` unless said otherwise, each added to `main()`'s list.

- **H1.** `claude_route` over the whole table: player to the API key, Discord operator to their
  slot, `github_pr` resolving through the GitHub ids and not the Discord ones, a shell prompt
  through the `shell` ids, a mixed-author batch to the API key, an autofix turn inheriting its
  conversation's answer.
- **H2.** Four of the five refusals: no `claude` field, an id naming no slot, an id two slots
  claim, and a player path with no `ANTHROPIC_API_KEY`. Each sentence names what was wrong. The
  fifth is H4.
- **H3.** Ids: `"Loth"`, `"loth"` and `" Loth "` all resolve to slot 2; `"2"` resolves to slot 2
  by number; a slot with no `CLAUDE_CODE_NAME_TOKEN` is still reachable by its number.
- **H4.** A local conversation whose actor is the bare kind refuses rather than resolving.
- **H5.** `operator_ids` still drops a non-digit `discord` and a non-digit `github`, and keeps a
  non-digit `shell`.
- **H6.** The per-key hold: an operator over `new_conversation_hold_pct` holds their own request
  while a player's request runs in the same pass; an API-key record never holds.
- **H7.** The refusal is said once — a second pass over the same conversation queues no second
  outbound — and the messages stay unclaimed and ungated, so a pass after the config is fixed
  creates the turn.
- **H8.** `review_held` refuses an unresolvable operator through `refuse_review` and marks the
  comment seen.
- **H9.** `pool_claim_for` refuses a spare staged on another key and accepts one staged on the
  same key; `pool_would_serve` agrees with it on both.
- **H10.** `pool_stage_key` returns the API key for ffagent, the most recent operator's key for
  ffdev, and `None` when no operator has one; `keep_pool` stages one spare per demanded key and
  stops at `idle_agents`.
- **H11.** The classifier's child environment carries `ANTHROPIC_API_KEY` and no
  `CLAUDE_CODE_OAUTH_TOKEN` of any spelling. Extends the existing environment assertion at
  test_ffwatch.py:14645.
- **H12.** In `test_ffweb.py`: an API-key row renders with no windows and does not blank the
  page; an unclaimed subscription is marked; an unresolved id shows the id it was given.
- **H13.** In `test_ffweb.py`: the existing `claude_token_pool` tests are rewritten against
  `claude_subscriptions` and keep every case they cover — the gap, the legacy unnumbered name,
  the rate parsing, the label parsing, the secrets-file read, the "no keys" answer.
- **H14.** ffbox: `bash -n`, plus the existing `test_container_credential.sh` extended to assert
  that `--claude-key ANTHROPIC_API_KEY` with an empty variable exits 78 rather than falling back
  to a slot.
- **H15.** Add `test_container_credential.sh` to `ffbox/test.sh`. It is not in the runner today,
  so H14 would otherwise be a suite nobody runs.

`sh ffbox/test.sh` runs the offline suite. Nothing here needs the daemon, a real container or the
network.

## Deploy (S, but do it in this order)

1. `ANTHROPIC_API_KEY` into secrets.env and `shell` / `claude` into every `operators` entry,
   BEFORE the code ships. Both files are hashed by `ffbox-update.timer` every five minutes and
   neither the old code nor the new minds a key it does not read.
2. Ship. Read `journalctl -u ffwatch` for the per-operator resolution lines from B6 before
   assuming it worked.
3. Verify on the box, in a throwaway container, that `claude -p --dangerously-skip-permissions`
   accepts `ANTHROPIC_API_KEY` from the environment without wanting the key approved
   (`customApiKeyResponses` in `.claude.json`). If it does want it, seed the approval into the
   container's claude directory, which both launch paths already create and mount. Do this
   before the first player turn runs on the API key, not after.
4. Expect the first player turn after the deploy to run cold: ffagent spares staged under the
   old code carry an OAuth slot and no longer match.
