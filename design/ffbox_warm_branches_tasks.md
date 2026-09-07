# ffbox warm branches: implementation tasks

Derived from `design/ffbox_warm_branches_design.txt` (2026-09-06) after reading the code it
lands in: `ffwatch.py`'s keeper (`keep_pool`, `pool_stage`, `pool_expire`, `pool_status`,
`pool_claim_for`), its config plumbing (`DEFAULTS`, `_class_blocks`, `load_config`), `ffbox`'s
staged `docker run` (1323-1371), `ffstatus.sh`'s `gather`, and the pool tests already in
`test_ffwatch.py`.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more.

## Fixed after the first deploy, 2026-09-06

Two defects found by watching the live box, both now in this branch:

1. **A finished run left no spare on its branch.** The candidate query dated a branch by
   `COALESCE(started_at, queued_at)` — when the turn BEGAN. A dev turn can run for hours
   (`agent_secs` is 7200 for ffdev, with warm-up and verification either side), so a long turn's
   branch was already outside the one-hour window the instant the run ended, which is the moment
   the follow-up arrives. Now `COALESCE(ended_at, started_at, queued_at)`: the latest thing that
   happened to the turn. Covered by "a long run's branch is dated by when it ENDED".
2. **`ffstatus` showed no ref for a running container.** The agent rows blanked it — for a cold
   run there was no label to read, and for a dispatched one the `ffbox.pool` label was right there
   and thrown away. `ffbox` now sets `ffbox.ref` on BOTH routes and `ffstatus` reads it, falling
   back to `ffbox.pool` for a container staged before the label existed. The label means "where
   the clone started"; a sha-pinned turn dispatched into a spare keeps the staged branch's name,
   because a label is creation-time.

## Added after the first deploy, 2026-09-06

**Every decline reason is logged**, one line per transition. The tier shipped with all six of its
decline paths silent, so the first real report against it — "the run finished and no spare
appeared" — had nothing behind it to diagnose, and the first answer I reached for was wrong
because there was no evidence to check it against. `warm_branch_note` latches on the reason key
(`deadband`, `ceiling`, `memory`, `nothing:<which filters>`), the same shape as
`_pool_squeeze_logged` on the held tier, so a keeper running every five seconds cannot turn a
useful line into wallpaper. Covered by
`test_the_warm_branch_tier_says_why_it_is_not_staging`.

## Status, 2026-09-06

**All phases implemented and green**, offline: `test_ffwatch.py` and `test_ffweb.py` both pass,
`bash -n` on the three shell files, `bumpVersion.sh --check` clean. Nothing here has run against a
real docker daemon yet, so three things are covered only by construction and want watching on the
build server after the deploy:

- **A staged evictable container actually filling.** `ffbox --pool-tier` is exercised for its
  refusal (a bad value exits 2) and for the label going onto the argv, not for a container coming
  up warm on a non-default branch.
- **The shed reaching a real `docker stop`.** The claim, the ordering, the `out/retiring` marker
  and the refusal to touch a held or claimed spare are all tested; `_pool_expire_one` is stubbed.
- **The reserve under real contention** — CI taking the reserved place and the next pass giving it
  back. The arithmetic is tested against stubbed room counts.

Two deviations from the phases below, both deliberate and both folded into the design:

- **`ffstatus.sh` counts the tiers apart**, and `ffweb.py`'s pools table grows a `branch` column.
  A5 only asked for the state word. Folding a guess into `WAITING` would show a pool as full while
  the promise `pool.idle` made was unkept, which is the same bug the keeper's own count had.
- **`keep_warm_branches` reads `workload_room()` once, lazily**, where the held loop re-reads it
  per class. That loop stages one per class so a place taken by an earlier class must be visible to
  the next; this one stages at most one in total and returns, so there is nothing to re-read, and a
  box with the tier off makes no `docker ps` call at all.

## What already exists

Worth knowing before estimating. Most of this feature is a scheduling decision, not machinery.

- **A spare is already per branch.** `pool_stage` passes `--ref`, the branch goes on as the
  `ffbox.pool` label, and `pool_claim_for` already matches a turn to a spare by class AND exact
  branch. Staging on a second branch needs no new claim path and no new dispatch path.
- **`pool_expire` already runs a host-side clock** off `out/staged`'s `ttl_secs`, which arrives
  from `--idle-ttl` at stage time. A shorter TTL for the new tier is a different number through
  the same pipe.
