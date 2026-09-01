# ffbox idle agents: implementation tasks

Derived from `design/ffbox_idle_agents_design.txt` (2026-08-31) after reading the current launch
path: `ffwatch.launch()`, `ffbox`, `entrypoint.sh`, `restore-workspace.sh`, `discord-task.sh`, and
`runners/lib/config.sh` for the admission arithmetic this copies.

Effort: **S** under an hour, **M** an afternoon, **L** a day or more, **?** unknown until something
is measured.

## Status, 2026-09-01

G, H, A, B, C, D and E are **implemented**; F is implemented except F4 and F6, which want a
stub-container fixture that does not exist yet. B5, the gate the rest was conditional on, came
back at **1.2 seconds** from dispatch to the agent starting, against a 40-second cold launch, with
the resync inside the warm container at 0s.

Two things are NOT verified on live traffic yet, and both need the deploy: ffwatch claiming a
staged container for a real Discord turn, and the transcript sweep on a run that crashes. The
pieces either side of each are covered offline, and `ffbox --stage-pool` / `--dispatch` was driven
end to end by hand with a real agent answer.

G1 is worth knowing about separately. 0404c0f fixed the missing harvest independently while this
was being written, but left the agent in the foreground, so its trap still could not fire on the
path its own message describes — an agent stopped at its ceiling. That half is here.

## What already exists

Worth knowing before estimating.

- **`restore-workspace.sh` already is the staging step.** It takes the cache entry, the mirror and a
  target ref from the environment and leaves a workspace at a commit. Staging is calling it with no
  branch and no job; nothing in it needs to change.
- **The admission arithmetic is written and tested**, in `runners/lib/config.sh`
  (`ffghr_pool_admit`, `ffghr_pool_counts`) with offline coverage in `runners/test_pool.sh`. That is
  shell and the keeper is Python, so it is a port of about thirty lines, but the reasoning does not
  need re-deriving. What does NOT port is the slot numbering: there are no slots here (design
  section 3).
- **`docker rename` on a running container works on this daemon.** Verified 2026-08-31 against the
  rootless daemon at `/run/ffbox-container/docker.sock`: renamed a running container, and both
  `docker ps --filter name=` and `docker exec` followed the new name immediately. This is what lets
  a dispatched container take its `ffbox-<run-id>` name, so ffbox's clock loop and ffwatch's
  `container_live()` need no change at all.
- **`ffbox --mount HOST:CONTAINER[:ro]` is already repeatable and validated**, so the three pool
  mounts need no new plumbing in the argument parser.
- **The clock loop already watches markers, not the container's age**, so starting it at dispatch is
  a change to one variable rather than to the loop.
- **`ConversationLock`** is the precedent for why the claim has to be inter-process: `schedule()`
  runs in the daemon, but `ffwatch submit --wait` drives a pass itself when no daemon holds the
  lock.
- **The agent lane takes no Unity licence up front** since 2026-08-31, so nothing about staging has
  to think about seats.
- **The request ceiling exists and is wired end to end**: `agent_secs` -> `ffbox --agent-timeout`
  -> the clock loop -> `docker stop` -> exit 124 -> `ffbox-timeout` -> `terminal = "timed_out"` ->
  `compose_head`. Phase G changes a default and repairs three things behind it; it adds no new
  clock and no new setting.

## Design gaps closed while writing this

Six places where the design's prose and the code disagree, settled here.

1. **`run.stream_path` is written at INSERT**, before the container starts, and for a pooled run it
   points into the pool directory. Decision: **write the pool path at insert, rewrite at finish**,
   because the live indexer is the thing that must not guess and the rewrite happens in one place.
