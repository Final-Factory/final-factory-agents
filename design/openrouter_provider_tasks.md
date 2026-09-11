# OpenRouter as a credential type: implementation tasks

Derived from `design/openrouter_provider_design.txt` revision 6 (2026-09-10), against the code at
d7e4053. The code read:

- `claude_keys.py`: the slot scan, `slot_ids`, `subscription_named`, `default_api_key`,
  `_claude_secrets_file`, `ClaudeKeys.__init__`, `_probe`, `_probe_api`, `_load`, `read`.
- `ffwatch.py`, routing: `claude_route`, `claude_key_id`, `claude_keys_now`, `claude_route_for`,
  `claude_route_for_turn`, `claude_routes`, `claude_route_for_comment`.
- `ffwatch.py`, classification: `classifier_invocation`, `classifier_attempt`, `run_classifier`,
  `should_engage`, `should_engage_for`, `failed_open`, `model_selection`, `select_for_turn`,
  `resettle`.
- `ffwatch.py`, turns and holds: `create_turn`, `claim_turns`, `conversation_held`,
  `hold_until_morning`, `say_holding`, `say_route_refused`, `claude_hold`, `work_hold`,
  `claude_records`, `claude_status`, `review_held`, `schedule`, `_launch_guarded`, `launch`,
  `finish_run`, `result_failure_detail`.
- `ffwatch.py`, pool and schema: `pool_stage_key`, `pool_claim_for`, `init_schema`,
  `ADDED_COLUMNS`.
- `ffbox`'s `--claude-key` block and `RUN_ARGS`.
- `ffweb.py`'s `page_claude` and `claude_claims`.
- The Claude, hold and gate tests in `test_ffwatch.py`, `test_ffweb.py` and
  `test_container_credential.sh`.

Revision 6 of these tasks folds in a cross-check of revision 5. What changed:
- **State.** Health and flags moved to the database.
- **Failures.** The failure kinds are read from the CLI's error fields, and a 429 never counts.
- **Queued turns.** `schedule` is where a turn on a down credential stays queued.
- **Routing order.** `launch` routes before `build_job`.
- **Missed callers.** Added `claude_route_for_comment`, `claude_claims` and `review_held`.
- **Deploy.** `config.md` is split across the two deploys.
- **Tests.** The tests that depend on the gate failing open are named.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more.

## Status, 2026-09-10

**Not started.** Phases A and B ship first and alone, and do not depend on Phase 0. Phase 0 is by
hand and gates the deploy of phases C onward.

## What already exists

- **Every request already has one payer.** `claude_route(cfg, tier, actor, kind, keys)`
  (ffwatch.py:1944) returns a variable name or a refusal, from the trust tier and an authenticated
  id. How trust is decided does not change.
- **A refusal and a hold already wait without writing anything.** `conversation_held`
  (ffwatch.py:7180) returns `(verdict, secs, why, key)` with `run`, `hold` or `refused`, and
  `create_turn` leaves the messages unclaimed and ungated for the last two. Quiet hours do the same
  above `resettle` (ffwatch.py:7468).
- **API errors are already recognised.** `result_failure_detail` (ffwatch.py:17231) reads
  `is_error`, `terminal_reason: api_error` and `api_error_status` out of a run's `result.json`, and
  documents the session-limit shape: a 429 with `subtype: success`.
- **A credential already travels as a name.** `--claude-key` carries a variable name, ffbox
  resolves it out of secrets.env, forwards it with a bare `-e NAME`, and refuses a name its own scan
  did not find. `CLAUDE_ENV_ARGS` already lets the forwarded names differ per credential.
- **A run and a spare already record their credential.** `run.claude_key` holds the variable name;
  `<pool dir>/claude-key` holds the spare's, and `pool_matches` (ffwatch.py:9159) compares it.
- **Two record kinds already exist.** `KIND_SUBSCRIPTION` and `KIND_API_KEY` (claude_keys.py:143)
  flow through `ClaudeKeys.read`, the shared store and `page_claude`.
- **The lost-transcript path already exists.** `build_job`'s `resume_summary`.
- **Tables and columns migrate on start.** `init_schema` runs `ffwatch_schema.sql` (every statement
  `IF NOT EXISTS`) and then `ADDED_COLUMNS`.

