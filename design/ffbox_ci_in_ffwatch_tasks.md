# ffbox: the CI lane inside ffwatch — implementation tasks

Derived from `design/ffbox_ci_in_ffwatch_design.txt` (revision 3, 2026-09-08) after reading the
code both lanes actually run: `runners/slot.sh`, `runners/lib/config.sh`, `runners/lib/gh.sh`,
`runners/lib/mirror.sh`, `runners/reap.sh`, `runners/05-services.sh`, `runners/ffgithubrunners`,
`ffwatch.py` (`keep_pool`, `recover`, `adopt_run`, `settling`, `drain`, the daemon loop),
`update_ffbox.sh`, `pool-task.sh`, `lib-workloads.sh`, and the game repo's
`.github/workflows/main.yml` and `.github/actions/ffghr-artifact-handoff/` read out of the mirror
at `/opt/ffcache/mirror/FinalFactory.git`.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more, **?** unknown until
something is measured.

**On citations.** Shell files are cited by line, because they are small and change rarely.
`ffwatch.py` is cited by SYMBOL, and that is not a style preference. It is 15,272 lines and
several commits a day land in it: while this pair of documents was being written its line numbers
moved twice, once by 3 and once by 248, and both times every reference in them broke. Sampled the
same day, 19 of 20 `ffwatch.py:NNNN` citations across the rest of `design/` already point at
unrelated code. A function name survives what a line number does not.

Every phase letter matches section 12 of the design. Phases are ordered; tasks inside a phase are
not, unless one says so.

## What already exists

Worth knowing before estimating, because most of D is porting rather than inventing.

- **The image is already one image with a mode switch.** `FFBOX_MODE=ci` at `slot.sh:407`,
  read at `entrypoint.sh:33`. Nothing about the container changes in this work.
- **ffwatch already counts CI containers.** `workload_count()` in `ffwatch.py` reads
  `ffbox.workload` and treats `ci` as one of three kinds. The ceiling arithmetic is done.
- **ffwatch already adopts containers across its own restart.** `recover()` in `ffwatch.py`
  and `adopt_run()` in `ffwatch.py`, whose body is deliberately empty of work.
- **ffwatch already separates what a stop loses from what survives it.** `settling()`
  in `ffwatch.py` and `HOST_TAIL`.
- **The updater already applies this design's container rules from outside.** It leaves busy CI
  containers alone and removes idle ones (`update_ffbox.sh:459-468`), and waits only on
  `ffwatch quiet --host-only` (`update_ffbox.sh:517`).
- **Every clock is already a file.** `ffghr_mark_busy` / `ffghr_mark_idle`
  (`runners/lib/config.sh:696`, `:701`); `work_deadline()` (`slot.sh:514`) derives rather than
  remembers, so a restarted supervisor lands on its predecessor's deadline.
- **The agent lane already holds the same handshake open for four hours.**
  `pool-task.sh:147` polls for a host-written file; `pool-task.sh:41` sets `TTL` to 14400. This is
  fact (n) and it is why phase A2 is two constants rather than a new component.
- **Phase A has landed** (`5d4efbc`, `cdc2da9`): unit instances are sized to
  `max_concurrent_runs`, `ffgithubrunners slots N` needs no root and no restart, and
  `ffghr_reload_limits` no longer forks a python3 per poll.

---

## Phase A2 — make the job patient  (design 5c)

The merge's only hard-failure mode, removed by two constants. Both are testable **under today's
supervisor**: a job with a ten-minute allowance behaves identically to one with two minutes as
long as somebody answers, and today somebody always does. So this lands first and is simply
correct later.

- [x] **A2.1 — the host sets the artifact wait.** `S` — DONE
  `_ffghr_set ARTIFACT_WAIT_SECS artifact_wait_secs 600` in `runners/lib/config.sh`, and
  `-e FFGHR_ARTIFACT_WAIT="$ARTIFACT_WAIT_SECS"` on the `docker run` in `slot.sh`. The action
  already reads that variable (`ffghr-artifact-handoff/index.js:28`, `|| 180`) and nothing sets it
  today, so **no game-repo change is needed for this half**.
  Config shape moves, so `ffbox/config.md` is edited in the same commit — CLAUDE.md's rule.