- **`pool_drop` already destroys a spare correctly** — soft stop floored at `LICENCE_STOP_FLOOR`
  so PID 1's traps run, then `container_rm`, and it refuses a claimed spool.
- **`_pool_expire_one` is already the off-loop stop**, threaded, with `_pool_expiring` guarding
  against a second thread for the same id. The shed reuses it whole.
- **`pool_take` is already the atomic arbiter** — `out/owner` created `O_EXCL`. The shed claims
  before it stops, exactly as the expiry does.
- **`mirror_carries` already exists** (written for the launch path) and answers the one question
  that decides whether a branch can be staged at all.
- **`workload_room` / `agent_room` / `pool_has_room`** are all written and tested. The reserve is
  arithmetic on top of `workload_room`, not a new count.
- **ffstatus's `state` column flows into `--json` untouched**, so a new state word reaches
  `/status` with no change to `render_json` or to ffweb.

## Decisions taken while writing these tasks

Six places where the design's prose and the code did not line up. Settled here, and the design
was edited to match.

1. **The feature ships ON, at `count: 1` per class.** The design's section 0 made the whole thing
   conditional on a measurement and seeded `count: 0`. The measurement is still worth taking, but
   the request was for the behaviour, and a feature that ships off is a feature nobody sees.
   1 per class rather than 2 because there are two classes: "a warm sandbox or two" is the box's
   number, not one class's. Raising it is one key.
2. **A pass that staged a HELD spare stages no evictable one.** Not in the design. `pool_stage`
   blocks the daemon's own loop for up to 180 seconds and the keeper already runs one staging per
   class per pass; a third would add half a minute of blocked loop on a bad pass, which is the
   2026-09-02 incident with a new cause. Held first, and at most one evictable per pass overall.
3. **`effective_pool_tier` reads `c.get("tier")`, not `c["tier"]`.** Every existing test builds
   container dicts by hand with four keys. A required fifth key would break them for no reason,
   and an absent tier already has a correct answer: held.
4. **The shed orders by activity, and an unknown branch sorts FIRST.** The design said "oldest
   first, and among those with no `seen` at all, any". A spare whose branch has dropped out of the
   window entirely is the guess with the least behind it, so it is not a tiebreak case — it is the
   first thing to go. `seen.get(...) or ""` sorts it there by construction.
5. **`_pool_stage_after` is re-keyed to `(class, branch)`.** It is keyed by class today. The
   evictable tier needs a per-branch cooldown, and a shared key would let one branch's failure
   stop the class's held pool being topped up. `test_a_failed_staging_is_not_retried_every_pass`
   pokes that dict directly and is updated with it.
6. **The existing keeper tests pin `warm_branches.count = 0`.** They stub `pool_stage` with
   `lambda cls=None:` and assert exact lists of what was staged; with the tier on by default they
   would see extra calls and fail for a reason that is not about them. One line each, with the
   reason.

## Phase A — the tier exists and is visible (S)

- **A1.** `ffbox`: `POOL_TIER=held` beside `STAGE_POOL`, a `--pool-tier` argument, validation
  against `held|evictable` next to the `--agent-class` check, a usage entry, and
  `--label "ffbox.pool.tier=${POOL_TIER}"` on the staged `docker run` beside the three labels
  already there.
- **A2.** `ffwatch.py`: `POOL_TIER_HELD` / `POOL_TIER_EVICTABLE` constants; `pool_containers`
  reads the label into `c["tier"]`, empty meaning held.
- **A3.** `effective_pool_tier(c)`: the label, except that a spare whose branch is not its class's
  `pool_branch()` reads as evictable whatever its label says. Docker cannot relabel a running
  container, so a `base_ref` move has to be handled by arithmetic.
- **A4.** `pool_stage` takes `ref`, `tier` and `ttl_secs`, defaulting to today's behaviour, and
  passes `--pool-tier` through.
- **A5.** `pool_status` and `ffstatus.sh` say `warm-evictable` where they say `warm` for a spare
  of the new tier. `ffstatus.sh` needs `ffbox.pool.tier` in its `docker ps` format string.

## Phase B — configuration (S)

- **B1.** `DEFAULTS`: `workload_reserve: 1` at the top level; `warm_branches` (`count`,
  `window_secs`, `ttl_secs`) in each class's block.
