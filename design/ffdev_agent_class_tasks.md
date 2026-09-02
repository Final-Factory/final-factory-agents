# ffdev agent class: implementation tasks

Derived from `design/ffdev_agent_class_design.txt` (2026-09-01) after reading the current pool and
launch path: `ffwatch.py` (`load_config`, the pool block from `pool_containers` to `keep_pool`,
`schedule`, `launch`), `ffbox` (`--stage-pool`, the cold `docker create`), `ffweb.py`
(`_prompt_box`, `/actions/prompt`, `FfwatchActions.submit`), and `05-discord-setup.sh` for the
config seeding.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more.

## Status: IMPLEMENTED and verified on live traffic, 2026-09-02

A through G are implemented, H1-H4 are verified on the live box, and **H5 is closed as
obsolete** rather than done — see below. Every offline suite passes: `test_ffwatch.py`,
`test_ffweb.py`, `runners/test_pool.sh`, `runners/test_pin.sh`. (`test_golden_lock.py` no
longer exists; master removed it with `update-golden.sh`.)

Deployed by the self-updater at 2026-09-02 00:07, `f75820d -> 4ca6e7d`. The migration ran
clean: schema **v14** (v13 was taken by the attach watermark while this was in flight),
`conversation.agent_class` present, all 49 existing conversations backfilled to `ffagent`,
zero NULLs.

**What the live verification actually showed.** Conversation 50 was opened as ffdev from the
web page. Three containers were warm at that moment, all staged on `master`, identical but for
their class -- ffagent `3cb3c8d5`, ffdev `111f4475`, ffagent `5091d7d3`. The turn took the
ffdev one:

    00:07:48  pool: staging ffdev 111f4475 on master
    00:11:56  run d50t1-a2574a1a: agent=ffdev lane=dev ... pooled
    00:11:56  pool: staging ffdev d7919721 on master

and the keeper immediately restaged ffdev rather than a third ffagent. The continuation (turn
2, run `d50t2-fecc8a54`) took ffdev container `ea559019` **without being asked** -- nothing on
the follow-up path carries a class -- resumed the same session id with no host-rendered
summary standing in, and the agent confirmed the context survived. job.json on both runs records
`turn.agent_class: ffdev` with ffdev's clocks.

**H5 is obsolete, not skipped.** It asked for a full box to be observed queueing rather than
evicting. What it was really guarding is the ABSENCE of an action, and that is already pinned
where it can regress: `test_a_launch_never_destroys_a_warm_container` asserts `launch()`
contains no `pool_drop`, no `pool_warm` and no `pool_has_room`, and that nothing anywhere asks
`pool_has_room` for zero containers. There is no code left that could evict, so there is no
behaviour under contention to discover -- a full box has only the queueing path to take.
Manufacturing saturation on a live build server to watch nothing happen is not worth the
containers it would cost.

## Follow-ups found while verifying, and their state

- **The live transcript window: FIXED (2026-09-02).** Every pooled run logged exactly two
  `could not index the live transcript ... PermissionError` warnings. Not a broken index, as
  first reported here: `share_transcript_loop` starts one line before the agent is exec'd, so
  its first pass finds no transcript, and at a flat five-second cadence the file then existed
  at 0600 for the rest of that sleep while ffwatch polled every two seconds. Two polls, two
  lines, every run. The loop now polls every 200ms until the first transcript appears (bounded
  at 30s) and settles into the five-second cadence afterwards, which is what covers a
  compaction rewriting the path as a new 0600 inode. Measured on a standalone harness: shared
  250ms after the file appears, against a window of up to five seconds.
- **Leaked pool spools: OPEN.** Three directories on the live box that nothing will ever
  remove -- `13c6506a` (3.0M, holds a transcript), `2819f072` (146K) and `9c82d7c0` (166K).
  All three belong to runs whose `terminal_state` is `done`. `pool_reap` skips the first
  because it holds a transcript and defers to "recovery", but `recover()` only sweeps spools
  belonging to runs with `terminal_state IS NULL` -- of which there are none -- so that
  deferral never comes. The other two fail `_rmtree_spool` with "Directory not empty" on
  subdirectories owned by the container's subuid. Both branches log once per process now, so
  the leak is quiet rather than noisy, which is a fix to the noise and not to the leak.

