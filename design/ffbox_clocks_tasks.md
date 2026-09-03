# ffbox clocks: implementation tasks

Derived from `design/ffbox_clocks_design.txt` (2026-09-02) after reading the code both lanes
actually run: `runners/slot.sh`, `runners/lib/config.sh`, `runners/reap.sh`, `pool-task.sh`,
`ffbox` (the clock loop), `ffwatch.py` (`pool_reap`, `pool_warm`, `keep_pool`), `ffstatus.sh` and
`ffweb.py`'s `/status` renderer.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more, **?** unknown until something
is measured.

## What already exists

Worth knowing before estimating, because most of this design is wiring rather than invention.

- **The job's start time is already on disk.** `ffghr_mark_busy` (`runners/lib/config.sh:608`)
  writes `at=<iso>` into `state/<container>.busy` for the pool's own accounting, and
  `ffghr_clear_busy` is called from exactly one place, slot.sh's teardown trap (`slot.sh:83`). So
  the marker exists for the whole life of a job and the work clock needs no new state.
- **The deadline format exists.** `pool-task.sh:61-66` writes `staged_at` and `ttl_secs` into
  `out/staged`, and `ffstatus.sh:319-327` already parses them and subtracts. Phase B moves that
  code rather than writing it.
- **The stop path is identical in both lanes.** `docker stop` with a grace, never `docker kill`,
  because PID 1 has a trap that returns a Unity seat: `ffbox:1146-1152` (floor of 120s) and
  `slot.sh:492` (`-t 90`).
- **The agent lane already measures work from markers**, not from launch: `ffbox:1116-1141` picks
  the phase by the newest of `.agent-started` and `.verify-started` and judges each against its own
  ceiling. This design does not touch that loop; it copies its idea into the CI lane.
- **`out/owner` is written, tested and reasoned about** (`pool-task.sh:100-125`, `ffwatch.pool_warm`
  at `ffwatch.py:3960`). Phase D changes how often it is exercised, not what it means.
- **`reap.sh` already sweeps markers for containers that are gone** (`reap.sh:104-115`), which is
  the loop the new idle file has to join.
- **The web page needs nothing.** `ffweb.py:2147` renders `ttl_secs` through `fmt_ttl` for every
  container row already, and prints `—` for null. Fill the field in `ffstatus` and the page follows.
- **`ffghr_reload_limits` re-reads only `slots` and `idle_pool`** (`runners/lib/config.sh:720-728`),
  so a new `idle_minutes` is naturally fixed at mint rather than re-read under a waiting slot. That
  matches the agent lane's rule and is not something to work around.
- **`slot.sh` already sources `../lib-workloads.sh`** (`slot.sh:46-47`), with a warning and a
  degraded path when it is missing. Phase B needs no new plumbing on the CI side at all.
- **A spare stopped by the host already runs its licence trap.** `unity-license.sh:115` arms
  `trap return_license EXIT INT TERM`, `pool-task.sh` sources it as pid 1, and the foreground child
  during the idle wait is `sleep 1`, so a deferred bash trap runs within a second of the TERM.
  **What the trap then does depends on the path.** On the `.ulf` path it returns immediately —
  `FFBOX_LICENCE_MODE=offline` is checked before the owner test, because that licence took no
  concurrent seat and `-returnlicense` would want the credentials the .ulf exists to delete. On the
  activation fallback it runs a real return, an editor launch, and the stop has to allow 120
  seconds for it: D1a and A6 are that number. Without both halves Phase D would be a regression on
  the fallback path rather than a refactor.
- **Nothing reads `at=` out of the busy marker except the code that writes it.** The only other
  `at=` in the tree is the cache claim at `runners/lib/config.sh:486`, a different file with a
  different reader. So B3's key rename breaks no consumer.
- **`watchdog_minutes` has a second consumer**, and it is not the watchdog:
  `ffghr_cache_should_archive` (`runners/lib/config.sh:471-475`) ages out a cache claim with it.
  Re-basing the watchdog on the job leaves that reader correct, because a claim is made by a job.
  Checked so nobody re-derives it; no task follows from it.

## Design gaps closed while writing this

Five places where the design's prose leaves an implementation choice open, settled here.

