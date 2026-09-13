# Per-user limits, the triggering author, and !lock: implementation tasks

Derived from `design/ffbox_per_user_limits_design.txt` (2026-09-13) after reading the paths it
changes: `ffwatch.py` (`DEFAULTS`, `rate_limited`, `turn_trust`, `create_turn`, `claim_turns`,
`schedule`, `record_blocked_reply`, `launch`, `run_ref`, `build_job`, `publish`,
`record_branch_pull_request`, `finish_run`, `insert_message`, `take_branch_directive`,
`take_fork_directive`, `demote_for_stranger`, `stranger_downgrade_class`, `title_from`,
`stop_workload`), `ffweb.py` (`page_conversations`, the conversation page header,
`REQUIRED_COLUMNS`), `05-discord-setup.sh`, `config.md`, `README.md` and
`docs/docker-security-model.md`.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more.

## Status: implemented and pushed.

One correction found while implementing: `record_branch_pull_request()` is only called from
branch adoption and the reconcile sweep, neither of which has a turn, so it stays on the
conversation's class like `reconcile_publication`. Only `publish()` reads the turn's class for
the pull request token. B5 and the design say so now.

## Cross-check against the design

Checked before implementing. Corrections, all made in the design:

- **The pool readers were named loosely.** `run_ref()` reads the class's `base_ref`, and
  `publish()` picks the pull request token by class. Both now read the turn's class.
  `reconcile_publication` and `send_github` have no turn and follow the conversation's class,
  which each new turn updates.
- **`claim_turns` would offer a locked conversation every tick.** Its query now leaves locked
  conversations out; the check at the top of `create_turn` stays as the backstop.
- **The design only stopped the reply of a run it stopped.** A run that finishes on its own
  after a lock is the same case. `finish_run` checks the lock however the run ended.
- **`!unlock` plus a question needs `addressed=1`**, as `!conv` sets, or an engage=mention channel
  swallows the question.
- **The schedule order was unstated.** The lock check comes before the rate limit, so a locked
  turn is never counted and never draws BLOCKED_NOTE.
- **Docs and tests were under-listed.** `config.md`'s "Two halves" table, the `user_pool` section,
  four README passages and `docs/docker-security-model.md` all state the one-way demotion. Six
  existing tests assert the old rules. All are listed now.
- **ffweb cannot show a name from an id on its own.** It reads the operators block for itself,
  so `locked_by` stays an id and the page resolves the name.
- **`fenced_history` is not affected.** It frames a fork's prompt, not its pool. Said in the design.

## A. Run budget and defaults

- **A1 (S).** `DEFAULTS["max_budget_usd"]` 10 -> 30. Update the comments that quote $10.
- **A2 (S).** `DEFAULTS["rate_limits"]`: `player` 5 -> 15, add `"users": {}`. Rewrite the comment
  block above it to say per person and describe `users`.
- **A3 (S).** `05-discord-setup.sh` seeded template: `player` 15, `"users": {}`, comment updated.

## B. The triggering author

- **B1 (S).** `turn_trust()`: actor is `authors[-1]`; tier is operator when that id is an
  operator. Local and GitHub branches unchanged. Docstring rewritten.
- **B2 (S).** Schema: `("turn", "agent_class", "TEXT")` in the added-columns list.
- **B3 (M).** `create_turn()`: write `turn.agent_class` = `discord_agent_class(cfg, actor)` for a
  Discord conversation, the conversation's class for local and GitHub. Set
  `conversation.agent_class` to the same value.
- **B4 (S).** A helper `turn_class(turn, conv)`: the turn's `agent_class` if it is a known class,
  else `conversation_class(conv)`.
- **B5 (M).** Read the turn's class in `launch()`, `schedule()` (ceiling and `pool_would_serve`),
  `run_ref()`, `build_job()` and `publish()`. Update the long
  comment in `launch()` that calls the fence a conversation property.
- **B6 (S).** Remove `demote_for_stranger()`, its call in `insert_message`, and
  `stranger_downgrade_class()`. Fix the comments that name them (`discord_agent_class`,
  `upsert_conversation`, the budget-class block).

## C. Per-user turn limit

- **C1 (S).** `user_limit(cfg, actor)`: `(True, limit)` for the first `rate_limits.users` entry
  whose `discord` matches, else `(False, None)`. Logs a duplicate id once per process.
- **C2 (S).** `rate_limited(tier, actor="")`: refuse `send` and `users` as tiers; limit from C1,
  else `rate_limits[tier]`; count turns by `COALESCE(trust_actor,'')` in the last 24 hours.