## What already exists

Worth knowing before estimating.

- **The pool already matches on an attribute carried by a label.** `pool_claim_for` filters
  `pool_warm()` by `ffbox.pool` (the branch), and `pool_containers()`'s format string already pulls
  the name plus two labels out of one `docker ps`. Class is a third label, a fourth field in the
  same tuple, and a second clause in the same filter.
- **The per-lane ceiling is already wired.** `agent_pool_max` is read by `agent_room()`, which
  `keep_pool()` and `schedule()` both consult. (The comment above `_agent_pool` in `load_config`
  still says "pool.max IS NOT READ" — that was true when it was written and has not been since;
  fix it while passing.)
- **The coercion helper is already one place.** `load_config`'s local `_int` plus the three lines
  under it are the whole of the idle/max normalisation, and they move into a per-class function
  unchanged.
- **`ADDED_COLUMNS` is how a column lands.** Append a tuple and `init_schema` runs
  `ALTER TABLE … ADD COLUMN` with whatever DDL it carries. A bare `TEXT` leaves every existing row
  NULL; `TEXT NOT NULL DEFAULT 'x'` backfills them all, which is what D1 wants and what five
  existing entries already do. `conversation.branch` (v12) is the precedent for the guarded
  reader — the guard is for a row read before the migration ran, and is needed either way.
- **`ffbox` builds both containers from ONE argument list.** `RUN_ARGS=(` at `ffbox:840` is
  shared by the staged `docker run` and the cold one; only the two `ffbox.workload` values differ,
  because they differ. A label whose value is the same for both belongs in `RUN_ARGS`, and
  `test_ffwatch.py:3812` already asserts every `docker run` in the file is built from it.
- **`select()` in ffweb** renders a labelled dropdown with a selected option and no blank when
  `blank=None`. The prompt box needs exactly that.
- **ffweb never writes.** The dropdown's value reaches the database only through
  `ffwatch submit --agent`, on the argv-not-a-shell route `submit()` already uses.

## A — config (S)

- **A1** `AGENT_CLASSES = ("ffagent", "ffdev")` and `DEFAULT_AGENT_CLASS = "ffagent"` as module
  constants in `ffwatch.py`. ffweb and `ffbox` cannot import them — ffweb shells out to ffwatch and
  ffbox is shell — so each carries a mirrored literal with a comment naming ffwatch as the
  original, the way `ffweb.py:130` already mirrors `LOCAL_KINDS`.
- **A2** `DEFAULTS["agent_classes"]` — one literal block **per class**, each carrying `base_ref`,
  `agent_secs`, `warmup_secs`, `kill_grace_secs`, `idle_agents`, `agent_pool_max`,
  `idle_agent_ttl_secs`, `pool_ref`. ffdev's are ffagent's values except `idle_agents: 1` and
  `agent_pool_max: 3`. Written out twice rather than derived: the two are expected to diverge. The
  flat keys stay in `cfg` and stay ffagent's.
- **A3** `load_config()` builds `cfg["agent_classes"]`: for each name, that class's DEFAULTS block
  deep-merged with that class's section of config.json, `pool.idle`/`pool.max` mapped onto
  `idle_agents`/`agent_pool_max`, then the existing coercions. No cross-class fallback anywhere —
  a missing section is filled from its own defaults.
- **A4** `class_cfg(cfg, name)` — the one reader, a dict lookup. Unknown name raises; `None` is
  `DEFAULT_AGENT_CLASS`.
- **A5** `05-discord-setup.sh`: seed the `ffdev` section with `pool: {"idle": 1, "max": 3}` and the
  rest of `ffagent`'s values. Two `_help` edits, not one: the `_help` block INSIDE the section,
  and the `"ffdev"` key in the top-level `_help` dict beside the existing `"ffagent"` one, saying
  what a class is and that the two sections are independent. Add the section and both help entries
  to the config.json on this box as well.