1. **Host-side expiry of an agent spare must claim `out/owner` first, and the container's failsafe
   must not be gated on that file.** The design says the host becomes the enforcer of record and
   the container keeps a failsafe, which leaves both able to act. Decision: **the keeper does
   exactly what a dispatch does** — win the O_EXCL create, then stop; a keeper that cannot create
   `owner` has lost to a container already retiring and does nothing. AND the container's failsafe
   becomes absolute: at `ttl_secs + 900` it exits whether or not `owner` exists, unless
   `in/dispatch` has arrived. Without the second half the first half is a trap — `pool-task.sh`
   pushes its deadline 900 seconds every time it finds `owner` taken (`pool-task.sh:113-126`) and
   re-attempts a create that can never succeed, so a keeper that claims and then dies strands a
   container holding 22 GiB and a Unity seat with its own failsafe disarmed. Today that is
   unreachable in practice because only a dispatch creates `owner` from the host side and the
   dispatch lands a second later; D1 is what makes it reachable (design section 6). Note that the
   loop's own comment at `pool-task.sh:119-122` already claims this behaviour — "so a host that
   claimed and then died does not leave a container waiting for ever" — so D3 implements a stated
   intent rather than changing one.
2. **A spare being retired shows as `claimed` in `ffstatus`**, because that arm tests only for
   `out/owner`. Decision: **add a `retiring` state**, distinguished by the container being stopped
   or the file carrying a `retire` marker. A row that says `claimed` while nothing is claiming it
   is how an operator learns not to trust the column.
3. **The new CI idle file needs sweeping.** `reap.sh` globs `*.busy` only. Decision: **one loop
   over both suffixes**, same rule, same message. A per-container file that nothing deletes is a
   directory that grows for the life of the box.
4. **`idle_minutes` is fixed at mint, not re-read.** The deadline goes into the file at mint and the
   file is the deadline (design section 3), so a change to the config applies to containers created
   afterwards. Same rule `FFBOX_IDLE_TTL_SECS` already documents at `pool-task.sh:41`.
5. **Phase A duplicates three lines of parsing that Phase B removes.** The bug fix should land
   alone and early, so it reads `at=` out of the busy marker with its own `sed` and `date -d`.
   B replaces that with `ffbox_clock_left`. This is deliberate and is noted at both ends.

---

## Phase A — the two live bugs (each stands alone)

A1 to A5 are the whole of the bug in design section 4. A6 and A7 are a second, unrelated one found
while writing it. Neither set needs the helper, the idle clock, or either README, and neither needs
the other.

**A1 (S)** Reset `DEADLINE` when the job starts. At `slot.sh:475`, where `BUSY` flips, recompute
from the busy marker rather than from the clock:

    job deadline = at(state/<container>.busy) + WATCHDOG_MINUTES * 60

Derived from the marker rather than from the moment of the flip, so a supervisor that restarts
mid-job lands on the same deadline the previous one had.

**The fallback when the marker cannot be read is the CONTAINER'S START TIME plus
`WATCHDOG_MINUTES`, not `now` and not "no deadline".** That is today's rule exactly, it is always
bounded, and it is the safe direction for a work clock: an unbounded one leaves a wedged container
holding a slot, a workspace and a Unity seat for ever (design section 12). `now` would be
survivable but drifts on every supervisor restart. The marker write is already non-fatal
(`slot.sh:480-482`), so this path is reachable.

**A2 (S)** Keep an idle bound in the same loop, so a container that never takes a job still goes at
`WATCHDOG_MINUTES`, which is today's behaviour and stays it until Phase C separates the number.
After A1 the loop has two deadlines and picks by `BUSY`.

**A3 (S)** Say which clock fired. `slot.sh:486` and `:547` currently print one message for both
cases; a wedged job and a recycled idle runner want different reactions from whoever reads the
journal. Two messages, and the kind recorded on the teardown path the way `ffbox` writes
`warmup`/`agent`/`verify` into `ffbox-timeout` (`ffbox:1153`).

**A4 (S)** Correct the comment at `slot.sh:428`. It has described the intended behaviour all along
and is now describing the code as well; it should say what the deadline is measured FROM, because
that is the part that was wrong and the part a future reader will assume.

**A5 (S)** The same correction in `design/ffgithubrunners_design.txt:81-83`, which states the same
invariant about the same watchdog.