## Decisions taken while writing these tasks

1. **Health counts calls, not readings.** `test_a_hold_that_cannot_read_the_windows_runs_the_work`
   stays green: an unreadable window reading still runs the work.
2. **"Could need a classification" is decided above `resettle`, conservatively.** The selector
   could run when the conversation is non-thread and non-local and holds a message routed `recent`.
   The gate could run when the kind is outside GATE_BYPASS_KINDS, the channel is `engage: all`, and
   `always_a_turn` is false. All of it is readable from config and the pending rows before anything
   moves.
3. **Health and flags live in the database.** A `credential_health` table and five `conversation`
   columns, so `ffwatch status` and ffweb (separate processes) read what the daemon wrote, and a
   restart does not forget a down credential.
4. **The failure kind rides on the error string.** `ClassifierFailure(str)` carries `.kind`, so
   every existing caller and test that treats the error as a string keeps working, and
   `run_classifier` keeps its `(parsed, error)` shape.
5. **The classifier credential is resolved at module level.** `classifier_credential(cfg, creds)`
   is called inside `classifier_invocation`, so none of the module-level classifier functions grows
   a parameter, and the Watcher calls the same function to know whose health to report to.
6. **A `down` turn is skipped in `schedule`, not in `launch`.** `schedule` has already marked the
   turn running and taken the lock by the time `launch` runs, so the check sits beside `sched_key`
   (ffwatch.py:9255), with `continue` rather than `break`.
7. **The OpenRouter probe's token budget is a constant** (`OPENROUTER_PROBE_MAX_TOKENS`), set from
   0d.
8. **`CLAUDE_API_KEY_NAME` stays**, meaning "the default when `claude.default` is unset".
9. **The session-crossing rule is conditional.** G3 is built only for crossings 0e shows do not
   resume.
10. **`approve_before_send` stays box-wide.** Per-route approval is an open decision, not a task.
11. **Notices only where `always_a_turn` says a turn was coming**, and the outage notice has its own
   `down:` marker.

## Phase 0 — measure, by hand (M)

Nothing here ships. Each result is written into the design's next revision. Gates the deploy of
phases C onward.

- **0a.** The classifications on Flash against the stored answers (design 13a).
- **0b.** Player turns on an OpenRouter credential wired into a scratch ffbox, a screenshot report
  among them (13b).
- **0c.** Deliberate failures (402, a refused model, 503, 401): the classifier's exit code and
  envelope, and the container's `result.json`, `claude.log` and `stream.jsonl` (13c). Confirms A1's
  and B2's mapping on OpenRouter; Anthropic's shapes are already in `result_failure_detail`.
- **0d.** `GET /api/v1/key` fields and cost, and the smallest `max_tokens` Flash answers with (13d).
- **0e.** Session crossings (13e).
- **0f.** Last week's threads replayed on Flash (13f).
- **0g.** One operator dev turn on an OpenRouter credential in ffdev (13g).

## Phase A — a classification that fails waits (M)

`ffwatch.py`, `ffwatch_schema.sql`. Ships with Phase B.

- **A1.** `ClassifierFailure(str)` with `.kind` in `refused`, `outage`, `budget`, `limited`,
  `unusable` (decision 4). `classifier_attempt` parses stdout as an envelope whether or not the exit
  code is zero. It reads `is_error`, `terminal_reason` and `api_error_status`:
  - 402 is `budget`.
  - 429 is `limited`.
  - 401, 403, 5xx, or an API error with no status, is `outage`.
  - No parseable envelope, a timeout or an OSError is also `outage`.
  - An envelope whose answer does not validate is `unusable`.
  - A credential that does not resolve is `refused` (in Phase A that means no `ANTHROPIC_API_KEY`).
- **A2.** `run_classifier` retries under `--json-schema` only after an `unusable` first attempt.
- **A3.** `CLASSIFY_HOLD`: a small class carrying the failure. `should_engage` returns a
  classification dict with `status: "hold"` and the failure, instead of calling `failed_open`
  (including its "gate output did not match the schema" branch). `should_engage_for` passes it
  through, returning `(None, cls)`.