- **A6** Tests: per-class resolution, a missing section resolving to its OWN defaults rather than
  to ffagent's configured values, and the coercions running per class.

## B — labels and ffbox (S)

- **B1** `ffbox --agent-class NAME`, defaulting to `ffagent`, validated against the two names.
- **B2** `--label "ffbox.agent.class=$AGENT_CLASS"` in the shared `RUN_ARGS` list (`ffbox:840`),
  NOT at the two `docker run` sites: the value is the same for both, and the existing
  "every container is started from the one argument list" assertion then covers it for free. The
  two `ffbox.workload=pool|agent` labels stay where they are, since those genuinely differ.
- **B3** `ffbox --help` and the flag block at the top of the file.
- **B4** Test: the flag reaches both `docker create` argvs, and an unknown name exits non-zero
  before anything is created. (Source-shape check, like the existing ffbox tests.)

## C — the pool splits (M)

- **C1** `pool_containers()` reads `ffbox.agent.class` into each dict; an empty label is
  `ffagent`.
- **C2** `pool_branch(cls)`, `pool_stage(cls)` (ref, TTL and `--agent-class` from that class's
  block), `pool_claim_for(ref, cls)`, `pool_would_serve(ref, cls)`. The `idle_agents <= 0` early
  return in the last two reads THAT class's idle, so `ffdev.pool.idle: 0` stops ffdev claiming
  without touching ffagent.
- **C3** `agent_workload_count(cls)` counts by the class label rather than "not ci"; an unlabelled
  agent or pool container counts as ffagent. Its two "daemon will not answer" fallbacks return that
  CLASS's `agent_pool_max`, not the flat key. `agent_room(cls)`.
- **C4** `keep_pool()` runs the existing keeper once per class, in a fixed order, with no
  arbitration between them: each gets its own warm count, its own target, its own
  `agent_room(cls)` and its own one-per-pass limit. `workload_room()` and `pool_has_room()` stay
  exactly as they are and are consulted by each. The `_pool_squeeze_logged` flag becomes per class
  so one class's squeeze does not silence the other's message. `keep_pool()` now returns a LIST of
  staged ids (empty for none) rather than one id or None, since a pass can stage one per class;
  `test_the_pool_only_stages_what_it_has_room_for` asserts on the old contract and changes with it.
- **C5** `pool_status()` groups by class.
- **C5b** `pool_drop()` stays class-blind and keeps reading the FLAT `kill_grace_secs`
  (`ffwatch.py:3488`). It is handed an id and nothing else, and looking the class up to stop a
  container would mean a `docker ps` inside a teardown path. Record it as a decision in the
  docstring: if the two classes ever configure different grace periods, this is the one place that
  will not notice.
- **C6** `ffwatch pool status` reports per class; `pool stage` takes an optional class, `pool drop`
  keeps taking a bare id. Both reuse the ONE optional positional the subparser already has
  (`id`, `nargs="?"`), whose meaning already depends on `action` — name it something neutral and
  say so in the help rather than adding a second. The `"the pool is off (idle_agents: 0)"` message
  becomes per class.
- **C7** Tests: C2, C3 and C4 as listed in the design's section 13.

## D — the conversation's class (S)

- **D1** `agent_class TEXT NOT NULL DEFAULT 'ffagent'` in **both** places a conversation column
  lives: the `conversation` table in `ffwatch_schema.sql`, for a fresh database, and
  `ADDED_COLUMNS`, for a long-lived one. NOT NULL with a default, so `init_schema`'s
  `ALTER TABLE … ADD COLUMN` backfills every existing row and the column is never NULL —
  `conversation.is_thread` and `run.pushed` are the precedent. This is what lets F4's filter work
  at all (design section 6). `conversation.branch` (v12) is the model for the column comment. Bump
  `SCHEMA_VERSION` to 14.
- **D2** `conversation_class(conv)` — guarded reader. The guard is for the column being ABSENT on
  a row read before the migration, not for NULL; after D1 there are no NULLs.