- **B2.** `_class_blocks`: coerce `warm_branches` wholesale from that class's own defaults, the
  way `github` is coerced — a partial object or a string in the file must still come back with
  all three keys present and numeric.
- **B3.** `load_config`: clamp `workload_reserve` to `0 .. max_concurrent_runs - 1`. A reserve at
  or above the ceiling can never be satisfied, so the keeper would shed everything and stage
  nothing.
- **B4.** `05-discord-setup.sh`: seed both, with the comment block that section carries for
  everything else.
- **B5.** `ffbox/config.md`: `warm_branches` in the `pools` table and its own prose; a
  `workload_reserve` row beside `max_concurrent_runs`. REQUIRED IN THE SAME COMMIT — the config's
  shape is documented there and CLAUDE.md says so.

## Phase C — choosing branches (M)

- **C1.** `pool_branch_activity(window_secs)` → `{(class, branch): seen}` from `turn` joined to
  `conversation`, `COALESCE(started_at, queued_at)`, non-closed conversations with a branch. No
  git, no filtering: the shed needs the ordering for branches that are no longer candidates.
- **C2.** `pool_branch_candidates(agent_class, containers)` → branches to stage, most recent
  first: activity within that class's window, minus the class's own `pool_branch()`, minus
  anything already staged for that class, minus anything inside its cooldown, and finally
  `mirror_carries()` — asked LAST and only for the branch about to be used, because it forks git.

## Phase D — the reserve and the shed (M)

- **D1.** `pool_shed()`: when `workload_room() < workload_reserve`, claim and stop ONE unclaimed
  evictable spare, oldest activity first, via `pool_take` → `out/retiring` → `_pool_expire_one`.
  Returns the id or None. Sets that branch's cooldown so the next pass does not restage it.
- **D2.** `keep_pool` calls `pool_shed` after the expiry and reap and BEFORE any staging, and
  returns immediately when it shed something. One shed restores the invariant; a second in the
  same pass is shedding for demand nobody has expressed.
- **D3.** `keep_warm_branches(containers)`: at most one evictable staging per pass, only when the
  held loop staged nothing, only while `workload_room() >= workload_reserve + 2` (the dead band),
  and behind `agent_room` and `pool_has_room` exactly as the held loop is.

## Phase E — tests (M)

All in `test_ffwatch.py`, all offline, all added to `main()`'s list.

- **E1.** `effective_pool_tier` answers from the label, and an unlabelled container is held.
  (The `docker ps` PARSING of the new field is covered only by the format string itself; the
  suite has no container-listing fixture to hang it on.)
- **E2.** `effective_pool_tier` demotes a held spare whose branch is no longer its class's pool
  branch, and does not promote an evictable one.
- **E3.** The candidate query: a branch touched inside the window is offered, one outside it is
  not, a closed conversation's is not, the class's own pool branch is not, and a branch the
  mirror does not carry is not.
- **E4.** The reserve: no evictable staging while free places are below `reserve + 2`; the held
  pool is still topped up at the same moment.
- **E5.** The shed: fires only when free places are below the reserve, takes the oldest-activity
  evictable spare, never a held one, and never one with an `out/owner`.
- **E6.** A pass that staged a held spare stages no evictable one.
- **E7.** `load_config` clamps a `workload_reserve` set at or above the ceiling.
- **E8.** The four existing keeper/pool tests still pass, with `warm_branches.count = 0` pinned
  where they assert exact staging lists.

## Phase F — documentation (S)

- **F1.** `ffbox/README.md`: the pool section's **Nothing is evicted** paragraph becomes "nothing
  HELD is evicted" and says what makes the second tier different — a promise against a guess.
  The `/status` table entry gains the new state word.
- **F2.** `design/ffbox_idle_agents_design.txt` section 9 gets a pointer to this design, since
  that is where the eviction rule was set.
- **F3.** `ffbox/config.md` gains a `workload_reserve` section and a `warm_branches` one under
  `pools`, and the example document carries both. Same commit, per CLAUDE.md.

## Order

A → B → C → D → E, with F alongside. A and B are independent of C and D and land first because
everything else reads the label and the config. Nothing is publishable until E: the shed is the
only thing here that destroys a container, and the 2026-09-01 loss was exactly a sweep that
destroyed one it should not have.
