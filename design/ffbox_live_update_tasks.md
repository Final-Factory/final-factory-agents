# ffbox live update: implementation tasks

Derived from `design/ffbox_live_update_design.txt` (2026-09-03) after re-reading the code each
phase touches: `ffwatch.launch()`, `finish_run`, `recover`, `pool_reap`, `sweep_finished_spool`,
the counters (`workload_count`, `agent_workload_count`), `ffbox`'s stage/dispatch/cold paths,
`lib-workloads.sh`, and `update_ffbox.sh`'s drain loop.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more, **?** unknown until
something is measured.

## Status, 2026-09-03 — implemented and live

All of V through G landed on the build server the same day, one commit per phase, verified end to
end: a real turn was launched detached, its container was renamed at dispatch, and a later pass
finished it and posted the answer.

Phase V settled all three facts, and two of them mattered:

- a file bind mount KEEPS ITS INODE when git replaces the source. The host inode changed and the
  container went on reading the old bytes for the whole run. So the task script and ffverify were
  never changed under a running container; the plugin DIRECTORY was, and that was the real bug.
- `docker run --rm` is performed by the DAEMON. A client killed mid-run leaves the container to
  exit and be removed with nobody able to ask what it exited with. That is what made dropping
  --rm necessary rather than tidy.
- a container outlives the shell that created it, which is what the whole design rests on.

Live evidence from the first turn through the new path, run 68 (`d56t1-13ea10a2`):

    run d56t1-13ea10a2: container is up; the finish pass owns it from here
    pool: 0c6a7ca8's container is gone but its run has not been finished; leaving the spool alone
    pool: 0c6a7ca8 finished; swept 1 transcript(s) home

The middle line is B7 — the guard pool_reap only ever had by accident — firing in the window the
design predicted it would matter in.

Two things were found by running it rather than by writing it, and both are fixed:

1. **A detached dispatch orphaned a `docker wait`.** That line sits above the detach exit, so
   every dispatched run left a process waiting for hours on a container nothing would hear about
   — and its redirect created `out/.container-rc` EMPTY, which a less careful reader would score
   as a failed run. Skipped when detaching; the container writes its own status and the host asks
   docker for the rest.
2. **A config key from a newer build killed every older `ffwatch` invocation.** Not part of this
   plan, found while landing it, and it had the box wedged: see the gap list below and the commit
   "a config written by a newer ffbox must not kill an older one".