**A6 (S)** `pool_drop` stops a staged spare with `kill_grace_secs`, default 10
(`ffwatch.py:4156`). Where a container settles its licence by ACTIVATION, the trap that gives the
seat back is an editor launch of tens of seconds — which is exactly why `ffbox:1146-1150` floors
its own stop at 120 whatever `kill_grace_secs` says. Apply the same floor here. `kill_grace_secs`
is about an agent ignoring SIGTERM and is the wrong number for a licence round trip.

**Insurance, not a leak in progress.** With a `.ulf` staged — this box since 2026-09-01 — there is
no activation to interrupt and ten seconds costs nothing. The floor matters when the `.ulf` lapses
or is bound to the wrong machine id and `try_unity_license` falls through to `activate_unity`. Say
that in the commit message rather than claiming a live leak; design section 6 has the full split.

**A7 (S)** The same floor in `update_ffbox.sh:432`, which stops idle staged containers with a
hardcoded 10 on every update pass that has something to merge. On this box that is potentially
every five minutes, against a container holding a seat.

On the activation path neither A6 nor A7 loses a seat permanently: machine ids are per slot, so the
next container on that slot reuses the entitlement. What they cost between times is a concurrent
activation finding no free entitlement, which is the failure mode `entrypoint-ci.sh` and the
runners README both describe at length. Worth landing on its own merits, and worth landing BEFORE
Phase D, which would otherwise turn a stop that is too short on drains into one that is too short
on every retirement.

## Phase B — the shared clock helper

**B1 (S)** Four functions in `lib-workloads.sh`, POSIX shell, on the two-key file:

    ffbox_clock_write PATH SECS      staged_at=<now, date -Is> and ttl_secs=<secs>
    ffbox_clock_start PATH           the start as epoch seconds, empty if unreadable
    ffbox_clock_left  PATH           seconds remaining, negative when expired
    ffbox_clock_expired PATH         exit 0 when it has passed

Empty means "no deadline", never "expired": every caller has to treat a missing or malformed file
as a reason not to act (design section 12).

**B2 (S)** `pool-task.sh:61-66` writes through `ffbox_clock_write`. The other three keys in that
file (`commit`, `entry`, `ref`) stay where they are; the helper owns two keys, not the file.

**B3 (S)** `slot.sh` sources the helper and A1's inline parse becomes `ffbox_clock_left` against the
busy marker. The marker's key is `at=`, not `staged_at=`, so either the helper accepts both or the
marker gains the second key; prefer **one key name everywhere** and have `ffghr_mark_busy` write
`staged_at=` with `ttl_secs=` alongside it, since it is the only writer and `reap.sh` and
`ffstatus` read it by field rather than by shape. The deploy window is covered by A1's fallback: a
marker written by the old supervisor has no `ttl_secs`, the helper returns empty, and the job is
bounded by the launch-based deadline it would have had anyway.

**B4 (S)** `ffstatus.sh:319-327` calls the helper instead of carrying its own `sed` and `date -d`.

**B5 (S)** ffwatch reaches the helper through `ffbox`, the way it already runs every other shell
side of this system (`ffbox_cmd()`). No second implementation of the format in Python.

## Phase C — the CI idle clock

**C1 (S)** `githubrunner.idle_minutes`, default 120, via `_ffghr_set` beside `watchdog_minutes`
(`runners/lib/config.sh:137`). Same section of `~/.config/ffbox/config.json` as the rest of that
lane. Coerced, not just defaulted, the way both pools already coerce `pool.idle`: 0 means "no idle
deadline" rather than "expire immediately", a negative value is 0, and a value small enough to
churn JIT registrations against GitHub's API is refused at read time rather than honoured.

**C2 (S)** `slot.sh` writes `state/<container>.idle` at mint with `ffbox_clock_write`, and the idle
arm of A2's two-deadline loop reads it rather than reusing `WATCHDOG_MINUTES`.

**C3 (S)** The pre-stop re-check from design section 10: immediately before an idle stop, run
`ffghr_container_busy` again and abandon the stop if it now says busy. Five seconds of poll interval
is the window.