- **D3** `submit(..., agent_class=DEFAULT_AGENT_CLASS)` validates against `AGENT_CLASSES` and
  writes it on the row it opens. `follow_up()` takes none. The write goes through
  `upsert_conversation()`, which the Discord ingress shares, so: a new keyword defaulting to
  `DEFAULT_AGENT_CLASS` on the INSERT branch, and **the UPDATE branch must not touch the column** —
  an existing conversation's class is settled and a second upsert must never move it.
- **D4** `ffwatch submit --agent {ffagent,ffdev}`; ignored with a stderr note under
  `--conversation`, beside the existing `--ref`/`--branch` note.
- **D5** Test: the class survives to turn 2; `--agent` on a continuation is noted and ignored.

## E — launch (M)

- **E1** `launch()` resolves `cls` and `ccfg`, and takes the three clocks, `base_ref` and
  `--agent-class` from `ccfg`. The outer `subprocess.run` timeout uses the same numbers.
  `verify_secs` is NOT one of them — it stays `self.cfg["verify_secs"]`, top-level and shared
  (design section 7).
- **E2** `run_ref()` takes the class's `base_ref` as its last rung.
- **E3** `pool_claim_for(ref, cls)`.
- **E4** **Delete the eviction block in `launch()`** — the `if not pool_id and not
  self.pool_has_room(for_containers=0)` loop that drops a warm container before a cold launch. A
  turn that cannot get a place waits for one; `schedule()` already queues it and retries on the
  next pass. This changes ffagent's behaviour too, deliberately (design section 5). Keep
  `pool_has_room()` itself — `keep_pool()` still calls it, where it withholds a speculative
  container rather than destroying an existing one — and drop the now-unused `for_containers=0`
  branch of its signature only if nothing else reaches for it.
- **E5** `schedule()` uses `agent_room(cls)` for the turn's class; `workload_room()` unchanged;
  still `break`, not `continue`. **Add `c.agent_class AS conv_agent_class` to its SELECT** —
  it works off the JOIN and never loads the conversation row, so without this both `agent_room(cls)`
  and the ref given to `pool_would_serve()` silently run against ffagent's numbers.
- **E6** `build_job()` records `turn.agent_class` in job.json.
- **E7** **`build_job()` has two more class-dependent readers, both easy to miss** because they sit
  nowhere near the clocks in `launch()`:
  - `job["limits"]` (`ffwatch.py:4072`) copies `agent_secs`, `warmup_secs` and `kill_grace_secs`
    out of the flat `self.cfg`. Left alone, an ffdev turn's job.json states ffagent's clocks while
    ffbox is actually running it on ffdev's — the record and the container disagree, and job.json
    is what a run directory is read back from months later.
  - `job["rebase"]["to"]` (`ffwatch.py:4013`) is `self.cfg["base_ref"]`, and that string goes into
    the agent's own prompt as the branch it was re-based onto. On an ffdev conversation it would
    name ffagent's base.
  Both take `ccfg`. `build_job()` therefore needs the class too, so resolve it there or pass
  `ccfg` in from `launch()` — `launch()` calls `build_job()` before it builds the ffbox argv, so
  either order works.
- **E8** Tests: E3, and the clocks a launch passes for an ffdev conversation.
  `test_a_cold_launch_short_of_memory_evicts_a_staged_container` in `test_ffwatch.py:6660` is a
  source-shape check asserting the block E4 deletes. Invert it: a launch that cannot claim a
  container never drops one, and no warm container is destroyed to serve a turn. Its name changes
  with it, and so does its entry in the runner list at `test_ffwatch.py:7413`. Also assert E7: an
  ffdev job.json carries ffdev's `limits`.

## F — ffweb (S)

- **F1** `_prompt_box()` renders the dropdown, default ffagent, no blank option.
- **F2** `/actions/prompt` reads `agent`, defaults empty to ffagent, 400s an unknown value, and
  passes it to `FfwatchActions.submit`.
- **F3** `FfwatchActions.submit(prompt, agent_class)` → `["submit", "--source", "web", "--agent",
  cls, "--", prompt]`.