Three tasks were missed on the first pass and landed after a check of this list against the
code: **B8** (the harvest ceilings recorded in the run directory), **E8** (the contract file and
its two constants) and **G2** (the clock on the run's page). B8 and E8 turned up a real defect
while being written — the `--finish` path had the harvest ceilings *and* the contract constant
inside the container guard, so they were simply undefined on it. The first `--finish` test did
not catch it because a run with no work bundle never reaches them, and `set -o pipefail` turned
the second one into an exit nobody would have read as "unbound variable".

What is NOT done, deliberately:

- **D5 is not applicable as written.** It said to remove ffbox's clock loop after comparing the
  two enforcers for a release. Phase E removes the loop from the executor path by construction —
  a detached ffbox does not reach it — so there is nothing left to compare. The loop stays for
  `--direct`, where a human is watching, and that is the right home for it.
- **The dispatch rename stays.** Section 4a says land the ids, move every reader onto them, and
  remove the rename afterwards. The readers have moved and the updater no longer classifies by
  name, so the prerequisite is met; removing it is its own change and its own commit.

## What already exists

Worth knowing before estimating.

- **`recover()` already reaches the adoption branch.** It skips a non-terminal run whose
  container is live (`ffwatch.py:8171`) and then does nothing with it. Adoption is a body for a
  branch that is already there, not a new call site.
- **Everything `finish_run` needs is already on disk except two numbers.** `job.json` is written
  before the container starts, `turn`/`conv` are rows, `run_dir` is derivable. Only `rc` and
  `wall` live nowhere but the launching process, and `wall` is `run.started_at` subtracted from
  now.
- **`.container-rc` already exists on the dispatch path.** `ffbox:1065` backgrounds
  `docker wait` into it. The cold path is the one that has no equivalent.
- **The pool already decides busy by a file, not a process.** `pool_unclaimed` tests `out/owner`,
  `pool_expire` skips a container that has one, `pool_drop` refuses a claimed spool. An adopted
  pooled run is safe from all three with no change.
- **Every ceiling counter is `docker ps`.** `workload_count`, `agent_workload_count` and
  `lib-workloads.sh`'s `ffbox_workload_count` all filter on labels over running containers, so a
  surviving container goes on counting correctly across a restart and an exited one stops
  counting the moment it stops. Checked so nobody re-derives it; there is no task here.
- **Slot claims survive a restart already**, keyed by container id and validated against
  `docker ps`. Design section 4b. No task.
- **`reconcile_publications()` runs every pass**, so the design's assumption that a half-finished
  publish can be looked at again is the existing shape rather than a new one.
- **`ffbox --mount` is repeatable and validated**, so the run-private mounts in Phase C need no
  argument-parser work.
- **`ffstatus` reads the `ffbox.slot` label off the container** (`ffstatus.sh:461`), not the slot
  file, so Phase A's labels are the surface it already uses.

## Design gaps closed while writing this

Twelve places where the design's prose and the code disagree, or where the design assumed
something the code does not do. Each is settled here and the design has been amended to match.

1. **Excluding `runs` from `ffwatch quiet` does not make the update stop waiting.** Design
   section 8 said the settle predicate keeps `turns` and `outbound` and drops `runs`. But `turns`
   counts `turn.status='running'`, and an adopted twenty-hour run holds that status for twenty
   hours, so the updater would wait exactly as long as before. **Decision:** the tail predicate is
   a new count, `publishing` — turns marked running whose run row is terminal, plus turns marked
   running whose run row names no live container. That is "the host is still working on a turn
   whose container is gone", which is what the update actually has to wait for. `settling()`
   returns four counts; `quiet --host-only` sums `publishing` and `outbound`.

2. **A pooled container cannot have `--rm` dropped after dispatch.** Design section 5 says drop
   `--rm` from the agent containers, but a staged container is created with `docker run --rm -d`
   (`ffbox:983`) and dispatch only renames it. Flags are creation-time. **Decision:** drop `--rm`
   from the staged container too, so both routes behave alike, and give `pool_drop`,
   `_pool_expire_one` and `pool_reap` an explicit `docker rm` by id. Uniformity is worth one
   extra call; two lifecycles is what produces the bug nobody reproduces.

3. **`pool_reap` protects a live run's spool only by accident.** It refuses a spool that still
   holds a transcript, and `sweep_finished_spool` refuses to move one whose run is non-terminal,
   so the two together happen to protect a dispatched run. A run whose container exited before
   writing any transcript has no such protection, and today the window is milliseconds because
   ffbox moves `out/` immediately after `wait`. Under this design the window is up to a poll
   interval. **Decision:** `pool_reap` skips any spool whose run row is non-terminal, directly and
   by that test, rather than relying on the transcript guard to imply it.

4. **Nothing records where a run's `out` directory is.** It is `$RESULTS/$RUN_ID` for a cold run
   and `$POOL_HOME/out` for a dispatched one (`ffbox:565`, `ffbox:633`), and it MOVES to the run
   directory after `wait` (`ffbox:1181`). The clock pass, `finish_runs` and `ffbox --finish` all
   need to know which. **Decision:** add `run.out_dir`, written at INSERT and rewritten to the run
   directory after the move — and the move becomes ffwatch's, because ffbox no longer waits around
   to do it. This also settles what `ffbox --finish` is given: exactly one directory, after the
   move, with no need to know whether the run was pooled.

5. **`.container-rc` is written outside `out/`.** `ffbox:1065` writes it to
   `$POOL_HOME/.container-rc`, so it does not travel with the move at `ffbox:1181` and
   `ffbox:1188` deletes it. **Decision:** write it inside the out directory on both routes, so one
   path answers "what did this container exit with" whoever is asking and whenever.

6. **Removing the dispatch rename would break the updater, badly.** Design section 4a proposes
   dropping `docker rename` once nothing depends on the name. `update_ffbox.sh` tells an idle
   staged container from a busy dispatched one by NAME PREFIX
   (`ffbox-agent-pool-*|ffbox-dev-pool-*|ffbox-pool-*`), and destroys what matches. Without the
   rename every dispatched container matches, and the updater destroys containers serving turns —
   the exact shape of the 2026-09-01 loss of conversation 30's turn 5, which is what put the
   `out/owner` rule in the design in the first place. **Decision:** the updater stops classifying
   by name before the rename is touched. It asks `ffwatch drain`, which already decides by
   `out/owner`; when ffwatch cannot answer it LEAVES CONTAINERS ALONE rather than guessing. That
   default is now free, because nothing waits on them. Hard ordering constraint: F3 lands before
   the rename is removed, and the removal is not in this plan.

7. **The subprocess timeout in `launch()` does not disappear, it shrinks.** Design section 11 said
   nothing bounds a run once it goes. **Decision:** ffbox now returns as soon as the container
   exists, so `subprocess.run(timeout=...)` becomes a bound on CREATION — 300 seconds — and the
   run is bounded by the clock file instead. Keeping a timeout matters: a wedged `docker run` must
   not hold a launch thread for ever.

8. **The container-side failsafe is load-bearing and was an open question.** Sections 7 and 10
   assume a container is always bounded, and the clock file is written and read by the HOST. With
   no daemon there is no reader — reachable two ways: `ffbox "prompt"` on a box whose ffwatch is
   down drives passes itself and can be ctrl-C'd, and an ffwatch that never comes back leaves its
   containers with a deadline nobody enforces. Today the ffbox trap covers both by killing the
   container, and this design removes that. **Decision:** the turn task carries its own failsafe
   at its clock plus a margin, the way `pool-task.sh` already does for a staged container. It
   moves from open question 5 to task E5, in the same phase as detachment, and detachment does not
   land without it.

9. **`finish_runs` has to be in `once()` as well as `run()`.** The daemon loop does not call
   `once()`; it drives the same steps itself. The idle-agents work recorded the exact cost of
   forgetting that — the keeper went into `once()`, the daemon ran `run()`, and the live box
   staged nothing while reporting "0 staged, 1 wanted". Not a design error; an implementation trap
   with a name.

10. **`ffbox --finish` needs the harvest ceilings, which are ffbox's own defaults.**
    `MAX_CHANGED_FILES`, `FORBIDDEN_PATHS_RE`, `MAX_BUNDLE_BYTES`, `PROTECTED_BRANCHES` and the
    mirror path are read from the environment with built-in fallbacks, so a `--finish` invocation
    that sets none of them gets the same answers as the run would have. **Decision:** no plumbing
    needed, but the ceilings are recorded in the run directory at launch so a later `--finish`
    under changed config cannot be more permissive than the run it is finishing.

11. **The contract version needs a home in two languages.** Design section 5 introduces it without
    saying where the constant lives. **Decision:** one integer in `ffwatch.py` beside
    `CAPABILITIES` and one in `ffbox`, checked by `--finish` and by `finish_runs`, with the same
    lockstep note the three copies of the Unity machine-id constant already carry.

12a. **A config written by a newer ffbox killed an older one.** Not from this design; found on
    the build server at 12:28 on 2026-09-03 while landing phase D, and it had the box wedged.
    Several checkouts share one `~/.config/ffbox/config.json` and `setup.sh` seeds new keys into
    it every pass. A newer checkout wrote `cluster.compact_turns`; the checkout the services run
    from was one commit older and had no such default, and `config_warnings` does
    `DEFAULTS["cluster"][key]` on every invocation. So `ffwatch drain` died — no drain flag, so
    the keeper went on staging — and `ffwatch quiet` died, so the updater could never see the box
    go quiet. It spent its whole hour destroying every container the undrained keeper had just
    staged, once every fifteen seconds, and the only way out was to force at the end of the
    window. **Decision:** an unknown key is reported and ignored. The config file is shared and
    the code is not, so a config from the future is a normal state on this machine. This is the
    same forward-compatibility contract gap 11's contract version exists for, one layer down.

12. **`FFBOX_DRAIN_TIMEOUT` should not be joined by a second knob.** The design named
    `FFBOX_SETTLE_TIMEOUT` for the shorter window, next to an existing `FFBOX_FORCE_SETTLE_SECS`
    that means something else. Three knobs for two ideas. **Decision:** keep
    `FFBOX_DRAIN_TIMEOUT`, change its default from 3600 to 300 and its meaning to "how long to
    wait for the host-side tail". The 3600 lives on as the default under
    `update.stop-running`, where waiting for containers is the point.

---

## Phase V — verify on the box, before anything is written

Three facts the design infers rather than measures. All three are quick, and getting one wrong
invalidates a phase.

**V1 (S)** Does a bind mount of a FILE survive git replacing its source? Start a container with a
file mounted, `git checkout` a change to it on the host, read it from inside. Settles
self_update_design fact (g) and tells us how urgent Phase C is. Expected: the container keeps the
old bytes.

**V2 (S)** Does `docker run --rm` remove the container when the client is killed and the container
exits afterwards? Settles how much of Phase B's exit-code work is recovering a real loss.
Expected: yes, the daemon does it, which is why `--rm` has to go.

**V3 (S)** Does a container survive `systemctl stop ffbox.target` with ffbox's trap taken out of
the path? Confirms self_update_design fact (h) as corrected. Do it by hand with a throwaway
container, not by editing the trap on a live box.

## Phase A — identity that does not move

Design section 4a. Everything else depends on having a handle that survives a rename and a
restart.

**A1 (S)** `--label ffbox.run.id=<run id>` on the cold `docker run` in ffbox. Creation-time, so it
survives a rename; a staged container already carries `ffbox.pool.id` and needs nothing.

**A2 (S)** ffbox writes the container id to `<out>/container-id` as soon as the container exists,
on both routes. It already asks docker for the id for the slot confirm; this writes down the
answer.

**A3 (S)** `run.container_id`, a new column, populated by ffwatch from `<out>/container-id` after
ffbox returns. Additive migration, NULL for every existing row.

**A4 (S)** `container_live()` takes an id or a label and falls back to the name for a NULL
`container_id`. The fallback is for rows written before A3 and can be removed once none are left.

**A5 (S)** Move `docker wait`, `docker logs`, `docker inspect` and the new explicit `docker rm`
onto the id. Grep for `container_name` and leave only the readable uses.

## Phase B — the run directory carries the facts

Design section 5, minus the contract file. Worth landing on its own.

**B1 (S)** `run.out_dir`, written at INSERT: the pool spool's `out` for a dispatched run, the run
directory for a cold one. Gap 4.

**B2 (S)** Write `.container-rc` inside the out directory on both routes. Gap 5.

**B3 (S)** The container task writes its own exit status to `<out>/.container-rc` from its finish
trap, so the answer exists even when nothing was watching.

**B4 (M)** Drop `--rm` from the cold run AND from `--stage-pool`, and remove containers explicitly
by id: after `finish_run` writes a terminal state, in `pool_drop`, in `_pool_expire_one`, and in
`pool_reap`. Gap 2.

**B5 (S)** A sweep for containers nothing removed — exited, carrying `ffbox.workload`, older than
an hour — on the same pass as the reaper. This is the backstop for an ffwatch that never came
back, and section 4b is why it does not have to be prompt.

**B6 (M)** Harvest a crashed run's directory instead of discarding it. If `terminal_state` has to
be `crashed` but the directory holds a work bundle and a result, publish and reply from them and
say the supervision was lost. This is the 2026-09-01 fix.

**B7 (S)** `pool_reap` skips a spool whose run row is non-terminal, by that test rather than via
the transcript guard. Gap 3.

**B8 (S)** Record the harvest ceilings in the run directory at launch. Gap 10.

## Phase C — immutable run inputs

Design section 4. Independent of the rest, and it makes the CURRENT drain-and-merge safe by
construction rather than by inode luck.

**C1 (M)** `<run-dir>/mounts/` holding copies of the task script, ffverify and the plugin
directory; mount from there on the cold path. 347 KB in 19 files, measured 2026-09-03, so a plain
`cp -a`.

**C2 (S)** The same for a staged container, into its spool at stage time, since it carries
`turn-task.sh` and ffverify from creation.

**C3 (S)** Mount `/opt/ffcache/unity` as a read-only DIRECTORY instead of the `.ulf` file, so a
host refresh is visible to a container that is already running.

**C4 (S)** `unity-license.sh` re-copies when the mounted `.ulf` is newer than the container's own,
before each editor launch, rather than only when it has none.

**C5 (S)** ffwatch calls `unity-offline-license.sh ensure` on its poll loop. One sed and no
network when there is nothing to do; without it a twenty-hour container never sees a fresh
licence however it is mounted.

**C6 (S)** Whatever launches the editor tolerates a licence that went stale between two launches
in one run, rather than failing the run on it.

## Phase D — clocks as deadline files

Design section 6.

**D1 (S)** `<out>/clock` in `lib-workloads.sh`'s two-key format plus a `phase=` key, written by
ffbox at creation with the warmup ceiling.

**D2 (M)** A stateless clock pass on ffwatch's loop: for every non-terminal run read the clock,
notice a newer `.agent-started` or `.verify-started` and rewrite the phase, and soft-stop with
`docker stop --timeout max(kill_grace, 120)` when the deadline has passed, on a thread.

**D3 (S)** Write `ffbox-timeout` from that pass, in the same words the ffbox loop uses, so
`finish_run`'s existing scoring needs no change.

**D4 (S)** Leave ffbox's own loop in place for `--direct` and running in parallel elsewhere for
one release, and compare. The two must agree before D5.

**D5 (S)** Remove the clock loop from ffbox's executor mode. Not before D4 has run on the live
box.

## Phase E — detach, adopt, finish

Design section 7. The phase that changes behaviour.

**E1 (M)** ffbox executor mode creates the container detached, waits only for it to exist,
confirms the slot, writes the clock, and returns. Its EXIT trap stops the container only on a
failure before creation succeeded, and in `--direct`.

**E2 (S)** `launch()`'s subprocess timeout drops to 300 seconds and means creation. Gap 7.

**E3 (L)** `finish_runs()`: for every non-terminal run, leave a live one alone, and for a gone one
take the conversation lock, move a pooled `out/` into the run directory, rewrite `run.out_dir`,
read `rc`, `wall`, `job` and the timeout kind off disk, call `ffbox --finish`, then the existing
`finish_run` and everything downstream. On a thread, one per run.

**E4 (M)** `ffbox --finish <dir>`: the harvest validation with no container started, refusing an
unknown contract version. This is the existing `harvest_from_out` and its callers behind a flag,
not new logic.

**E5 (M)** A failsafe in the turn task: its own deadline at the clock plus a margin, the way
`pool-task.sh` already carries one. Gap 8. E1 does not land without this.

**E6 (S)** Adoption: the `continue` at `ffwatch.py:8171` stamps `run.adopted_at`, logs the
container's age and the turn, and leaves the row alone. A pooled run with no `in/dispatch` is not
adopted; it is dropped and requeued as today.

**E7 (S)** `finish_runs` in `once()` AND in `run()`. Gap 9.

**E8 (S)** The `contract` file and its two constants. Gap 11.

**E9 (S)** `finish_runs` tolerates a missing conversation row: record the run, skip the reply, do
not raise.

## Phase F — the update protocol

Design section 8. By this point it is mostly deletion.

**F1 (S)** `settling()` gains `publishing`, and `quiet` gains `--host-only`. Gap 1.

**F2 (M)** `update_ffbox.sh` stops waiting for containers: the `_busy` loop goes, and what is left
waits on `ffwatch quiet --host-only` bounded by `FFBOX_DRAIN_TIMEOUT`, now 300. Gap 12.

**F3 (M)** The updater stops classifying containers by name prefix. It destroys what `ffwatch
drain` reports as unclaimed, and leaves everything else alone — including when ffwatch cannot
answer at all. Gap 6, and the hard prerequisite for ever removing the rename.

**F4 (S)** `update.stop-running` and `FFBOX_UPDATE_STOP_RUNNING=1`: one pass of the old behaviour,
with the old 3600-second window, for a fix that has to apply now.

**F5 (S)** `FFBOX_MAX_CONTAINER_AGE`, default 48 hours. A container older than that is soft-
stopped by the update rather than adopted again.

**F6 (S)** One journal line per surviving container: name, age, turn. An operator reading an
update log has to be able to see what the box is still carrying.

**F7 (S)** Assert in `setup.sh` that the docker daemon is never restarted by a non-interactive
run, rather than leaving it as a consequence of `--non-interactive` skipping root stages.

**F8 (M)** `ffbox-egress.sh up` defers a recreate while any `ffbox.workload` container is attached
to the fence, unless forced, and logs the deferral. Without it an allowlist change cuts egress
under a twenty-hour run.

## Phase G — make it legible

**G1 (S)** ffstatus and ffweb show an adopted run as adopted and from when, and show container
age.

**G2 (S)** The clock deadline on the run row in ffweb, read from the clock file the same way
ffstatus reads the pool's.

**G3 (S)** A line in the ffbox README on what an update does and does not stop, because the next
person to wonder will look there.

**G4 (S)** The `_help` block in `config.json` says that clocks, ceilings, networks and capability
lists apply to containers created afterwards and never retroactively.

## Tests

All offline, in `test_ffwatch.py` unless said otherwise. `once()` is what the suite drives, which
is why E7 exists.

**T1** A run whose container is live at startup is adopted, keeps its turn `running`, and is not
requeued.

**T2** A run whose container is gone at startup is finished from the directory — including the
case with a work bundle and no exit code, which is B6.

**T3** `finish_run` and `publish` called twice on one run produce one branch, one pull request and
one reply.

**T4** A clock file that has passed produces a soft stop and an `ffbox-timeout`, from a pass rather
than from a supervisor.

**T5** A drain destroys unclaimed staged containers and leaves a claimed one alone — this test
exists — and the updater does not WAIT on the claimed one.

**T6** An unknown contract version stops the container and records the refusal.

**T7** A pooled container renamed but never dispatched is not adopted.

**T8** A run is found and finished after its container has been renamed. This is the test that
stops anything drifting back onto the name.

**T9** An exited-but-not-yet-removed container holds neither a place under the ceiling nor its
slot number, and is removed by the B5 sweep.

**T10** `pool_reap` leaves the spool of a non-terminal run alone even when it holds no transcript.
Gap 3, and it needs a spool fixture with an empty `claude/`.

**T11** `settling()` reports a twenty-hour run as not publishing, so `quiet --host-only` returns
quiet with a container up. Gap 1, and it is the test that would have caught it.