Land it in Phase C even though nothing needs it yet. While `idle_minutes` equals
`watchdog_minutes` a missed flip is exactly today's behaviour and costs nothing extra; the moment
somebody lowers `idle_minutes`, which open item (c) proposes, it starts killing jobs early. This
task is the gate on that open item rather than a fix for anything visible today, and the commit
message should say so or somebody will remove it as dead weight.

**C4 (S)** `reap.sh` sweeps `*.idle` alongside `*.busy`, one loop over both.

**C5 (S)** `ffgithubrunners status` reports the idle clock next to the pool counts, since that is
where an operator already looks.

## Phase D — the agent idle clock moves host-side

**D1 (M)** `pool_reap` (`ffwatch.py:4033`) gains an expiry test: for each staged container whose
`out/staged` clock has passed and which has no `out/owner`, claim `owner` (gap 1), then retire it.
The claim is the same O_EXCL create `pool_claim_for` does, so a container already retiring wins and
the keeper does nothing.

**D1a (S)** The keeper's stop applies ffbox's 120-second floor, not `kill_grace_secs`. Same
reasoning and same number as A6, and if A6 has landed this is already the shape of the call. Get
this wrong and Phase D leaks a Unity seat on every retirement instead of on none, which would make
the phase a straight regression against the self-retirement it replaces.

**D2 (M)** The stop does not run on the daemon's loop. Commit c693d67 is the precedent: a blocking
call on that loop cost three minutes a pass and Max stopped answering Discord. Either background it
on the path staging already uses, or bound it the way the speculative caller bounds its lock
(`ffbox_workload_lock_acquire 30`). Nobody waits on a retirement, so "not this pass" is always fine.

**D3 (M)** `pool-task.sh`'s own deadline becomes the failsafe: `TTL + 900`, matching the 900-second
push it already applies when the host claims at the deadline (`pool-task.sh:124`). Its log line
should say it is a failsafe, because if it ever fires the interesting fact is that the keeper did
not.

**It exits at the second expiry whether or not `owner` exists**, which is gap 1's second half and
the reason this is M rather than S. The 900-second push may be taken ONCE: a claim that has not
become a dispatch within fifteen minutes is a failed host, not a dispatch in progress, and the
container stops waiting for it. Only `in/dispatch` actually arriving cancels the failsafe.

**D4 (S)** `ffbox --idle-ttl` keeps passing the configured TTL; the container adds the margin
itself. The host must not pass a number the container then treats differently from the one in the
file it wrote.

**D5 (S)** The `retiring` state from gap 2, so a spare the keeper is stopping does not read as
`claimed`.

## Phase E — ffstatus and the page

**E1 (S)** The `ci)` arm at `ffstatus.sh:303` sets `ttl` from the busy clock when the row is busy
and the idle clock when it is waiting. `render_json` and `ffweb` need no change at all.

**E2 (S)** `orphan` in place of a countdown for a CI container whose supervisor is gone, using
`supervisor_alive` against the `ffghr.supervisor.pid` label, the test `reap.sh:62-73` already
makes. A TTL that
nothing is enforcing must not be displayed as one.

**E3 (S)** The README paragraph at `README.md:1407-1416` says "each spare's slot, branch and
remaining TTL". After E1 it is both lanes, and the sentence should say which clock a CI row is
showing.

## Phase F — documentation

**F1 (S)** `ffbox/README.md`: the two-clock vocabulary in both lanes' sections, and the correction
to the idle-agents paragraph at `:1450`, which says the container times itself out and the host
compares nothing. After Phase D the host compares, and the container is the backstop.

**F2 (S)** `ffbox/runners/README.md`: what `watchdog_minutes` now measures from, and `idle_minutes`
beside it in the pool section.

**F3 (S)** `CREDENTIALS.md` and the security model need nothing. No credential, mount or network
changes here; worth one line in the commit message so nobody goes looking.

## Phase G — tests

All offline. `runners/test_pool.sh` stubs `docker` on PATH; `test_ffwatch.py` stubs it the same way;
neither needs the daemon, a cache entry or 22 GiB of RAM.

**G1 (S)** The clock helper, table-driven: write then read back, remaining seconds against a fixed
`now`, negative when expired, and empty for a missing, truncated or garbage file.

**G2 (S)** The CI work clock: a marker written 118 minutes ago and a job that starts now gets the
full `watchdog_minutes`, not two minutes. This is the regression test for the whole design and it
should name the bug in its message.