- **A4.** `model_selection` returns `CLASSIFY_HOLD(failure)` on any failure. An answer that
  validates but names an id that was not offered still returns `(None, None)`. `select_for_turn`
  passes it up; `resettle` returns it without moving or stamping anything.
- **A5.** `create_turn`:
  - It calls `resettle` into a variable and returns via `classify_held(conv, failure)` when the
    result is a `CLASSIFY_HOLD`.
  - It checks the gate's classification for `status == "hold"` before the decline test, since
    `None` is falsy and would otherwise decline.
  - Delete the `fc` handling: the `failed_open` log line and both `if not fc` guards. New turns write
    `failed_closed=0` and a NULL reason.
  - On a classification that succeeds (declined or engaged), clear the conversation's backoff.
- **A6.** `classify_held(conv, failure)`:
  - `log_hold` once.
  - Report the failure to the classifier credential's health (B2).
  - When the kind is `limited` or `unusable`, or is `outage` and the credential is still up after
    reporting, bump `conversation.classify_failures`, set `classify_retry_at` (`first_secs` doubling
    to `max_secs`) and `classify_error`.
  - At `flag_after`, set `classify_flagged_at` and log one WARNING.
  - Return None.
- **A7.** The backoff check sits in `create_turn` after quiet hours and before `conversation_held`:
  a conversation whose `classify_retry_at` is in the future returns None, unless `gate_released_by`
  is set.
- **A8.** `ffwatch release <conversation>`, a subcommand beside `approve`. It sets
  `conversation.gate_released_by` to the unix user and clears `classify_retry_at`.
  - In `create_turn` a released conversation is treated as `forced` (no gate).
  - A `CLASSIFY_HOLD` from `resettle` keeps the deterministic answer instead of holding.
  - The column and the three `classify_*` counters are cleared when the turn row is written.
- **A9.** Schema: `ADDED_COLUMNS` gains `conversation.classify_failures INTEGER NOT NULL DEFAULT 0`,
  `classify_retry_at TEXT`, `classify_error TEXT`, `classify_flagged_at TEXT`,
  `gate_released_by TEXT`. `SCHEMA_VERSION` 21, with a comment beside the v20 one.
- **A10.** `DEFAULTS["claude"]["classify_retry"] = {first_secs: 60, max_secs: 1800, flag_after: 5}`.

## Phase B — the health hold (M)

`ffwatch.py`, `ffwatch_schema.sql`, `claude_keys.py`. Ships with Phase A.

- **B1.** Table `credential_health`, in `ffwatch_schema.sql`: `name TEXT PRIMARY KEY`, `state TEXT
  NOT NULL DEFAULT 'up'`, `failures INTEGER NOT NULL DEFAULT 0`, `down_since TEXT`, `until TEXT`,
  `next_probe_at TEXT`, `last_error TEXT`, `updated_at TEXT`. `Watcher.health(name)` reads it, and
  a missing row is `up`. `Watcher.record_call(name, failure_or_none)` is the one writer:
  - A success resets `failures` and, if the credential was down, sets it `up`.
  - `outage` increments; at `after_failures` the credential goes `down` with `next_probe_at` =
    now + `probe_secs`.
  - `budget` goes `down` at once.
  - `refused`, `limited` and `unusable` write nothing.
- **B2.** Reporters:
  - Every classification reports to `classifier_credential`'s name (in Phase A that is always
    `ANTHROPIC_API_KEY`).
  - `finish_run` reports a failed run with `result.json`'s `terminal_reason: api_error` by the same
    status mapping (402 `budget`; 401, 403, 5xx or no status `outage`; 429 nothing).
  - A run that ended `done` reports success.
  - The credential reported is the run's `claude_key`.