- **F4** Conversation list: an `agent` column and filter, joining the existing
  `("kind", "state", "verdict", "lane")` loop unchanged — D1's backfill is what makes that safe,
  since those dropdowns are built with `SELECT DISTINCT` over the data. Add
  `agent_class` to `REQUIRED_COLUMNS["conversation"]`, or the page reads a column its startup check
  does not know it needs and a stale database gives a traceback instead of the sentence that check
  exists to print.
- **F5** Tests: the dropdown is on the prompt box and absent from the reply box; an unknown class
  is a 400; the default reaches ffwatch as ffagent; `FILTER_SCRIPT` does not bind to it.

## G — docs (S)

- **G1** `ffbox/README.md`: a subsection under the pool section on what an agent class is, the two
  names, where the numbers live, and that the dropdown is new-conversation only. The paragraph at
  `README.md:1311` states the eviction rule E4 removes ("a cold launch that is short of memory
  **evicts** a staged container rather than failing: the pool must never be why a real turn cannot
  start") — rewrite it to say the turn queues instead.
- **G2** The `_help` text in config.json (via A5) and the `--help` strings in ffwatch and ffbox.

## H — verify on the box (DONE, except H5 which is obsolete)

- **H1** ✓ `ffwatch pool` reports two blocks and both classes stage; `docker ps --filter
  label=ffbox.agent.class` shows the label on each. (Run the CLI with `DOCKER_HOST` set, or it
  talks to the wrong daemon and reports zero staged — the systemd unit supplies it.)
- **H2** ✓ An ffdev prompt from the page dispatched into ffdev container `111f4475` while two
  ffagent containers sat warm on the same branch.
- **H3** ✓ Turn 2 of that conversation took ffdev `ea559019` without being asked, resumed the
  same session id, and carried its context.
- **H4** ✓ ffagent conversations kept claiming ffagent containers throughout.
- **H5** ~~Fill the box and confirm a queued turn waits~~ — **OBSOLETE.** It was written to
  observe the absence of an eviction under contention, and there is no longer any code that
  could evict: `test_a_launch_never_destroys_a_warm_container` pins that `launch()` holds no
  `pool_drop`, no `pool_warm` and no `pool_has_room`, and that nothing asks `pool_has_room` for
  zero containers. A full box has only the queueing path left to take, so saturating a live
  build server would demonstrate nothing the test does not already hold.

## Verified as needing no change

Checked while writing these tasks, so nobody re-derives them:

- **`update_ffbox.sh`'s drain** matches staged containers by the NAME pattern `ffbox-pool-*`
  (`update_ffbox.sh:320`), and both classes keep that prefix — `pool_drop` builds
  `ffbox-pool-<id>` for either. Its comment about never sweeping by label still holds and must
  stay.
- **`ffbox --direct`** takes the `--agent-class` default and lands in ffagent, which is what a
  hand-run prompt on this box should be.
- **`pool_reap()`, the drain sweep and `recover()`** decide by `out/owner` and the spool directory,
  neither of which knows about classes.
- **The capability set.** One set for every run, per design section 12.
- **`container.memory` / `pids_limit` / `workspace_size`.** Per container, shared with CI.
- **`ffwatch init`** creates the state directory and applies the schema; it does not seed
  config.json, so A5 is the only seeding path.
- **`pool-task.sh`, `discord-task.sh`, `entrypoint.sh`, `ffverify.sh`.** Nothing in the container
  reads the class; `job["limits"]` is written by the host and read by nothing in the container
  today.

## Order

A → B → C → D → E → F, with G alongside and H after the deploy. C is the only part with real
reasoning in it; the rest is threading a value through paths that already carry two others like
it.

A and B are independently landable and change no behaviour: a config section nothing reads and a
label nothing filters on. C without D and E gives two pools that nothing claims from the second of,
which is safe — `pool_claim_for` falls through to a cold launch — so C can land and be watched for
a day before anything routes to it.

## Deploy

Config first (A5's seeding is idempotent), then the code, then a restart. A staged container from
before the deploy has no class label and is claimable as ffagent, so nothing has to be drained for
correctness — but the updater's drain destroys the unclaimed ones anyway, and the first pass after
the restart stages one of each class.