- [~] **A2.2 — the host sets the mirror wait.** `S` (this repo, DONE) + `S` (game repo, OWED)
  `_ffghr_set MIRROR_WAIT_SECS mirror_wait_secs 600` and
  `-e FFGHR_MIRROR_WAIT="$MIRROR_WAIT_SECS"` beside it. Then in the game repo, main.yml's
  "Wait for the host git mirror" step stops hardcoding `40` and computes its loop bound from
  `FFGHR_MIRROR_WAIT` (seconds) over its 3-second poll, falling back to today's 120 when the
  variable is absent, so an old host and a new workflow still agree.
  **Two commits in two repositories.** The host half landed first, deliberately: a workflow that
  does not yet read `FFGHR_MIRROR_WAIT` simply ignores it and keeps its 120, which is today's
  behaviour, so the host change is inert until the game repo catches up.
  **STILL OWED:** main.yml's `n -lt 40` becomes a bound computed from `FFGHR_MIRROR_WAIT` over its
  3-second poll, falling back to 40 when the variable is absent. Until that lands, phase D must
  not ship — the 120-second fuse is still live and it is the merge's only hard-failure mode.

- [x] **A2.3 — a test that the two variables reach the container.** `S` — DONE
  In `runners/test_pool.sh` or a new `test_slot_env.sh`: render the `docker run` argument list
  without a daemon and assert both `-e` flags are present with the configured values. Cheap, and
  it is the only thing standing between a rename and a silent return to 120 seconds.

- [x] **A2.4 — fix the stale comment in `lib/mirror.sh`.** `S` — DONE
  The failure branch says it writes `fetch.done: failed` so the job "stops waiting and goes to
  GitHub". github.com left the CI allowlist on 2026-08-31 (`runners/egress/allowlist.txt:28`);
  there is nowhere to go. The behaviour is right and the sentence is wrong. Design open question
  (a) records this. Independent of everything else here.

---

## Phase B — an identity that survives a restart  (design 4a, 4b)

Both land while `slot.sh` is still the supervisor, which is the point: they are testable before
anything structural moves.

- [ ] **B.1 — the staging directory is keyed by container name.** `M`
  `ffghr_cache_stage_dir` (`runners/lib/config.sh:484`) takes a container name instead of a slot
  number and returns `$FFGHR_CACHE_STAGING/<container name>`. Callers: `slot.sh` (creation,
  teardown, every staging reference) and `reap.sh` (the staging sweep, which currently reasons in
  slot numbers).
  Phase A's deployment is the argument: the moment units outnumbered the ceiling, containers
  landed on slots 2, 3, 5 and 8, and a slot number stopped correlating with anything.
  **Leaves litter on upgrade:** existing `slot-N` directories belong to no container under the new
  rule. `reap.sh` gets a one-release sweep for the old shape, and it is deleted afterwards.

- [ ] **B.2 — `ffghr.owner` replaces `ffghr.supervisor.pid`.** `S`
  A constant label that does not change when the daemon restarts. `slot.sh` sets it; `reap.sh`'s
  orphan test becomes "no live owner process on this box" rather than "this pid is not a
  `slot.sh`".
  **Both labels are written for one release** and reap accepts either, or a container started
  before the upgrade reads as an orphan and is removed mid-job. Drop the pid in the release after.

- [ ] **B.3 — tests for both.** `S`
  Offline, in `test_pool.sh`'s style: the stage path is derived from the name; the orphan test
  says "live" for a container whose owner is running and "orphan" for one whose owner is gone;
  and a container carrying only the old pid label is still recognised during the overlap.

---

## Phase C — a versioned staging protocol  (design 9e)

- [ ] **C.1 — the container writes its protocol version; the host refuses one it does not know.**
  `S`
  A `protocol` file in the staging directory at container start. A host that does not recognise
  the version answers requests with the failure form (`fetch.done: failed`) and logs loudly,
  rather than guessing at a wire format a different commit wrote.
  Today this cannot bite, because `slot.sh` does not restart mid-job. Under D it can, which is why
  it lands here, under the supervisor that cannot yet get it wrong.

---

## Phase D — the daemon grows the CI lane  (design 3, 4, 6, 7)

Land with `slot.sh` still present and `githubrunner.pool.max` at 0, so nothing real runs on the
new path. The keeper and the serving pass are exercised against containers a test harness starts.