**G3 (S)** A supervisor restart mid-job recovers the same deadline from the marker rather than a
fresh one.

**G4 (S)** The idle clock fires on a container that never goes busy, and does NOT fire on one that
did, including the case where the flip happened after the idle deadline had passed.

**G5 (S)** C3's pre-stop re-check: a container that becomes busy between the deadline test and the
stop is not stopped.

**G6 (M)** The keeper's expiry, in `test_ffwatch.py`: an expired spare is retired, a spare with
`out/owner` is never touched, and a keeper that loses the `owner` race does nothing.

**G7 (S)** `test_ffweb.py`'s `FFSTATUS_DOC` fixture currently carries `"ttl_secs": None` on its CI
row (`test_ffweb.py:498-499`). Give it a number and assert the page renders it, so the fixture stops
encoding the bug as expected output.

**G8 (M)** The absolute failsafe, and it is the most important test in this phase because the case
it covers is the worst outcome in the design. Drive `pool-task.sh` against a scratch spool
directory: create `out/owner` from outside and never write `in/dispatch`, and assert the task takes
one 900-second push and then EXITS, rather than pushing for ever. Run it with the margin shrunk
through the environment so the test does not take half an hour.

**G9 (S)** The work-clock fallback: a busy marker that is missing, truncated, or written in the old
`at=`-only format yields the container's launch-based deadline, and never "no deadline". Assert the
computed deadline is bounded, not that it is any particular value.

**G10 (S)** Every stop of a seat-holding container carries at least 120 seconds, asserted against
the argv `pool_drop` and the keeper build rather than against a running container. Cheap, and it is
the only guard on a leak that is invisible until somebody counts Unity seats.

---

## Order, and where to stop

**Phase A first, on its own.** Two fixes rather than a feature, needing nothing else in this
document. Until A1-A5 land, about a quarter of CI jobs start with less than thirty minutes of
runway against a workflow ceiling of 90; until A6-A7 land, every drain that destroys a staged spare
gives its Unity seat ten seconds to come back and then SIGKILLs it. G2 and G10 land with them.

A6 and A7 in particular should not wait for the rest, because Phase D changes how often that path
runs: today it fires on a drain, and after D it fires on every retirement.

**Then B**, which is the substrate everything else reads, and which pays for itself immediately by
deleting A1's inline parse and `ffstatus`'s duplicate one.

**Then C and E together.** C makes the CI idle clock a real number and E puts it on the screen; each
is dull without the other, and E is how the change gets watched on the real box.

**D last, and it is the only part with real reasoning in it.** Everything before it is threading a
value through paths that already carry others like it. D moves an enforcement decision between two
processes, and the three things that make it safe — the `owner` claim, the absolute failsafe behind
it, and keeping the stop off the daemon's loop — are each easy to get subtly wrong. G8 is the test
that says whether the second one is right.

**The useful stopping point is after C and E**, and it is a real stopping point rather than a
pause. At that point the bug is fixed, both lanes describe their deadlines in one vocabulary, and
the box can show you every clock it is running. D is a refactor of a lane that works: the race it
removes has produced no failure anybody has recorded, and it trades that for a new host-side stop
path and a lane whose seats come back on time only while ffwatch is healthy. Design section 13 is
the full ledger. If part of this is going to be left unbuilt, D is the part.

## Deploy

Config first, then code, then the restart, in the order `update_ffbox.sh` already imposes: it merges
and re-runs both setups, so `idle_minutes` appearing in `config.json` before the code that reads it
is a no-op, and code that reads a key which is not there takes its default.

Nothing needs draining for correctness. A CI container minted before the deploy has no `.idle` file;
the loop treats a missing clock as "no deadline" (B1) and that container keeps the single-deadline
behaviour it started with until its job or its watchdog ends it, which is at most `watchdog_minutes`
away. A spare staged before Phase D has an `out/staged` clock in the format the keeper reads, so it
is expired correctly on the first pass after the restart.

The one thing to watch on the first day is C3's re-check firing. If the journal shows idle stops
being abandoned regularly, `Runner.Worker` detection is racing more than the five-second poll
suggests, and open item (b) in the design — a durable job-start signal out of the runner's own log —
stops being optional.
