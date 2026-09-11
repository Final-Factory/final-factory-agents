# OpenRouter as a credential type: implementation tasks

Derived from `design/openrouter_provider_design.txt` revision 5 (2026-09-10), against the code at
eb4cfaa: `claude_keys.py` (the slot scan, `slot_ids`, `subscription_named`, `default_api_key`,
`_claude_secrets_file`, `ClaudeKeys.__init__`, `_probe_api`, `_load`, `read`), `ffwatch.py`'s route
(`claude_route`, `claude_key_id`, `claude_keys_now`, `claude_route_for`, `claude_route_for_turn`,
`claude_routes`), its classifier (`classifier_invocation`, `classifier_attempt`, `run_classifier`,
`should_engage`, `should_engage_for`, `failed_open`, `model_selection`, `select_for_turn`,
`resettle`), its turn path (`create_turn`, `conversation_held`, `hold_until_morning`,
`say_holding`, `say_route_refused`, `claude_hold`, `work_hold`, `launch`), its pool
(`pool_stage_key`, `pool_claim_for`, `pool_would_serve`, `schedule`), `ffbox`'s `--claude-key`
block and `RUN_ARGS`, `ffweb.py`'s `page_claude`, and the Claude tests in `test_ffwatch.py`,
`test_ffweb.py` and `test_container_credential.sh`.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more.

## Status, 2026-09-10

**Not started.** Phase 0 is by hand and gates phases C onward. Phases A and B do not depend on
it and ship first, on their own, because they change behaviour on every box whether or not
OpenRouter is ever configured.

## What already exists

- **Every request already has one payer.** `claude_route(cfg, tier, actor, kind, keys)`
  (ffwatch.py:1944) returns a variable name or a refusal, from the trust tier and an authenticated
  id. Nothing about how trust is decided changes here. What changes is the lookup underneath:
  which credentials exist, and what an id resolves to.
- **A refusal and a hold already wait without writing anything.** `conversation_held`
  (ffwatch.py:7180) returns `(verdict, secs, why, key)` with `run`, `hold` or `refused`, and
  `create_turn` leaves the messages unclaimed and ungated for the last two. Quiet hours do the
  same above `resettle` (ffwatch.py:7468). Section 7 of the design adds a fourth verdict and a
  HOLD from the classifications; it does not invent the shape.
- **A credential already travels as a name.** `--claude-key` carries a variable name, ffbox
  resolves it out of secrets.env, forwards it with a bare `-e NAME`, and refuses a name its own
  scan did not find (ffbox, "which Claude credential this container gets"). `CLAUDE_ENV_ARGS`
  already exists so the forwarded names can differ per credential.
- **A run and a spare already record their credential.** `run.claude_key` holds the variable name;
  `<pool dir>/claude-key` holds the spare's, and `pool_claim_for` (ffwatch.py:9108) matches on it.
- **Two record kinds already exist.** `KIND_SUBSCRIPTION` and `KIND_API_KEY` (claude_keys.py:143)
  flow through `ClaudeKeys.read`, the shared store and `page_claude`. OpenRouter is a third kind on
  the same path.
- **The API key is already probed.** `_probe_api` (claude_keys.py:597) is a one-token request with
  `x-api-key`; it is the pattern for the OpenRouter probe.
- **The lost-transcript path already exists.** `build_job`'s `resume_summary` starts a new session
  with a host-rendered summary. Design section 10 uses it only if a crossing does not resume.

## Decisions taken while writing these tasks

Places where the design's prose and the code did not line up, settled here. The design was edited
to match where marked.

1. **The health hold counts calls, not readings.** `test_a_hold_that_cannot_read_the_windows_runs_the_work`
   pins that an unreadable window reading runs the work, and that stays true. A credential goes
   `down` only on failed calls billed to it: a classification or a container run whose result is an
   API error. A reading that fails is still "nothing to hold on". (Design section 7 edited.)