2. **`transcript_path()` computes a path from `conv_id` and `session_id`** and has no way to say
   "this run's transcript is in a pool directory". Decision: add `run.transcript_dir`, NULL for a
   cold run (meaning the conversation's claude directory, unchanged).
3. **`container_name` and `recover()` need nothing**, given the rename. The run row records
   `ffbox-<run-id>` exactly as it does today and `container_live()` keeps its exact-match rule.
4. **`drain()` counts run rows**, and a staged container is not one, so `drain(wait=True)` would
   report "quiet" with containers up. Deliberate. The update path destroys them explicitly rather
   than relying on the count.
5. **A SIGTERM to PID 1 does not reach the agent.** Verified 2026-08-31: bash defers a trap handler
   until the foreground child finishes, so with a 20-second child and a TERM at 2 seconds the
   handler ran at t=20; backgrounded and `wait`ed, it ran at t=2 and killed the child. `docker stop`
   signals PID 1 only, so today the agent clock stops nothing and SIGKILL takes the container 120
   seconds later. Phase G1.
6. **`discord-task.sh` has no finish trap**, only `return_license` from `unity-license.sh`. So a
   timed-out Discord or web turn harvests nothing: no bundle, no branch, no PR. `run-as-user.sh`
   has `_ffbox_finish` and is the model. Phase G2.

---

## Phase G — the request ceiling (independent of the pool)

Nothing here needs a staged container, and all of it is worth having whether or not the pool ships.

**G1 (S)** Run the agent with `&` and `wait` in both `discord-task.sh` and `run-as-user.sh`, and
have the trap kill the child before it does anything else. Without this the ceiling is advisory and
the container dies by SIGKILL 120 seconds late.

**G2 (S)** A finish trap in `discord-task.sh`: harvest, then return the licence, in that order and
for the reason `run-as-user.sh` states. A timed-out run's committed work is published like any
other run's; verification is skipped, so the PR gate withholds the pull request on its own.

**G3 (S)** Write a `result.json` stub from the trap, so a killed run leaves the shape the host reads
rather than nothing.

**G4 (S)** `agent_secs: 1800` in `ffwatch.DEFAULTS` and in `~/.config/ffbox/config.json` on this
box, which sets 900 explicitly and would otherwise ignore the new default.

**G5 (S)** The three replies: a `PUBLIC_TIMED_OUT` string that does not claim something broke and
does not invite the same question again; the configured ceiling on the private state line; and
`result_text()` falling back to a fixed line for a `timed_out` run with no result, pointing at the
transcript that is already indexed.

**G6 (S)** `record_verification` gains an agent-clock evidence string beside the verify-clock one it
already has. A timed-out run that changed files currently gets "the container produced no
verification report", which compose_head prints as ⚠️ NOT VERIFIED and reads as a suite that failed
rather than one that never ran.

## Phase H — base Discord turns on master (independent of everything else)

Design section 6a. Two lines and a paragraph, and it is worth landing whether or not the pool ships,
because today the bot answers questions about the released game out of unreleased source.

**H1 (S)** `base_ref: "master"` in `ffwatch.DEFAULTS` and in `~/.config/ffbox/config.json`, with the
comment section 6a is the long form of: this is what the agent READS, and the agent still picks
where its work goes by picking what it branches from.

**H2 (S)** `github["base"]: "master"` to match. It is `pr_base`'s fallback when the commit graph
cannot answer; it fails closed rather than wrong as it stands, but leaving it at develop makes the
fallback the less likely answer.

**H3 (S)** Check the container preamble reads correctly from master. `publish_bases` is rendered
into it verbatim and its descriptions are written from develop's point of view ("the integration
branch, and the default"); "the default" is now only true of where work is PROPOSED, not of where
the workspace starts, and the agent should not have to work that out.

**H4 (S)** One line in the ffbox README's Discord section saying which branch a turn reads and why,
because the next person to wonder will look there rather than in a design document.

## Phase A — the pool directory and the knobs

**A1 (S)** `~/ffbox-state/pool/<id>/{in,out,claude}` created at stage and deleted when the container
is gone, owned the way `share_with_container()` already sets up a claude directory.

**A2 (S)** Config: `idle_agents`, `idle_agent_ttl_secs`, `pool_ref` in `ffwatch.DEFAULTS`, with
`idle_agents` and `pool_ref` re-read on the poll rather than at start. Mirror
`ffghr_reload_limits`'s
rule that a key deleted from the file returns to its default.

**A3 (S)** The `O_CREAT|O_EXCL` claim on `pool/<id>/out/owner`, and the ordering it depends on: the
host creates `owner` before anything lands in `in/`, and `dispatch` is written last. One file does
both jobs, asking and taking, which is what makes the container's retirement and the host's dispatch
mutually exclusive. Test it with two threads before there is anything to launch.

## Phase B — a container that stages and waits

**B1 (M)** `ffbox/pool-task.sh`: stage via `restore-workspace.sh`, write `staged` with the commit
and
the entry it used, then poll `/ffbox/in` for `dispatch` with a deadline of `FFBOX_IDLE_TTL_SECS`.
Retire on the deadline only by winning `owner` (design section 7), never unconditionally. It is
PID 1, so
it keeps the signal discipline `entrypoint.sh` relies on and must exit cleanly on SIGTERM while idle
without harvesting anything or touching the licence.

**B2 (M)** `ffbox --stage-pool`: the three mounts, the `ffbox.pool` label, the `ffbox-pool-<id>`
name, the TTL in the environment, no job file, no branch, no clocks. Returns as soon as the
container is up; the keeper reads `staged` to know when it is warm.

**B3 (S)** `ffbox --dispatch <id>`: write job.json, prompt and attachments into `in/`, write
`dispatch` last, `docker rename` to `ffbox-<run-id>`, then run the existing clock loop with
`STARTED_AT` taken at that moment, then move `out/` into the run directory. Everything after the
container exits (`ffbox_validate_harvest` and the rest) is unchanged and reads the moved directory.

**B4 (S)** `entrypoint.sh` hands to `pool-task.sh` when `FFBOX_POOL` is set, keeping the uid dance
and the restore guard exactly as they are.

**B5 (?)** Measure the real dispatch cost: mirror fetch, reset, and the agent's first token, against
the 40s cold baseline in the design. This is the number that decides whether the rest is worth
landing.

## Phase C — the keeper

**C1 (M)** A thread on ffwatch's poll: count by label, apply the admission rule, stage one at a time
(never two at once, or a burst of staging competes for memory with the runs it exists to serve).

**C2 (S)** The MemAvailable check before staging, with headroom for `max_concurrent_runs` cold
launches. Note it reads `/proc/meminfo`, NOT `df /dev/shm` — design section 9 records why the
obvious reading is wrong by 23 GiB.

**C3 (M)** Eviction: a cold launch short of memory destroys a staged container and proceeds. This is
the rule that makes the pool safe to turn on, and it needs a test that does not require 22 GiB.

**C4 (S)** Adoption at start: staged containers from a previous ffwatch are counted, and ones staged
before the current checkout are destroyed. Deleting a pool directory whose container is gone belongs
here too.

## Phase D — dispatch

**D1 (M)** `launch()` asks the keeper for a staged container matching the turn's ref branch; on a
hit
it adds `--dispatch <id>`, on a miss it does exactly what it does today.

**D2 (M)** Transcript copy in at dispatch and move out at finish, plus `run.transcript_dir` and the
schema v8 `ALTER TABLE`. `index_live_runs` reads the column.

**D3 (S)** `recover()` sweeps any pool directory holding a transcript before it decides anything,
and destroys a container that was mid-dispatch rather than adopting it.

**D4 (S)** The out-directory move, and `run.stream_path` rewritten at finish.

## Phase E — the rest of the machine

**E1 (S)** `update_ffbox.sh` destroys staged containers as part of its drain. Without this a merge
lands under a container that has `pool-task.sh` bind-mounted from the checkout, and the four-hour
timer does not help.

**E2 (S)** `ffwatch pool` / `pool stage` / `pool drop`, and one line on `ffwatch status`.

**E3 (S)** README: the pool, the two numbers, the TTL, the RAM, and the sentence that
`idle_agents: 0` is today's behaviour exactly.

## Phase F — tests

**F1 (S)** Admission arithmetic, table-driven, ported from `runners/test_pool.sh`.

**F2 (S)** The claim under contention: two dispatchers, one staged container, exactly one winner and
the other launching cold.

**F3 (S)** The claim/timeout race, both directions: a container reaching its deadline after the host
won `owner` keeps waiting and serves the prompt; a host that loses `owner` to a retiring container
treats it as a miss and launches cold.

**F4 (M)** The transcript sweep on a crash, the one place the pool can lose something a cold run
would not. Kill the stub container mid-dispatch and assert the session file reaches the conversation
directory.

**F5 (S)** Cold fallback: `idle_agents: 0`, an empty pool, a ref on an unstaged branch, and
`--direct` all take the existing path and produce a byte-identical `docker run` argument list.

**F6 (S)** Eviction under simulated pressure, with the memory probe stubbed.

**F7 (S)** The three timeout replies, one per front door, from a `timed_out` run row with no
result.json: public gets the timeout text and not `PUBLIC_NO_ANSWER`, private names the ceiling, and
`result_text()` returns something rather than "".

**F8 (S)** The trap reaching the agent, offline: a stub task with a backgrounded sleep, a TERM, and
an assertion that the handler ran inside a second rather than after the child. The bash behaviour in
gap 5 is the thing being regression-tested, and it is not obvious enough to leave uncovered.

All of these stub `docker` the way `test_ffwatch.py` already does. Nothing in this phase needs the
daemon, a cache entry or 22 GiB of RAM.

---

## Order, and where to stop

Phases G and H first, both on their own and in either order. Neither needs the pool, and both are
fixing something rather than adding something: today a request that runs out of time is not stopped,
loses its work and tells a player that something broke, and every Discord answer is read out of a
branch nobody is running.

Then B5 is the gate for the rest. Stage a container by hand, dispatch one turn into it, and measure.
If dispatch does not land near a second, the design's premise is wrong and phases C through F should
not be written.

After that the useful stopping point is D1: a keeper, one staged container, cold fallback everywhere
else. E and F are what make it safe to leave running unattended, and E1 in particular is not
optional on a box whose checkout moves every five minutes.