- [ ] **D.1 — `keep_ci_pool()`.** `M`
  The two conditions of `ffghr_pool_admit` (`runners/lib/config.sh:746`), reading the counters
  `keep_pool()` already reads, minting at most one runner per pass. Inside `owns_lock` (see the
  daemon-lock warning in `ffwatch.py`'s `run()`), or two daemons would both mint (design 9d).
  Returns early on `killed()` and `draining()`; `config_failsafe()` is design open question (c)
  and must be decided here, not discovered.

- [ ] **D.2 — `serve_ci_runners()`.** `L`
  The loop half of `slot.sh`, once per daemon pass: flip idle to busy on `Runner.Worker`, write
  the busy marker, decide the cache archive from `branch.info`, serve `fetch.request`, upload on
  `artifact.request`, enforce the two deadlines, and hand a container whose job has ended to the
  teardown path.
  **Blocking work goes to a thread keyed by container** — the mirror fetch is ~4.6s, the upload is
  a transfer, `docker stop` is the grace. `_pool_expire_one()` in `ffwatch.py` is the pattern.
  A guard so no two threads serve one container.
  **And the poll rate must not drop** (design 3). `slot.sh` polls every 5s while a runner is idle
  because that interval is the latency between "a job arrived" and "a replacement is registered",
  which is CI queue time. ffwatch's loop is `poll_secs` (5) with a doorbell, so it lands in the
  same place — but if this pass ever needs to be slower, it gets its own clock inside the pass
  rather than slowing the loop.

- [ ] **D.3 — the CI launcher.** `M`
  The `docker run` of `slot.sh:390-413` in python: `ffghr-net`, the read-only cache mount, the
  staging mount, the licence, the machine id, `FFBOX_MODE=ci`, the labels, and the JIT config
  through the environment rather than argv.

- [ ] **D.4 — credentials, by subprocess.** `M`
  `gh_mint_jitconfig`, `gh_delete_runner` and `gh_post_check_run` are called by running
  `runners/lib/gh.sh`, not ported. It is working, audited, and its token cache is one line.
  A python port means a new dependency (PyJWT/cryptography) or a hand-rolled RS256 through
  `openssl`, which is what `gh.sh` already is. Design section 7.

- [ ] **D.5 — adoption.** `S`
  In `recover()`: list `label=ffbox.workload=ci`, write a row for any container with none, log one
  line each. Nothing else — the serving pass carries them (design 4). Idempotent because it is
  derived from `docker ps`, so no `adopted_at` equivalent is needed (design 9b).

- [ ] **D.6 — `ci_publishing` in `settling()`.** `M`
  CI containers that have exited with teardown still owed. Joins `HOST_TAIL`. `ci_runners` is
  **not** counted: the container survives the stop, which is the whole of requirement 3.

- [ ] **D.7 — the pool numbers are re-read, not held.** `S`
  `keep_ci_pool` stats `config.json` and re-parses on a change, rather than using the dict
  `load_config()` produced at startup. Otherwise raising a CI ceiling by one triggers the config
  restart, which is the restart this design spends section 5 avoiding. Design section 6.

- [ ] **D.8 — tests.** `M`
  Against a stub daemon in `test_ffwatch.py`'s style: admission at and under the ceiling; adoption
  of a container with no row; a container that exits between passes reaching teardown; two threads
  never serving one container; `settling()` counting a teardown and not counting a running job.

---

## Phase E — cut over on one box  (design 12E)

**Ordered, unlike the others.** E.3 runs before E.1: the design asks for the window measured
before the cut-over, and once `slot.sh` is deleted the before-number cannot be taken any more.
E.6 is last by definition.

- [ ] **E.1 — delete `slot.sh` and the unit template.** `M`
  `05-services.sh` stops rendering slot instances and **must disable the instances it previously
  enabled**, or twelve units linger and fail on a missing script. Keep the timers and the egress
  units. `runners/systemd/ffgithubrunners@.service` goes.

- [ ] **E.2 — the pool half of `lib/config.sh` goes.** `S`
  Admission, the counts, the markers' writers and the two coercions move into the daemon. What
  stays is the credential, image, network, cache and licence configuration, which `reap.sh` and
  the CLI still source. `ffghr_slot_units` and `ffghr_enabled_slots` go with the units.

- [ ] **E.3 — measure the stop-to-start window. FIRST, before E.1.** `S`
  Design open question (b). No longer a gate — the question is "is 600 comfortably more than it",
  not "does it fit under 120" — but it should be a number in the journal rather than an
  impression, and it would want revisiting if the update ever grew a cold image build. Taken
  before the cut-over so there is a baseline to compare the after against; `slot.sh`'s deletion
  makes the before-number unobtainable.

- [ ] **E.4 — settle what replaces `slot stop N`.** `S`
  Design open question (e). An operator can quiesce one slot today; with no slots there is nothing
  to quiesce, and lowering `max` does not choose which runner goes. Whether anyone has ever needed
  to pick one is not known — find out before deleting the verb, and if the answer is no, delete it
  and say so in the CLI's own help.

- [ ] **E.5 — check the Unity seat accounting did not change.** `S`
  Design open question (d). Both lanes present the same pinned machine id and share one `.ulf`,
  and the stop grace already goes through `ffbox_stop_grace`, so this design does not believe
  anything moves. It is a belief, and the cost of it being wrong is leaked seats, so verify rather
  than assume: one job through the new path, and confirm the seat comes back.

- [ ] **E.6 — restore `pool.max` and watch one real day.** `?`
  What to watch: no orphaned registrations after an update, no job failing its checkout within
  two minutes of one, and `ffstatus.sh` unchanged throughout (design 5e).

---

## Phase F — the updater  (design 5b)

Only honestly testable once D and E are real.

- [ ] **F.1 — `ffwatch drain` destroys idle CI runners and deletes their registrations.** `M`
  The daemon holds the credential, so it closes the leak the updater's bare `docker rm -f` leaves
  for the next reap (design fact l). Carry over `idle_stop_ok`'s re-check (`slot.sh:566`): a
  runner that takes a job in the moment before the stop is detached, not killed.

- [ ] **F.2 — delete the updater's own `ffghr.slot` loop.** `S`
  `update_ffbox.sh:459-468`, **in the same commit as F.1**. Two things deciding which runner is
  idle, on the one pass where being wrong costs a job, is worse than either alone.

- [ ] **F.3 — a pool-only config edit stops triggering a restart.** `M`
  The updater compares a parsed document rather than a file hash, so a change confined to
  `githubrunner.pool` is not a restart trigger. Without this, raising a CI ceiling still costs the
  restart that opens the window. Design section 6.

- [ ] **F.4 — `STOP_RUNNING` still stops everything.** `S`
  Design fact (m): the escape hatch is the only path that may end a live CI job, and it must keep
  working. A test, or at minimum a deliberate exercise on the box.

---

## Documentation, in the commits that change the behaviour

- [ ] **DOC.1** — `ffbox/config.md` for any config shape that moves (A2.1, A2.2). Required in the
  same commit; CLAUDE.md's rule.
- [ ] **DOC.2** — `ffbox/runners/README.md`: the CI lane's operational section, substantially, at
  phase E. Most of it describes a per-slot supervisor that will not exist.
- [ ] **DOC.3** — `ffbox/README.md`: the lane description, at phase E.
- [ ] **DOC.4** — `design/ffbox_unified_runners_design.txt` section 5, amended rather than left to
  read as a refusal of this document. Its argument is against merging **dispatch** and it stands;
  it does not reach supervision. Design section 0.

---

## Deliberately not doing

- **Merging dispatch.** GitHub decides which job runs where and nothing here touches that.
- **A standalone mirror answerer.** Proposed in revision 2 and withdrawn in revision 3: once the
  job's patience exceeds the window (A2), there is nothing for it to defend against.
- **Folding `reap.sh` into the daemon.** It is the cleanup for "the daemon is broken" and must not
  be inside the thing that broke (design 5d).
- **Retiring `lib-workloads.sh`'s cross-process ceiling lock.** Deleting `slot.sh` removes its CI
  caller, so within the daemon the CI/agent ceiling decision becomes ordinary local state (design
  9g). The lock itself stays, because ffbox's own runs are still a separate process taking it.
  Moving those into the daemon too is a different piece of work and is not proposed here.