2. **"Needs a classification" is decided above `resettle`, conservatively.** `conversation_held`
   runs before the selector and the gate, so it cannot know whether either will actually be called.
   It answers `down` for the classifier's credential when the conversation COULD need one: a
   non-thread, non-local conversation holding a `recent`-routed message (the selector's band), or a
   conversation in an `engage: all` channel that `always_a_turn` does not force (the gate's). Both
   are readable from config and the pending rows before anything moves. (Design section 7 edited.)
3. **The conversation backoff and its failure count live in memory.** A dict on `Watcher`, like
   `_hold_decided`. A restart forgets them, and the next pass retries at once, which is the right
   default after a restart. The flag's durable trace is its journal WARNING.
4. **`ffwatch release` writes the database, not the daemon.** The CLI is a separate process, the
   same as `ffwatch approve`. It sets `conversation.gate_released_by` (new, nullable), which
   `create_turn` reads as `forced` for that conversation's next turn and clears when the turn row is
   written. Schema migration via the existing `ALTER TABLE ... ADD COLUMN` path.
5. **The OpenRouter probe's token budget is a constant, set by 0d.** Flash reasons by default, so
   `max_tokens: 1` may not be enough to get a 200 at all. `OPENROUTER_PROBE_MAX_TOKENS` in
   claude_keys.py starts at 1 and is set from the measurement.
6. **`claude_keys_now` returns three things.** `(credentials, default, classifier)`, where each of
   the last two is `(name, why)` or `(None, refusal)`. `claude_route` takes the credentials and the
   resolved default in place of `(subscriptions, api_key)`. Every caller of the old pair moves:
   `claude_route_for`, `claude_route_for_turn`, `claude_routes`, `pool_stage_key`, the startup
   check and the status line.
7. **`CLAUDE_API_KEY_NAME` stays.** It becomes "the default when `claude.default` is unset" rather
   than "the default". ffweb and ffwatch keep importing it.
8. **The session-crossing rule is conditional.** G3 is built only for the crossings 0e shows do not
   resume. If all resume, G3 is dropped and the design's section 10 loses its rule.
9. **`approve_before_send` stays box-wide.** Per-route approval is an open decision in the design
   (section 15), not a task. The deploy step says what box-wide costs during phase 4.

## Phase 0 — measure, by hand (M)

Nothing here ships. Each result is written into the design's next revision.

- **0a.** The classifications on Flash against the stored answers (design 13a). The gate must never
  decline a message the current gate engaged.
- **0b.** Player turns on an OpenRouter credential wired into a scratch ffbox by hand, a screenshot
  report among them (13b).
- **0c.** Deliberate failures: 402 via a $0.01 limit, a model the allowlist refuses, a provider
  allowlist no endpoint meets (503), a revoked key (401). Record the classifier's exit code and
  envelope and the container's `stream.jsonl` and `claude.log` for each (13c). B2 and B5 are written
  against these.
- **0d.** `GET /api/v1/key` fields and cost, and the smallest `max_tokens` Flash answers with (13d).
- **0e.** Session crossings: Anthropic to OpenRouter, OpenRouter to Anthropic, OpenRouter model A
  to model B, each after a thinking block and a tool call (13e).
- **0f.** Last week's bug-report and ask threads replayed on Flash, replies read against max-voice
  and the venue rules (13f).
- **0g.** One operator dev turn on an OpenRouter credential in ffdev, through compile and the fast
  suite (13g).

## Phase A — a classification that fails waits (M)

`ffwatch.py`. Ships with Phase B, before anything else.

- **A1.** `classifier_attempt` and `run_classifier` return a failure kind beside the message:
  `unavailable` (non-zero exit, timeout, envelope not JSON, no credential) or `unusable` (ran, did
  not validate). `run_classifier` skips the `--json-schema` retry after an `unavailable` first
  attempt.
- **A2.** `should_engage` returns a HOLD result on either failure kind instead of calling
  `failed_open`. `should_engage_for` passes it through.
- **A3.** `model_selection` returns HOLD on either failure kind. An answer that validates but names
  an id that was not offered still returns `(None, None)` and keeps the deterministic answer.
  `select_for_turn` and `resettle` pass HOLD up without moving or stamping anything.
- **A4.** `create_turn` returns None on a HOLD from `resettle` or the gate, with nothing claimed,
  gated or marked. Delete the `fc` handling: the `failed_open` log line, and the two `if not fc`
  guards before `say_route_refused` and `say_holding`. New turns write `failed_closed=0`. The
  column, the prompt note and the footer stay for historical rows.
- **A5.** The conversation backoff (decision 3): after a HOLD on a conversation whose credential is
  not `down`, `create_turn` returns early for it until `first_secs`, doubling to `max_secs`. It is
  cleared when a classification for that conversation succeeds.
- **A6.** Flagging: at `flag_after` failures, one WARNING in the journal and an entry in a
  `_classify_flagged` set that `ffwatch status` and ffweb read. The conversation keeps waiting at
  `max_secs`.
- **A7.** `ffwatch release <conversation>` (decision 4): the CLI sets
  `conversation.gate_released_by`, and `create_turn` treats that conversation as `forced` and clears
  the column when it writes the turn row. The migration adds the column.
- **A8.** `DEFAULTS["claude"]` gains `classify_retry: {first_secs: 60, max_secs: 1800,
  flag_after: 5}`.

## Phase B — the health hold (M)

`ffwatch.py`, `claude_keys.py`. Ships with Phase A.

- **B1.** A per-credential health state on `Watcher`: `up`, `down(since)`, and the time of the next
  probe. `record_call(name, ok, kind)` is the one writer. A success resets the count.
  `after_failures` consecutive failures of kind `unavailable` (A1), or one budget error (B5), go
  `down`. `unusable` does not count (decision 1).
- **B2.** Every classification reports to `record_call` for the classifier's credential. `launch`'s
  result handling reports a run whose `stream.jsonl` result is an API error, recognised by the
  shapes 0c recorded.
- **B3.** `conversation_held` returns a new `down` verdict when the conversation's route credential
  is down, or when the classifier's credential is down and the conversation could need a
  classification (decision 2). `create_turn` returns on `down` ABOVE `resettle` and the gate, the
  way it returns on quiet hours, and adds nothing to `_hold_decided`.
- **B4.** Probing: when `down` and the probe time has passed, run that credential's reachability
  probe (`ClaudeKeys` probe for a subscription, `_probe_api` for an API key, C6 for OpenRouter), or
  one real waiting classification for the classifier's credential. A success goes `up`.
- **B5.** The budget hold: an OpenRouter 402 goes `down` with a known end, read from C6's
  `limit_reset`, and no probe runs before then. A negative balance goes `down` with no end and logs
  an ERROR. (Written in B so the state has a place for it; exercised only after Phase C.)
- **B6.** `schedule` and `launch` leave a turn `queued` while its route credential is `down`.
- **B7.** Notices: a `down` hold with a known end calls `say_holding` with that duration. One with
  no end calls a new `say_waiting` once per hold, keyed `hold:<conversation>:<turns>`, after
  `notice_after_secs`. Its wording is the design's open decision, and the task ships a placeholder
  that must be replaced before phase 4.
- **B8.** `log_hold` lines for going `down` and coming back `up`, once each. `DEFAULTS["claude"]`
  gains `health: {after_failures: 2, probe_secs: 60, notice_after_secs: 600}`.

## Phase C — credential types (L)

`claude_keys.py`.

- **C1.** Constants for the new families: `ANTHROPIC_NAME_PREFIX = "ANTHROPIC_NAME_KEY"`,
  `OPENROUTER_KEY_PREFIX = "OPENROUTER_API_KEY"`, `OPENROUTER_NAME_PREFIX`, `OPENROUTER_MODEL_PREFIX`,
  `OPENROUTER_URL_PREFIX`, `OPENROUTER_DEFAULT_MODEL = "z-ai/glm-5.3-flash"`,
  `OPENROUTER_DEFAULT_URL = "https://openrouter.ai/api"`, `KIND_OPENROUTER = "openrouter"`, and
  `metered(kind)`.
- **C2.** `claude_credentials(env=None, secrets_path=None)` → one tuple per credential,
  `(name, token, kind, label, rate, model, url)`, in family then slot order. Subscriptions exactly
  as `_claude_tokens_from` reads them today, legacy unnumbered spelling included. The unnumbered
  `ANTHROPIC_API_KEY` always, then `ANTHROPIC_API_KEY1..16`, each with its NAME. `OPENROUTER_API_KEY1..16`
  with NAME, MODEL (default C1) and URL (default C1). "A gap is not the end" for every family.
  Environment first, then the filtered file, as today.
- **C3.** `claude_subscriptions()` becomes the subscription filter over C2, so its callers are
  unchanged.
- **C4.** `slot_ids(name, label, kind)`: the declared name and the variable name for every kind, and
  the bare slot number for subscriptions only. `credential_named(key_id, creds)` replaces
  `subscription_named` with the same answers (found, "no slot", "ambiguous: a, b") across all kinds.
- **C5.** `_claude_secrets_file` widens `wanted` to the C1 families, numbered 1..16, and nothing else.
- **C6.** `ClaudeKeys(credentials=...)` replaces `tokens=` and `api=`; keep both keyword arguments
  as thin adapters until the tests are moved, then delete them. `read()` builds its list from C2.
  `_load` gains the OpenRouter branch: `GET {url}/v1/key` with `Authorization: Bearer`, recording
  `limit`, `limit_remaining`, `limit_reset` and `usage_daily`, plus one
  `OPENROUTER_PROBE_MAX_TOKENS` request to `{url}/v1/messages` for the slot's model (decision 5). A
  401 is `unreachable`; a 429 is a live key, as `_probe_api` already reads it. A new seam,
  `openrouter_fetch`, beside `fetch`, `probe` and `api_probe`.
- **C7.** `default_api_key()` is deleted. `credential_for(key_id, creds)` returns the tuple for a
  resolved name, for the callers that need the token, kind and model together.
- **C8.** The module header gains a paragraph on the three kinds and the one namespace.

## Phase D — resolving the default and the classifier (M)

`ffwatch.py`.

- **D1.** `claude_keys_now()` → `(credentials, default, classifier)` (decision 6). `default` resolves
  `claude.default` with `credential_named`, or the unnumbered `ANTHROPIC_API_KEY` when unset;
  `classifier` resolves `claude.classifier`, or copies `default` when unset. A resolution that lands
  on a subscription is `(None, "<id> is a subscription, and ... must be metered")`.
- **D2.** `claude_route(cfg, tier, actor, kind, creds, default)`: operators through
  `credential_named`, everybody else through `default`. Refusal sentences name the id and variable
  involved and never the constant `ANTHROPIC_API_KEY` unless that is what was asked for.
- **D3.** `claude_route_for`, `claude_route_for_turn` and `claude_routes` pass D1's parts through.
  `claude_routes` reports each operator's credential kind.
- **D4.** A `Watcher.classifier_credential()` accessor over D1 for Phase E and B2.
- **D5.** `claude_hold` uses `metered(rec["kind"])` where it now relies on the API key being the only
  record without windows. Behaviour unchanged for existing kinds.
- **D6.** `pool_stage_key` stages player-pool spares on D1's `default` name, and returns None with the
  same once-only log when the default does not resolve.
- **D7.** `DEFAULTS["claude"]` gains `default: None` and `classifier: None`.

## Phase E — the classifier's environment (S)

`ffwatch.py`.

- **E1.** `classifier_invocation(cfg, prompt, schema, structured=True, credential=None)`, where
  `credential` is C7's tuple and None means D4's. The environment is the design's section 5 table for
  its kind: `ANTHROPIC_API_KEY` for `api_key`, the OpenRouter set for `openrouter`. A subscription is
  not accepted (D1 already refuses it).
- **E2.** Remove `ANTHROPIC_API_KEY` from the passthrough list. `LANG` and `LC_ALL` stay.
- **E3.** `--model` stays `cfg["classifier_model"]` (`haiku`); on OpenRouter the alias variables
  carry the model.

## Phase F — the container (M)

`ffbox`, `ffbox/egress/allowlist.txt`.

- **F1.** The `--claude-key` scan covers the three families the way C2 does and records each found
  name's kind from its prefix. Only a found name is accepted; an empty variable exits 78, as
  `ANTHROPIC_API_KEY` does today.
- **F2.** Per kind: a subscription exports `CLAUDE_CODE_OAUTH_TOKEN`; an API key (numbered or not)
  exports `ANTHROPIC_API_KEY`; an OpenRouter key exports `ANTHROPIC_AUTH_TOKEN`,
  `ANTHROPIC_BASE_URL` from `OPENROUTER_URL_KEY<n>` or the default, and the four
  `ANTHROPIC_DEFAULT_*_MODEL` from `OPENROUTER_MODEL_KEY<n>` or the default. The defaults are
  written once in ffbox beside the other mirrored constants, with a comment naming C1 as the
  original.
- **F3.** `CLAUDE_ENV_ARGS` forwards exactly that kind's names by bare `-e NAME`, plus the literal
  `-e ANTHROPIC_API_KEY=` for OpenRouter. Nothing else from the other kinds.
- **F4.** The no-flag path still takes the first subscription slot.
- **F5.** `openrouter.ai` on `ffbox/egress/allowlist.txt`, with a comment in the Anthropic section's
  style saying which traffic it carries.
- **F6.** The usage text for `--claude-key` names the three kinds.

## Phase G — launch, spares and sessions (M)

`ffwatch.py`.

- **G1.** `launch` records a run's credential as today; no new column. The status line and ffweb
  derive a run's kind from the name prefix with one helper, `credential_kind(name)`, in claude_keys.
- **G2.** Spares: nothing beyond D6. `pool_claim_for` already matches on name. Note in the
  `pool_stage_key` docstring that a model change on the same name is not caught (design section 9).
- **G3.** *Only for crossings 0e shows do not resume* (decision 8). In `build_job`, when the
  previous run's credential and this turn's differ in (base URL, model), build the job as not
  resumable with the summary. The pair comes from C7's tuple for both names; a previous credential
  that no longer exists counts as different.

## Phase H — the page and the status line (M)

`ffweb.py`, `ffwatch.py`.

- **H1.** `page_claude` (ffweb.py:2719): one row per credential with its kind. An OpenRouter row
  shows the model and budget ("$X of $Y left today, resets in Z", or "no limit set", or the 401 or
  balance error). Every row shows health and which operators, default or classifier use it.
- **H2.** The header counts credentials by kind and names what `claude.default` and
  `claude.classifier` resolve to, or the refusal.
- **H3.** A section for flagged conversations (A6), with the last error and the `ffwatch release`
  command to run.
- **H4.** `ffwatch status`: the resolved default and classifier, one line per credential with kind
  and health, and the flagged conversations.
- **H5.** The startup check (ffwatch.py:11134) logs the default and classifier resolutions and warns
  once for each refusal.

## Phase I — configuration and documentation (M)

- **I1.** `ffbox/config.md`: `claude` gains `default`, `classifier`, `health` and `classify_retry`;
  the routing table says what `default` and `classifier` resolve through; `operators.<name>.claude`
  may name any kind; a subsection on credential kinds with the section 2 tables; the engagement
  gate's failure behaviour rewritten (it waits). Same commit as D7, A8 and B8.
- **I2.** `ffbox/secrets.env.example`: the three families with the section 6 example, beside
  eb4cfaa's paragraphs, which lose "the only thing in this file that is not a subscription".
- **I3.** `ffbox/CREDENTIALS.md`: "the two Claude credentials" becomes three, with the OpenRouter
  key's blast radius and the guardrails from design section 8.
- **I4.** `ffbox/setup.sh`: `api_key_ready` counts any `ANTHROPIC_API_KEY[n]` or
  `OPENROUTER_API_KEY<n>`; `check_api_key`'s text names both and points at ffwatch's startup line.
- **I5.** `ffbox/05-discord-setup.sh`: the `operators.<name>.claude` hint names the three NAME
  variables.
- **I6.** `ffbox/README.md`: the "whose account pays" section gains the kinds and the default id.
- **I7.** `docs/docker-security-model.md`: the allowlist paragraph at :236 (three vendors) and the
  credential table at :98.
- **I8.** Source comments that say "the API key" where they now mean "the metered default": in
  `claude_route`, `classifier_invocation`, `pool_stage_key`, `claude_hold`, and ffbox's
  `--claude-key` block.

## Phase J — tests (L)

`ffbox/test_ffwatch.py` unless said otherwise. `sh ffbox/test.sh` runs all of them.

Existing tests that change:

- **J1.** `test_the_gate_answers_when_it_is_unsure` and `test_the_gate_fails_open` become one test that
  the gate waits: the stub exits non-zero, no turn row, the message keeps `gate IS NULL` and
  `turn_id IS NULL`, and the pass after the stub recovers gates it normally.
- **J2.** Any hold test with a could-not-decide gate case loses that case (find them by `failed_open`
  and `failed_closed` in the suite).
- **J3.** `test_the_classifier_is_handed_the_metered_key_and_no_subscription` runs once per metered
  kind. For OpenRouter the child holds `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, the four model
  variables and an empty `ANTHROPIC_API_KEY`, and no subscription token.
- **J4.** `test_a_classifier_call_carries_a_thinking_budget` widens its allowed environment set by
  exactly those names, only for OpenRouter.
- **J5.** The route tests (`test_an_operators_request_is_billed_to_the_subscription_they_claimed`,
  `test_an_operators_turn_is_billed_to_their_own_subscription`, and the `ROUTE_API` fixtures) move
  to `(creds, default)`, and gain: an operator claiming an OpenRouter id; `claude.default` naming an
  OpenRouter id; the default or classifier naming a subscription is refused; an id on two kinds is
  ambiguous; the number alias does not match an OpenRouter slot; a variable name matches for every
  kind.
- **J6.** `test_the_account_that_would_pay_is_the_one_the_hold_asks_about` and
  `test_a_hold_that_cannot_read_the_windows_runs_the_work` stay green unchanged (decision 1).

New:

- **J7.** A: the selector's call is unavailable → `create_turn` returns None, nothing moves or is
  stamped; an unavailable attempt is not retried under `--json-schema`; an offered-id violation
  still keeps the deterministic answer.
- **J8.** A: backoff 60, 120, 240 seconds; flagged after five without release; `ffwatch release` sets
  the column, the next pass creates a forced turn and clears it.
- **J9.** B: two unavailable calls go `down`; an unusable answer does not count; while `down`
  neither classification runs, queued turns on that credential stay queued, an operator
  conversation that cannot need a classification runs on its own credential, one that could need
  one waits; a probe success goes `up`.
- **J10.** B: an OpenRouter 402 with `limit_remaining` 0 holds until `limit_reset` and calls
  `say_holding` with that duration; a no-end hold posts nothing before `notice_after_secs` and once
  after.
- **J11.** C: the scan over all three families with gaps, legacy spellings, the unnumbered API key
  beside numbered ones, OpenRouter model and URL defaults; `_claude_secrets_file` still returns no
  other variable.
- **J12.** C: `ClaudeKeys` with a stub `openrouter_fetch`: budget fields on the record, 401
  unreachable, 429 live.
- **J13.** D: `pool_stage_key` stages the player pool on an OpenRouter default.
- **J14.** G3, only if built: a crossing on (base URL, model) builds a non-resume job, and the same
  pair on two names resumes.
- **J15.** `test_ffweb.py`: an OpenRouter row renders model, budget and health; a refused default
  shows in the header; a flagged conversation is listed with its release command.
- **J16.** `test_container_credential.sh`: `--claude-key OPENROUTER_API_KEY1` forwards
  `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL` and the four model names by bare name, passes
  `ANTHROPIC_API_KEY` only as a literal empty value, passes no `CLAUDE_CODE_OAUTH_TOKEN`, and puts no
  token on argv; a declared model and URL reach the environment; an empty key exits 78;
  `--claude-key ANTHROPIC_API_KEY2` forwards `ANTHROPIC_API_KEY` alone.

## Deploy (S, in this order)

1. **Phases A and B, with J1-J4, J6-J10.** `sh ffbox/test.sh` green. Push; the updater restarts the
   services within a tick. Watch `journalctl -u ffwatch` for `waiting rather than running now`,
   going `down` and coming back `up`. No config change.
2. **Phase 0**, any time before step 4.
3. **Phases C-I, with the rest of J.** Deployed with no OpenRouter credential declared and neither
   `claude.default` nor `claude.classifier` set; the startup lines must read as they did.
4. **Declare OpenRouter credentials** in secrets.env and set their guardrails in OpenRouter's
   console (design section 8). `/claude` shows each with its budget.
5. **`claude.classifier`** naming one. A week; compare the gate's decline rate with the week before.
6. **`claude.default`** naming one, with `approve_before_send` on. Box-wide approval holds operators'
   replies too for that week (decision 9). The outage notice's placeholder (B7) is replaced before
   this step.
7. **Operators opt in** by pointing `operators.<them>.claude` at an OpenRouter id, after 0g.