- **B3.** `conversation_held`:
  - `down` (with the hold's `until`, or None) when the route credential is down.
  - `down` when the classifier's credential is down and the conversation could need a
    classification (decision 2).
  - `refused` when it could need one and the classifier credential does not resolve.
  - `create_turn` returns on `down` ABOVE `resettle`, via `hold_down(conv, secs)`, which neither
    adds to `_hold_decided` nor calls a model.
- **B4.** `ClaudeKeys.probe_one(name, token, kind)`: no cache, no store write, independent of
  whether a window hold is configured. Subscription through `_probe`, API key through `_probe_api`,
  OpenRouter through C6. Returns `(ok, error)`.
- **B5.** Probing: in the daemon loop, for each `down` credential whose `next_probe_at` has passed
  and whose `until` is NULL or past, call `probe_one`. Success sets it `up`; failure pushes
  `next_probe_at` on by `probe_secs`. Done on the loop's thread with `timeout_secs`, one credential
  per pass at most, so a dead network cannot stall the loop for longer than one timeout.
- **B6.** `schedule` skips a queued turn whose `sched_key` is down, with `continue` (decision 6).
- **B7.** `review_held` returns True, with a `log_hold` line, when the operator's route credential
  is down.
- **B8.** Notices, only when `always_a_turn(conv, msgs)` (decision 11):
  - A `down` with an `until` calls `say_holding` with that duration.
  - A `down` without one calls `say_waiting(conv, msgs)` once `down_since` is `notice_after_secs`
    old, under `down:<conversation>:<turns>`. The wording is the design's open decision. The task
    ships a placeholder that must be replaced before step 6 of the deploy.
- **B9.** `log_hold` lines for a credential going `down` and coming back `up`, once each.
  `DEFAULTS["claude"]["health"] = {after_failures: 2, probe_secs: 60, notice_after_secs: 600}`.
- **B10.** `claude_status` gains one line per credential in `credential_health` that is not `up`,
  and the flagged conversations with their last error and the release command.

## Phase C — credential types (L)

`claude_keys.py`.

- **C1.** Constants: `ANTHROPIC_NAME_PREFIX = "ANTHROPIC_NAME_KEY"`, `OPENROUTER_KEY_PREFIX =
  "OPENROUTER_API_KEY"`, `OPENROUTER_NAME_PREFIX = "OPENROUTER_NAME_KEY"`, `OPENROUTER_MODEL_PREFIX`,
  `OPENROUTER_URL_PREFIX`, `OPENROUTER_DEFAULT_MODEL = "z-ai/glm-5.3-flash"`,
  `OPENROUTER_DEFAULT_URL = "https://openrouter.ai/api"`, `OPENROUTER_PROBE_MAX_TOKENS`,
  `KIND_OPENROUTER = "openrouter"`, `metered(kind)`, and `credential_kind(name)` from the prefix.
- **C2.** `claude_credentials(env=None, secrets_path=None)` returns
  `(name, token, kind, label, rate, model, url)` per credential, in family then slot order:
  - Subscriptions exactly as `_claude_tokens_from` reads them, legacy spelling included.
  - The unnumbered `ANTHROPIC_API_KEY` with the unnumbered `ANTHROPIC_NAME_KEY`, always, then
    `ANTHROPIC_API_KEY1..16` with their NAMEs.
  - `OPENROUTER_API_KEY1..16` with NAME, MODEL and URL, defaulted by C1.
  - "A gap is not the end" for every family. Environment first, then the filtered file.
- **C3.** `claude_subscriptions()` is the subscription filter over C2, so its callers are unchanged.
- **C4.** `slot_ids(name, label)` keeps its signature. It returns the declared name and the
  variable name for every kind, and the bare number only when `credential_kind(name)` is
  `subscription`. `credential_named(key_id, creds)` replaces `subscription_named`: found,
  "no slot", or "ambiguous: a, b", across all kinds.
- **C5.** `_claude_secrets_file` widens `wanted` to the C1 families, unnumbered and 1..16, and
  nothing else.
- **C6.** `ClaudeKeys(credentials=...)` replaces `tokens=` and `api=`. `read()` builds its list
  from C2. `_load` gains the OpenRouter branch:
  - `GET {url}/v1/key` with `Authorization: Bearer`, recording `limit`, `limit_remaining`,
    `limit_reset` and `usage_daily`.
  - One `OPENROUTER_PROBE_MAX_TOKENS` request to `{url}/v1/messages` for the slot's model.
  - A 401 is `unreachable`; a 429 is a live key.
  - A new seam, `openrouter_fetch`.
- **C7.** `default_api_key()` goes. `credential_for(name, creds)` returns one tuple.
- **C8.** Module header: the three kinds and the one namespace.

## Phase D — resolving the default and the classifier (M)

`ffwatch.py`.

- **D1.** Module-level `classifier_credential(cfg, creds)` and `default_credential(cfg, creds)`,
  each returning `(tuple, why)` or `(None, refusal)`. The default resolves `claude.default` through
  `credential_named`, or the unnumbered `ANTHROPIC_API_KEY` when unset. The classifier resolves
  `claude.classifier`, else the default. Either landing on a subscription is a refusal naming both
  the id and "must be metered".
- **D2.** `claude_keys_now()` returns `(credentials, default, classifier)`. `claude_route(cfg, tier,
  actor, kind, creds, default)` routes operators through `credential_named` and everybody else
  through `default`, with refusal sentences naming the id and variable.
- **D3.** Callers of the old pair move: `claude_route_for`, `claude_route_for_turn`,
  `claude_routes` (which also reports each credential's kind), `claude_route_for_comment`, and
  `pool_stage_key`, which today calls `default_api_key()` directly.
- **D4.** `classifier_invocation` resolves D1 itself. It fails with a `refused` `ClassifierFailure`
  when nothing resolves.
- **D5.** B2's classifier reporter and B3's classifier checks read D1 instead of the Phase A
  constant.
- **D6.** `DEFAULTS["claude"]` gains `default: None` and `classifier: None`.

## Phase E — the classifier's environment (S)

`ffwatch.py`.

- **E1.** `classifier_invocation` builds the environment from the design's section 5 table for the
  resolved kind. An `api_key` credential gives `ANTHROPIC_API_KEY`. `openrouter` gives
  `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, the four `ANTHROPIC_DEFAULT_*_MODEL` and an empty
  `ANTHROPIC_API_KEY`.
- **E2.** `ANTHROPIC_API_KEY` leaves the passthrough list. `LANG` and `LC_ALL` stay.
- **E3.** `--model` stays `cfg["classifier_model"]`.

## Phase F — the container (M)

`ffbox`, `ffbox/egress/allowlist.txt`.

- **F1.** The `--claude-key` scan covers the three families as C2 does, unnumbered spellings
  included, and records each found name's kind from its prefix and its slot number. Only a found
  name is accepted; an empty variable exits 78.
- **F2.** Per kind:
  - A subscription exports `CLAUDE_CODE_OAUTH_TOKEN`.
  - An API key exports `ANTHROPIC_API_KEY`.
  - An OpenRouter key exports `ANTHROPIC_AUTH_TOKEN`; `ANTHROPIC_BASE_URL` from
    `OPENROUTER_URL_KEY<n>` or the default; and the four model variables from
    `OPENROUTER_MODEL_KEY<n>` or the default.
  - The defaults are written once in ffbox beside the other mirrored constants, naming C1 as the
    original.
- **F3.** `CLAUDE_ENV_ARGS` forwards exactly that kind's names by bare `-e NAME`, plus the literal
  `-e ANTHROPIC_API_KEY=` for OpenRouter.
- **F4.** The no-flag path still takes the first subscription slot.
- **F5.** `openrouter.ai` on the allowlist, with a comment saying what it carries.
- **F6.** `--claude-key` usage text names the three kinds.

## Phase G — launch, spares and sessions (M)

`ffwatch.py`.

- **G1.** `launch` moves `claude_route_for_turn` and its refusal above `build_job`, and passes the
  resolved name into `build_job`. The pool claim stays where it is; `pool_matches` guarantees the
  spare holds the same name.
- **G2.** Spares: nothing beyond D3. `pool_stage_key`'s docstring notes that a secrets.env change
  restarts the services and destroys idle spares, so a changed model is never served stale.
- **G3.** *Only for crossings 0e shows do not resume* (decision 9). In `build_job`, compare the
  (base URL, model) pair of the previous run's `claude_key` with this turn's credential. When they
  differ and the session would resume, build the job as not resumable with the summary. A previous
  credential that no longer exists counts as different.

## Phase H — the page and the status line (M)

`ffweb.py`, `ffwatch.py`.

- **H1.** `page_claude` (ffweb.py:2719):
  - One row per credential with its kind.
  - An OpenRouter row shows the model and budget ("$X of $Y left today, resets in Z", "no limit
    set", or the error).
  - Every row shows health from `credential_health` and which operators, default or classifier use
    it.
- **H2.** The header counts credentials by kind and names what `claude.default` and
  `claude.classifier` resolve to, or the refusal.
- **H3.** A section for flagged conversations with the last error and `ffwatch release <id>`.
- **H4.** `claude_claims` (ffweb.py:3815) matches every kind, not only non-`api_key` rows.
- **H5.** `claude_status` and the startup check (ffwatch.py:11134) name the default and classifier
  resolutions and each credential's kind; the startup check warns once per refusal and per
  ambiguous id.

## Phase I — configuration and documentation (M)

Split by deploy step, because config.md changes in the same commit as the shape (CLAUDE.md).

**I-1, with phases A and B:**

- **I1.** `ffbox/config.md`: `claude.health` and `claude.classify_retry`, the gate's failure
  behaviour rewritten (it waits), `ffwatch release`, and the flagged-conversation lines in
  `ffwatch status`.
- **I2.** `ffbox/README.md`: the gate's failure behaviour.

**I-2, with phases C onward:**

- **I3.** `ffbox/config.md`:
  - `claude.default` and `claude.classifier`.
  - `operators.<name>.claude` may name any kind.
  - A subsection on credential kinds with the design's section 2 tables.
  - The routing table's wording.
- **I4.** `ffbox/secrets.env.example`: the three families with the section 6 example. Loses "the
  only thing in this file that is not a subscription".
- **I5.** `ffbox/CREDENTIALS.md`: three Claude credentials, the OpenRouter key's blast radius and
  guardrails.
- **I6.** `ffbox/setup.sh`: `api_key_ready` counts any `ANTHROPIC_API_KEY[n]` or
  `OPENROUTER_API_KEY<n>`; `check_api_key`'s text names both and points at the startup line.
- **I7.** `ffbox/05-discord-setup.sh`: the `operators.<name>.claude` hint names the three NAME
  variables.
- **I8.** `ffbox/README.md`: "whose account pays" gains the kinds and the default id.
- **I9.** `docs/docker-security-model.md`: three vendors at :236, and both metered types in the
  credential table at :98.
- **I10.** Source comments that say "the API key" where they mean "the metered default".

## Phase J — tests (L)

`ffbox/test_ffwatch.py` unless said otherwise. `sh ffbox/test.sh` runs all of them.

**J-1, with phases A and B.** Existing tests that change:

- **J1.** `test_the_gate_answers_when_it_is_unsure` and `test_the_gate_fails_open` become one test:
  - The stub exits non-zero, and no turn row exists.
  - The message keeps `gate IS NULL` and `turn_id IS NULL`.
  - `classify_failures` is 1.
  - The pass after the stub recovers and the backoff passes gates it normally.
- **J2.** Tests that relied on the fail-open gate, whether or not they name it:
  - `test_a_new_conversation_waits_for_the_refill_instead_of_being_refused`
  - `test_the_break_notice_waits_on_the_gate_rather_than_getting_ahead_of_it`, whose blind case
    asserts that the fail-open still engages
  - `test_the_reply_has_two_shapes`
  - Every `Case` in an `engage: all` channel without a `verdict`, because the default stub exits
    non-zero. Run the suite after A5 and read every new failure.
- **J3.** `test_a_hold_that_cannot_read_the_windows_runs_the_work` and
  `test_the_account_that_would_pay_is_the_one_the_hold_asks_about` stay green unchanged.

New:

- **J4.** A1: each kind from a stub envelope (402, 429, 401, 503, no status, no envelope, timeout,
  invalid answer). A2: `--json-schema` only after `unusable`.
- **J5.** The selector unavailable: `create_turn` returns None, nothing moves or is stamped. An
  offered-id violation still keeps the deterministic answer.
- **J6.** The backoff: 60, 120 and 240 seconds, then flagged after five with nothing released.
  `ffwatch release` sets the column, the next pass creates a forced turn with no gate call, and the
  columns clear.
- **J7.** Health:
  - Two `outage` failures go `down`, while `limited` and `unusable` do not count.
  - While down, neither classification runs, and a queued turn on that credential stays queued
    through `schedule`.
  - An operator conversation that cannot need a classification runs; one that could need one
    waits.
  - A `probe_one` success goes `up`.
  - The state survives a new `Watcher` on the same state dir.
- **J8.** `finish_run`: a `result.json` with 503 counts, one with 429 does not, and `done` resets.
- **J9.** `review_held` holds a trigger on a down credential.
- **J10.** Notices:
  - A no-end hold posts nothing before `notice_after_secs` and once after, under `down:`.
  - A message `always_a_turn` does not cover gets no notice.
  - An earlier `hold:` notice does not suppress it.
- **J11.** `claude_status` lists a down credential and a flagged conversation.

**J-2, with phases C onward.**

- **J12.** `test_the_classifier_is_handed_the_metered_key_and_no_subscription` runs once per
  metered kind. For OpenRouter the child holds `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, the
  four model variables and an empty `ANTHROPIC_API_KEY`, and no subscription token.
- **J13.** `test_a_classifier_call_carries_a_thinking_budget` widens its allowed environment set by
  exactly those names, only for OpenRouter.
- **J14.** The route tests (`test_an_operators_request_is_billed_to_the_subscription_they_claimed`,
  `test_an_operators_turn_is_billed_to_their_own_subscription`, the `ROUTE_API` fixtures) move to
  `(creds, default)` and gain:
  - An operator claiming an OpenRouter id.
  - `claude.default` naming an OpenRouter id.
  - The default or the classifier naming a subscription is refused.
  - An id on two kinds is ambiguous.
  - The number alias does not match an OpenRouter slot.
  - A variable name matches for every kind.
  - `claude_route_for_comment` resolves an OpenRouter id.
- **J15.** The scan: all three families with gaps, legacy spellings, the unnumbered API key and its
  NAME beside numbered ones, OpenRouter defaults. `_claude_secrets_file` still returns no other
  variable.
- **J16.** `ClaudeKeys` with a stub `openrouter_fetch`: the budget fields, 401 unreachable, 429
  live. `probe_one` for each kind.
- **J17.** A budget hold from OpenRouter waits until `limit_reset` and calls `say_holding` with that
  duration.
- **J18.** `pool_stage_key` stages the player pool on an OpenRouter default.
- **J19.** `launch` routes before `build_job`: a refused route writes no job.json. G3, only if built:
  a crossing on (base URL, model) builds a non-resume job, while the same pair on two names resumes.
- **J20.** `test_ffweb.py`:
  - An OpenRouter row renders model, budget and health.
  - A refused default shows in the header.
  - A flagged conversation is listed with its release command.
  - `claude_claims` credits an operator with their OpenRouter row.
- **J21.** `test_container_credential.sh`:
  - `--claude-key OPENROUTER_API_KEY1` forwards `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL` and the
    four model names by bare name.
  - It passes `ANTHROPIC_API_KEY` only as a literal empty value and no `CLAUDE_CODE_OAUTH_TOKEN`,
    and puts no token on argv.
  - A declared model and URL reach the environment.
  - An empty key exits 78.
  - `--claude-key ANTHROPIC_API_KEY2` forwards `ANTHROPIC_API_KEY` alone.

## Deploy (S, in this order)

1. **Phases A and B, with I-1 and J-1.** `sh ffbox/test.sh` green. Push; the updater restarts the
   services within a tick. Watch `journalctl -u ffwatch` for a credential going `down` and coming
   back `up`, and for conversations that wait. No config change.
2. **Phase 0**, before step 3.
3. **Phases C-H, with I-2 and J-2.** Deploy with no OpenRouter credential declared and neither
   `claude.default` nor `claude.classifier` set; the startup lines must read as they did.
4. **Declare OpenRouter credentials** in secrets.env with names that collide with nothing, and set
   their guardrails in OpenRouter's console (design section 8). `/claude` shows each with its
   budget.
5. **`claude.classifier`** naming one. A week; compare the gate's decline rate with the week before.
6. **`claude.default`** naming one, with `approve_before_send` on, which holds operators' replies
   too for that week (decision 10). B8's placeholder notice is replaced before this step.
7. **Operators opt in** by pointing `operators.<them>.claude` at an OpenRouter id, after 0g.