- **C3 (S).** `schedule()` passes `turn["trust_actor"]`.
- **C4 (S).** `record_blocked_reply()` marker `blocked:<channel>:<actor>`; docstring updated.

## D. !lock and !unlock

- **D1 (S).** Schema: `conversation.locked INTEGER NOT NULL DEFAULT 0`, `locked_by TEXT`,
  `locked_at TEXT`.
- **D2 (S).** `LOCK_DIRECTIVE_RE` (`^\s*!(lock|unlock)\s*$`, multiline), `lock_directive(content)`
  returning `"lock"`, `"unlock"` or None, and `is_only_lock_directive(content)`.
- **D3 (S).** `TITLE_DIRECTIVE_PREFIX_RE` gains `!lock` and `!unlock`.
- **D4 (S).** `insert_message`: the provisional directive gate also covers `lock_directive`.
- **D5 (M).** `take_lock_directive(conv_id, message_id, author, content)`, called before
  `take_branch_directive`. Operators only, silent otherwise; not local or GitHub. Lock: set
  the columns, post the lock message with thread/conversation, end queued turns `blocked`, stop a
  running turn's container with `stop_workload`, gate the message `lock_directive`. Unlock: clear
  the columns, post the unlock message, gate the message when it is only the directive, else set
  `addressed=1`. A no-op lock or unlock posts nothing but still gates a bare directive.
- **D6 (S).** `take_branch_directive` and `take_fork_directive` return early on a locked
  conversation.
- **D7 (S).** `claim_turns` query: `AND COALESCE(c.locked,0)=0`. `create_turn`: return None first
  thing when locked.
- **D8 (S).** `schedule()`: select `c.locked AS conv_locked`; a locked turn ends `blocked`
  ("the thread is locked") before the rate limit, with no note.
- **D9 (S).** `finish_run()`: on a locked conversation, skip `publish`, `reconcile_publication`
  and `record_reply` (which carries the private half). Still record the run and finish the turn.

## E. ffweb

- **E1 (S).** `REQUIRED_COLUMNS["conversation"]` gains `locked`.
- **E2 (S).** `page_conversations`: a "locked" column after "state".
- **E3 (S).** Conversation page header: "locked by <name> at <time>", the name from the
  operators block ffweb already reads, else the id.

## F. Config and docs

- **F1 (S).** Live `~/.config/ffbox/config.json`: `rate_limits.player` 15, `"users": {}`. After the
  code is pushed.
- **F2 (M).** `config.md`: `rate_limits` section (per person, `users`, lookup order), both
  `max_budget_usd` rows, the "Two halves" table and text, the `user_pool`/`operator_pool` section.
- **F3 (M).** `README.md`: the fence passages (around lines 1095, 1283, 1947, 2313), the rate
  limit line, and `!lock`/`!unlock` beside `!branch` and `!conv`.
- **F4 (S).** `docs/docker-security-model.md`, "The class that is not fenced": the triggering
  author picks the class, and `!lock` is the brake.

## G. Tests

- **G1 (S).** DEFAULTS: `player == 15`, `users == {}`, `max_budget_usd == 30`.
- **G2 (M).** `test_fix_lane_rate_limit`: per actor, a second player unaffected, overrides
  (raise, 0, null), `users` not a tier.
- **G3 (S).** `test_a_capped_lane_tells_a_channel_once_not_every_asker`: per actor.
- **G4 (M).** Rewrite `test_a_player_never_inherits_an_operators_clearance` and
  `test_a_discord_conversation_opens_in_the_pool_its_opener_earns` to the triggering-author rule
  (A, B then O is O's operator turn in ffdev; O then A is A's player turn in ffagent; a stranger
  posting does not change the class). Delete
  `test_where_a_conversation_goes_when_a_stranger_speaks_in_it`.
- **G5 (M).** Rewrite `test_an_operators_request_in_a_players_thread_gets_the_clock_and_not_the_network`:
  the operator's request now runs in ffdev on ffdev's clocks.
- **G6 (S).** Fix the comment on the mixed-batch route check in
  `test_everybody_else_is_billed_to_the_metered_default`.
- **G7 (M).** Lock tests: operator lock posts once with the right noun; player lock ignored;
  messages while locked create no turn and no classifier call; queued turn blocked; a finishing
  run posts nothing; unlock posts, and pending messages get a turn whose history holds them;
  unlock plus a question answers it; titles drop the directives.
- **G8 (S).** `test_ffweb.py`: the locked column and header.
- **G9 (S).** `sh ffbox/test.sh` passes.
