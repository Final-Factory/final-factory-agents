---
name: ffu-build-test
description: Build, test and land a change in Final Factory Universe (FFU), the Rust engine in the private Final-Factory/ffu repo - the toolchain on FF Factory machines, the six checks CI runs (fmt, sim rules, clippy, tests, hashcheck, crosscheck), the snapshot and hash rules a sim change must keep, reading CI on ffu's own runners with gh, and merging your own PR. Use before any work in an ffu checkout; it replaces editor-ops there, since FFU has no Unity editor.
---

# Building and testing FFU

FFU is all Rust (Ben, w2757): no Unity editor, no MCP bridge to pin, nothing to refresh. The checks below are the
whole verification. The repo's own `CLAUDE.md` is binding and longer; this skill is the path through it.

## 1. Get a checkout and a toolchain

- Clone into your `$TMPDIR`: `git clone https://github.com/Final-Factory/ffu.git "$TMPDIR/ffu"`. Branch from `main`
  (ffu's trunk is `main`, not `master`). Commit as `Final Factory <481770+bryding@users.noreply.github.com>`.
- `rust-toolchain.toml` pins Rust 1.94.0 with clippy and rustfmt; `cargo` picks it up by itself.
- When `cargo` is not on PATH, look for the machine's shared toolchain before installing one. On lothdesktop it is
  under `V:/ffw/tools` (measured, w2895):

  ```sh
  export RUSTUP_HOME=V:/ffw/tools/rustup CARGO_HOME=V:/ffw/tools/cargo
  export PATH=/v/ffw/tools/cargo/bin:/v/ffw/tools/cmake-4.4.5-windows-x86_64/bin:$PATH
  export CARGO_TARGET_DIR="$TMPDIR/ffu-target"   # builds stay in your temp folder
  ```

  `ffu-client` (the `ffu` binary) builds SDL3 from source and needs cmake on PATH: without it the build stops with
  "build script failed". A cold release build of `ffu-client` took 1 min 40 s there, `ffu-headless` 31 s (measured).
  On BEAST `cargo` is on PATH (`~/.cargo/bin`) and cmake is Visual Studio's:
  `export PATH="/c/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin:$PATH"`
  (measured, w2895 M2.17b).
  On biscuit (Linux) a worker shell has neither `cargo` nor `python` on PATH: `export PATH=$HOME/.cargo/bin:$PATH`
  and call `python3` (the bench queue script too). A backgrounded `nohup cargo build` or
  `nohup python ...` then dies with exit 127 and leaves an empty log: w3432 lost 10 min believing a bench ticket was
  queued. Check the first lines of a background job's log within seconds of starting it.
- A wait loop `until ! pgrep -f "<pattern>"` matches its own shell's command line and never ends (w3432); bracket a
  letter (`pgrep -f "[e]cho-biscuit"`) or wait on a pid file.
- Put those exports in `$TMPDIR/rust.sh` and source it in every shell call: shell state does not persist.
- **Keep one target per worker; never share a `CARGO_TARGET_DIR` across parallel workers** (w3396). Two builds on one
  target wait on cargo's build-directory lock ("Blocking waiting for file lock"): one rebuild alone took 44 s, two at
  once 48 s and 71 s (measured, BEAST). A shared target is also never idle, so FF Factory's clean-up can never prune it.
- **Give a second checkout its own target too** (w3480): a `main` worktree for the RED run and your branch must not
  share one `CARGO_TARGET_DIR`. After building main's tests there, `cargo test` on the branch ran main's stale test
  binaries and reported main's failures: the new `ship_flies_over_buildings` failed until its sources were touched and
  rebuilt, then passed 3/3 (measured, BEAST). Use `CARGO_TARGET_DIR="$TMPDIR/ffu-target-main"` for the RED checkout.
- **A big target is usually stale artifacts, not debug info** (w3396). Since ffu #381 (`[profile.dev] debug =
  "line-tables-only"`, dependencies `debug = 0`) a clean `cargo test --workspace --all-features --no-run` target is
  5.5 GB, down from 14.1 GB (measured, BEAST). Cargo never deletes what an older build left: a worker that rebuilt all
  day held 23.6 GB, with 13.8 GB in `debug/deps` (34 hashed copies of `ffu_server`) and 5.9 GB in `debug/incremental`,
  while fresh targets were 3.3 to 3.6 GB (measured 2026-11-07). Count the copies with
  `ls target/debug/deps | sed -E 's/-[0-9a-f]{16}.*//' | sort | uniq -c | sort -rn | head`; when no cargo of yours
  runs, `rm -rf "$TMPDIR/ffu-target/debug/incremental"` is rebuildable and frees most of it.

## 2. The checks, in CI's order

```sh
cargo fmt --all --check
./tools/check_sim_rules.sh
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace --all-features
cargo run --release -p ffu-headless -- hashcheck --golden golden/hashcheck.txt
cargo run --release -p ffu-headless -- crosscheck --threads 1,4,16 --golden golden/crosscheck
```

- Run what your change touches locally (`cargo test -p <crate>`); CI runs all of them on Linux and clippy, tests and
  hashcheck on Windows and ARM macOS.
- `hashcheck` ends with `"golden_match":true`. A change that moves the hash on purpose updates
  `golden/hashcheck.txt` in the same PR and says why; re-pin a crosscheck trace with
  `ffu-headless crosscheck --golden golden/crosscheck --write-golden` only for a change meant to move it.
- **Before a push, run `cargo test --workspace --all-features --no-fail-fast`.** A plain workspace `cargo test` stops at
  the first crate that fails and never runs the rest. In w3459 (ffu #427), fixing the failures in `ffu-agent` revealed
  another in `ffu-ui`'s `names.rs`, which the first run had not reached.
- **`python3` on lothdesktop is the WindowsApps Store stub**, so `./tools/check_sim_rules.sh` stops with "Python was not
  found". Putting `/c/Python313` on PATH does not help, because that folder has no `python3.exe`. The fix is a folder
  (`$TMPDIR/pybin`) whose `python3` is a two-line script, `#!/bin/sh` then `exec /c/Python313/python "$@"`, put first
  on PATH. With it the script printed "sim rules ok" (w3459, measured).
- Build a player with `-p ffu-client`, never `--workspace`: `ffu-mcp` turns `agent-api` on and Cargo unifies features
  across one command's packages. `tools/check_compiled_out.sh` (CI) fails a player build that holds the agent API.
- A golden image test that fails after a change: before re-blessing, render with `FFU_FALLBACK_ADAPTER=1
  FFU_CAPTURE_DIR=<dir>` and group the pixels that differ from the golden into blobs. Re-bless (`FFU_BLESS=1`, on the
  adapter the golden was blessed on) only when every blob is a change you meant to make; any other blob means the code
  is wrong (w2895 M2.17b: two 15 px discs on the two crafters, nothing else, so the golden was out of date).
- A test that opens a GPU device holds its crate's one-device lock (`ffu-render`'s `tests::gpu`, `ffu-client`'s
  `packs::tests::gpu` / `one_gpu_at_a_time`; a new crate with GPU tests adds one). Several devices made at once crash
  Mesa's Vulkan loader: a SIGSEGV with no Rust panic, in 25 of 200 parallel runs of `ffu-client`'s tests on biscuit
  without the lock and 0 of 200 with it (measured, w2895 M2.17b, probe ffu #226).
- Fuzzing needs nightly and cargo-fuzz (`tools/fuzz.sh [seconds] [target ...]`); BEAST has neither. Run new targets on
  biscuit by dispatching the nightly job on your branch: `gh workflow run fuzz.yml -R Final-Factory/ffu --ref <branch>
  -f seconds=600 -f targets="a b"`. Each target's result is its `stat::number_of_executed_units` line in
  `gh run view <id> --log` (w2895 P0.14c, run 42208794602: four targets in about 45 minutes with the build). A new
  target adds a `[[bin]]` in `fuzz/Cargo.toml`, a name in each of `tools/fuzz.sh`'s target lists, and minutes to
  `fuzz.yml`'s `timeout-minutes` (10 per target plus the build).

## 3. The rules a sim change keeps

`crates/ffu-sim` holds no floats, unordered maps or sets, interior mutability, clock, files, threads, environment, GPU
or unsafe code, and no panics in the tick (use `get`, `checked_*`, `saturating_*`, `wrapping_*` and say why).
`tools/check_sim_rules.sh` greps comments too, so write a banned type's rule in words. Every change to a sector is an
`Op` through `Sector::submit` (adding one: `/ff-agents:ffu-add-op`). A snapshot layout change bumps
`SNAPSHOT_VERSION`, keeps the old decoder and adds a fixture in `crates/ffu-sim/tests/fixtures`; existing fixtures are
never rewritten (`tools/check_snapshot_compat.sh BASE_REF` holds it in CI). No thread count may change a hash.

- **Run a fixture writer by its exact name**: `FFU_WRITE_FIXTURE=1 cargo test -p ffu-sim --test golden_snapshot
  <writer> -- --ignored --exact`. A bare `--ignored` runs every writer and rewrites the old fixtures, which
  `check_snapshot_compat.sh` then refuses (w3489). A new `include_bytes!` fixture needs an empty placeholder file before
  its writer can compile.
- **A new FF1 build can move every item id** (w3489, ffu #436: FF1 1.0.0.41 added ids 9, 10, 11 and 15, so 1.0.0.30's
  12 to 220 moved up 4). After re-running the exporter, compare both exports' names before anything else.
  - A hardcoded id then breaks silently: write `ffu_sim::content::IRON_ORE`, never `110` or `ITEM_NAMES[32]`.
  - Every stored format bumps its version and remaps old ids as it reads them, before any restore check (snapshot, op
    log, world messages; `content::from_1_0_0_30`). A server WAL refuses an old segment instead, because it appends.
  - Oracle replays keep the recording's build ids. They map puts in through `layout::from_build` and fingerprints out
    through `layout::in_build`, with `replay::absent_items`; a belt fingerprint is rebuilt from `connector_groups()`.
  - Expect re-pins of the hashes that hold ids: `golden_snapshot.rs`, `golden_world.rs`, `layout_is_pinned`,
    `golden/hashcheck.txt`, and the factory and world crosscheck CSVs (`--write-golden`). Give each a reason line, and
    check that every other scenario still matches.

- **A snapshot section that is not empty for older saves breaks the old fixtures' length checks.** The golden tests
  assert that re-encoding an older fixture adds only empty sections. In w3459 (ffu #427, v12), the new power section
  holds the rebuilt power state of any powered sector, so those asserts failed. Compute the section's exact length
  rather than hard-coding a new number: `let mut w = ffu_sim::codec::Writer::new(); s.power().encode_state(&mut w);`
  gives its bytes. Assert those bytes, and the zeros after them, then cut the section out before comparing with the
  old file (`without_power` in `golden_snapshot.rs`, `power_sections` in `golden_world.rs`).
- **A new `Kind` or `Op` is matched outside `ffu-sim` too.** `cargo check --workspace --all-features --all-targets`
  finds the non-exhaustive matches:
  - `ffu-agent`'s `building_json`;
  - `ffu-headless`'s `op_name`, for a new `Op`;
  - `ffu-client`'s `packs.rs` `model_name` and `view.rs` colours;
  - `ffu-ui`'s inspector `kind_word`.

  Only the tests find the expected lists:
  - `ffu-agent`'s `schema_names_what_set_accepts`, which lists `Kind::ALL` names;
  - `ffu-agent`'s `ui_tree_returns_the_build_menu_as_data`;
  - `ffu-ui`'s gate test `every_building` and its kind count;
  - `names.rs`'s Japanese build-menu list.

  (w3459.)

## 4. Land it: PR, CI with gh, merge your own

- Push your branch, `gh pr create -R Final-Factory/ffu --base main --title ... --body-file ...`, with
  `Request: wNNN` (or `Part of: wNNN`) in the body.
- CI runs on ffu's own runners, one job at a time each: `ffu-linux` (biscuit), `ffu-windows` (BEAST), `ffu-macos`
  (the M3). A job waits while its machine is off; a queue of several minutes is normal.
- **A run whose only jobs left are `ffu-macos` ones, queued for over half an hour, means the M3 is off**: check
  `gh api repos/Final-Factory/ffu/actions/runners` (ffu-m3, ffu-m3-2 `offline`) and the portal journal (grep `m3`)
  before you wait on it. ffu's main has no branch protection. A PR that touches no `crates/ffu-sim` and no platform
  `cfg` merges on green Linux and Windows legs, and says so: "the macOS legs never ran" (w2895, 2026-11-05: M3 offline
  from 11:57Z, ffu #222 queued 5 h). Never add a runner on m5 (Ben's own Mac) without asking him.
  - While the M3 is off, a push to the same PR can make no run start. The earlier run, still queued on its `ffu-macos`
    legs, holds the `ci-<ref>` concurrency group, and the new run sits `pending` with no jobs. FF Factory then reports
    "no CI run exists". `gh run cancel` leaves the earlier run queued.
    `gh api -X POST repos/Final-Factory/ffu/actions/runs/<old id>/force-cancel` ends it, and the new run is queued
    within a minute (w3168, ffu #302, measured).
- **A PR that changes only `docs/` runs no CI**: `ci.yml` has `pull_request: paths-ignore: ['docs/**']` (ffu #297).
  A `ci:` wait on it ends after 10 min with "no CI run exists". Merge it straight away with `gh pr merge <n> --merge
  --match-head-commit <head>` (w3382: ffu #395, a PLAN row, sat 10 min in such a wait).
- **A Windows test job red with every test passed and `temp leak check: ... MSBuildTemp`** was the build, not a test:
  SDL3's `-sys` crates build through cmake and MSBuild when a runner rebuilds its target. The test jobs build with
  `cargo test ... --no-run` before `check_temp_leaks.sh` since ffu #249 (w2895); keep any new checked step that way.
- **A Windows test job red with `LNK1171: unable to load mspdbcore.dll (error code: 1455)`, then "required to be
  available in rlib format" errors, ran no test**: error 1455 is "the paging file is too small", so BEAST ran out
  of commit memory while linking (w3385, ffu #373, CI run 42394339327 on ffu-beast-3). That is the machine, not the
  code. Ben's rule (2026-11-07, 15:38 UTC: "Yes, merge it now; the failing test is unrelated and its fix is a separate
  request") applies: no rerun. Merge on the run's other green Linux and Windows checks once a cause-fix request is
  handed up (`hand_up_requests`), and name the red and that request in the PR.
- **A job red with "The runner has received a shutdown signal" or "lost communication with the server", and no step
  failed, is the runner's machine, not a test** (w3152, ffu #286: biscuit dropped its portal link three times at
  07:34-07:39Z on 2026-11-06; lothdesktop at 100% CPU lost ffu-lothdesktop-2). Check `portal_logs` (journal, grep the
  machine), then re-run the failed jobs and say why: that is not a flaky-test rerun. `gh run rerun --failed` needs a
  finished run; one held open by queued macOS legs needs `gh run cancel`, then `force-cancel` (above).
- **An artifact upload or download that fails on the network is biscuit's Wi-Fi, not ffu** (w3427, ffu #389's
  `getaddrinfo EAI_AGAIN productionresultssa17.blob.core.windows.net` after `Request timeout: ... CreateArtifact`).
  Biscuit is on Wi-Fi (`wlp194s0`, -66 dBm). A read-only probe leg measured 4% loss in 200 pings to its router, and 4 of
  60 artifact-store lookups took over 5 s (2026-11-07). Since ffu #400 the diagnostic uploads (lavapipe-captures,
  crosscheck-*, fuzz-artifacts) carry `continue-on-error: true`, so the check step is the job's verdict. A missing
  crosscheck trace still fails `crosscompare`, which names the machine. To plant an upload network failure in a probe,
  set the step's `https_proxy` to a host that can't resolve. The runner overrides a step's `ACTIONS_RESULTS_URL`: run
  42399250233 uploaded anyway. Put probe workflows on a `probe/*` branch triggered on push, so `ci.yml` doesn't run.
  A sandbox can't delete a remote branch, so hand the probe branch's deletion up.
- **CI time on biscuit is compiling, not testing** (w3152, measured): the old single Linux `check` job took 11.8 min
  alone and 32.3 min with 4 copies at once, because every compile step slowed about 4x on the 16 cores while the tests
  barely moved. So Linux runs `lint`, `check` and `check-release` as separate jobs on separate runners (ffu #286). A
  new Linux step goes in the job whose build it reuses; never add a step that builds a new profile or feature set to
  `check`.
- **Never `cargo test -p <crate>` after the workspace `--all-features` build in one job**: Cargo resolves features
  again for the packages one command selects and rebuilds much of the tree (2.5 min a step idle, 5 under load). Run the
  binaries already built with `tools/run_built_tests.sh <package> [<target>] -- <libtest args>` (ffu #286).
- **A line protocol on a raw `TcpStream` sets `set_nodelay(true)` on both ends and sends each line as one
  `write_all`**: `writeln!` writes the line and its `\n` separately, and Linux's Nagle plus delayed ACK held each reply
  about 82 ms. `deploy`'s 2000-poll test took 164 s on biscuit and 0.07 s on BEAST (w3152, measured; ffu #286). A test
  that is fast on Windows and slow only on Linux, in a request-reply loop, is this first.
- Read CI by commit, not by `gh pr checks` (a vault token cannot read checks):
  `gh run list -R Final-Factory/ffu --commit <sha>` and, on red, `gh run view <id> -R Final-Factory/ffu --log-failed | tail -80`.
  While the run's `ffu-macos` legs sit queued (m3 runners offline) the run stays "in progress" and `--log-failed`
  (or `--job <id> --log`) answers "logs will be available when it is complete". Read a finished job anyway:
  `gh run view <id> -R Final-Factory/ffu --json jobs --jq '.jobs[]|"\(.databaseId) \(.name) \(.conclusion)"'`, then
  `gh api repos/Final-Factory/ffu/actions/jobs/<job id>/logs --allow-escape-sequences | sed 's/\x1b\[[0-9;]*m//g' > "$TMPDIR/job.log"`
  (without the flag gh refuses the colour codes and writes nothing; w2895 leg D, ffu #257, 2026-11-06).
  To wait, use `blocked_on` with `ci:Final-Factory/ffu#<n>` and the head, never a poll loop.
  - **A `ci:` wait ends as soon as one leg fails** (w3272), even while the other legs are still queued. When that
    red is a test your PR doesn't touch, and you will merge over it (below), a second `ci:` wait on the same head
    resumes you at once. In w3459 it resumed twice, with all four biscuit runners busy and the Linux legs queued.
    Hand up the fix for the cause, then set `wake_me` for the legs still to run. Read them by job:
    `gh run view <id> --json jobs`.
- A PR that adds or changes art (`art/`), or the code that draws the image (`crates/ffu-bake/src`, `crates/ffu-render/src`
  and `effects/`, `crates/ffu-client/src/fx.rs`, any `.wgsl`; w3097, ffu #222's baked sky), runs the evidence-gate's `pr_evidence.py --repo Final-Factory/ffu --pr <n>`
  before Ben is asked and before it merges: it wants `Reference capture:` and `Art language:` in `## Evidence`
  (ffu-drive, "Art previews"; w2895).
  A decoder-only change in those paths that draws nothing (w3385: `ktx.rs` refusing malformed files) still trips
  it; it passes with `Reference capture: n/a: <why, 25+ characters>` and an `Art language:` line saying no colours,
  no HDR accent and no bloom change. Run the newest `pr_evidence.py` (`sort -V` over the plugin cache): the merge hook
  refuses an older copy.
- Merge on green: `gh pr merge <n> -R Final-Factory/ffu --merge --match-head-commit <sha>`. "Not mergeable" means
  another PR touched the same lines (often `docs/PLAN.md`): `git merge origin/main`, keep both sides, push, wait for CI
  again. Never force-push or rebase a pushed branch.
- A conflict in a feature-gated list (`mod` lines under `#[cfg(feature = ...)]`, as in `ffu-bake/src/lib.rs`) keeps
  each side's `#[cfg]` line, and the check after it builds the crate without the feature too (`cargo check -p <crate>`):
  `--all-features` passes locally while CI's featureless build fails (w2895: ffu #149's merge dropped the `bake` gate on
  `surfaces`, and CI went red with E0433 on `png`).
- **Two PRs that each add a row to a fixed-length array can each pass CI and still break main together** (w3384).
  - ffu-ui's `locale.rs` `WORDS: [[&str; 11]; N]` is such an array. #377 and #379 each added one word and each set N
    from 46 to 47.
  - Git merged them without a conflict, and each PR's CI ran before the other merged.
  - Main then held 48 rows under a 47, and `ffu-ui` failed with E0308 until ffu #382.
  - Before merging a PR that changes such a length, check `git log HEAD..origin/main -- <file>`. If main touched the
    file since your CI ran, merge `origin/main` in and run `cargo check -p <crate>` first.
- **A `#[path]` on a `mod` declared inside an inline `mod tests {}` builds on Windows and fails on Linux** (w3384, ffu
  #377).
  - Its path is resolved from a folder named after the inline module (`src/follow/tests/`), which does not exist.
  - Windows resolves `..` from the text alone, so the path works there. Linux needs every folder on the path to exist,
    so CI's Linux `lint` and `check` went red at 7bef972.
  - Declare the module at the file's top level under `#[cfg(test)]`, where the path is relative to the file's own
    folder, and reach it from the tests through `use super::*`.
- `docs/PLAN.md` is the shared board: mark your row "in progress: <session> (wNNN)" in a one-line PR before you start,
  and record its result, with measured numbers labelled, in a PR when it is done.
- **A multi-process `ffu-server` test that fails now and then on a shared machine: rule out a full disk first.**
  Grep every child's stderr (`FFU_FAILOVER_LOGS=<dir>`) for `os error 112` (Windows: disk full; Linux `ENOSPC`, "No
  space left on device"), and read the portal journal (`portal_logs`, grep the machine, `disk`) for that time. A child
  that hits it dies, so its peer sees a link that closes right after its hello, or a run that never reaches its end.
  w3374 (ffu #380): two loose chain-takeover failures on lothdesktop came while V: filled to 0. With 19 GB free the
  same test passed 34 of 34 (measured). Only then chase a race.
- A flaky test is fixed at its cause, never by a rerun, a retry or a longer timeout (Ben, w2895). In `ffu-server`'s
  tests a server running free (`--tps 0` to an `--until-tick`) can finish its whole run while the test thread is held
  up: on BEAST one 2.17 s progress read let the peers run from tick 2490 to the end with events still unsent, so
  `peers.rs` saw 93 of 100 (measured, ffu #209). Pace such a server from the test (the peers test's `Gate` lets the
  relays the test owns forward only while it is watching). Prove the fix with a planted stall that fails before and
  passes after, plus a loop of 50.
  - **The loop of 50 on a CI runner is `.github/workflows/repeat.yml`** (w3402, ffu #383). It builds once, then runs
    one test target N times in a row and stops at the first failure. Dispatch it with package, target, filter, count
    and os (`gh workflow run repeat.yml -R Final-Factory/ffu -f target=owner_term ...`). A PR that changes repeat.yml
    runs it with its defaults. Keep the filter empty so the whole file repeats: ffu #383's first whole-file pass found
    a second flake, at run 24, that a filter on the fixed tests would have hidden.
  - **A lone shard takes `--paced` too** (w3437, ffu #405): the plain server's stdin `until T` lines, for a shard with
    no peers and no standby (a standby or a peered shard still refuses it). `gateway_failover` keeps each owner one
    tick ahead of the client (`Proc::pace`). Free at `--tps 200`, a 1 s hold of the test thread let the owner run
    about 200 ticks ahead, so the ticks "after" a kill had been made before it (0 re-subscriptions), or the restarted
    owner's next 150 ticks ran before any op reached it ("own ops ... 0 after").
    - Raise a restarted owner's pace only once the gateway holds its Welcome (`gw.stats().resubscribes != 0`, within
      `stall::ALIVE`). Raised earlier, the owner ticks once before the gateway's subscribe arrives, its Welcome is one
      tick past the client's, and the client waits for a tick the test never allows (10060; seen once locally).
    - A repeat run's RED on BEAST may not reproduce a local plant: main with both 1 s holds failed locally and passed
      10 of 10 on ffu-windows (run 42405135217). Keep the local RED as the proof, and say in the PR which it was.
  - **A failover test must not assume an owner stays owner until the test stops it** (w3417). A loaded runner
    can stop a process past the link timeout plus the takeover wait (1 s + 500 ms). Its standby then takes over
    legitimately, and a tell to the standby that lost hits a closed pipe. Check that round as you check a kill
    (fenced old owner, one term, every message once) and plant it with SIGSTOP on the owner
    (`FFU_OWNER_TERM_PAUSE_OWNER_MS`). On failure, quote the child's start line, exit status and stderr tail
    (`Proc::state` in owner_term.rs): CI's temp folder is gone by the time anyone reads the log.
- **A red in a test your PR does not touch is not rerun and does not hold the PR** (w3412, ffu #262). Ben, on ffu #370's
  failover red: "Yes, merge it now; the failing test is unrelated and its fix is a separate request." Name the exact
  failing test and line from the red run, hand up its cause fix (or name the one in flight), and merge on every other
  Linux and Windows check green, with the test and that request named in the PR. First read every job of that attempt
  (`gh api repos/<o>/<r>/actions/runs/<id>/attempts/1/jobs`): a `gh run cancel` also cancels jobs still queued, and
  #262's Linux `hashcheck`, queued 22 min behind busy biscuit runners, was cancelled that way without running: not
  green. Merge `origin/main` in and push for a fresh run instead, and wait for that leg however long it queues.
- **BEAST can freeze as a whole machine for 20 to 100 s, and a test's wall-clock wait then runs out with nothing wrong in
  the code** (w3341, ffu #357 probe, ffu #358 fix).
  - It happens when other work on BEAST runs it short of memory and it pages: soaks, extra Unity editors, every
    sandbox busy.
  - On 2026-11-07 four ffu-beast runners stalled for the same 22-23 s at 09:14:47Z. Counters: CPU 100 %, run queue up
    to 65, 6.4 GB free, up to 37,000 pages/s (measured).
  - A new owner's start line took 103 s (CI run 42349485056). BEAST's daemon lost its portal link for about a minute,
    six times, with no ffu job running.
  - The signs:
    - reds in unrelated multi-process tests on several BEAST runners within seconds of each other;
    - an empty start line after `recv_timeout`;
    - 10060 or 10054 on a connection that was healthy.
  - Measure it with `tools/probe_stall.sh <minutes> <dir>` (branch w3341-probe-stall, never merged). It runs a 200 ms
    sleep clock that prints `STALL` for a gap of 1.5 s or more, typeperf every 2 s, and a read of the System, Defender
    and Application logs. Run it as a `shell: cmd` step calling `"%ProgramFiles%\Git\bin\bash.exe"` in 5 matrix copies.
    The same stall time on every copy means the whole machine froze.
  - A wait that only checks that a process is alive (a start line, a client read, `resubscribe_within`, a standby's
    `hold`) uses `stall::ALIVE` (180 s) from `crates/ffu-server/tests/support/stall.rs`. Every wait's panic appends
    `stall::note()`. That is a longer timeout with the measured stall as its evidence, not a loosened claim; never
    lengthen a latency or ordering check this way.
  - Prove it with a planted slow start: an env var makes the Nth child of a kind sleep 40 s before `main`. ffu #358:
    main failed 9 of 9, the fix passed 9 of 9, and then 30 of 30 rounds in 10 copies on BEAST.
  - **Give `stall::ALIVE` to every liveness read in the file you touch, and sweep the others** (w3416, ffu #393).
    w3341 changed only the tests that had failed, and the next freeze broke the ones it left. At 16:41-16:45Z on
    2026-11-07, three BEAST runners went red on client reads with 10060:
    - shard.rs's 10,000-tick follower, on the client's default 30 s from `client.rs:128`;
    - `gateway_standby.rs:224`;
    - `sim_switch`.

    Sweep with `grep -rn 'connect_station\|connect_gateway\|Client::connect\|set_timeout' crates/ffu-server/tests`.
  - **Tell a freeze from a code stall before you fix anything.** Read the portal journal (`portal_logs`, journal,
    grep `beast`) for `machine beast: no answer for N s` near the failure. Its times are in -07:00. Then list the
    BEAST jobs of other runs in the same minutes and look for 10060 reds in tests that do not share code (w3416:
    the daemon was off its link from 16:42:25 to 16:45:21Z, around the test's 30 s silence).
  - **Plant the freeze in the server thread**, on a probe branch only. A one-off
    `if step.tick == 3000 { sleep(40 s) }` in `ShardServer::run`'s tick loop reproduced the CI panic exactly:
    shard.rs:383, 10060, 31.5 s on ffu-beast-5. It also catches an in-process server, which an env var on a child
    cannot reach.
  - `gh workflow run repeat --ref <probe branch>` works before repeat.yml is on main, once the probe branch carries
    it: dispatch RED, GREEN and the fix alone in parallel (runs 42394090019, 42394092744, 42394095691).
  - The product's own timers (gateway `WRITE_TIMEOUT` 10 s, a 1 s `--takeover-after-ms`, the follower's 5 s read)
    still lose to a longer freeze. The real fix is BEAST's load, which needs Ben.
- **A count a test reads once the far end has the bytes is counted before the write, never after** (w3167, ffu #300).
  `proxy.rs`'s `pipe` did `write_all` and then `fetch_add`: the test's client read its last 4-byte echo and the test
  read `stats()` while the down thread sat between the two, so it saw `(160, 156)` on ffu-biscuit-3. A count that is
  exactly one chunk short, with every byte delivered in order, is this. Plant a sleep right after the write for RED
  (0 of 10 on Windows and Linux, measured); GREEN 10 of 10 and the fix alone 50 of 50 on both. Any counter, flag or
  log line a test checks after the other side saw the data follows the same rule.
- **A gateway or proxy that closes a stream while the peer still has unread data from it loses that data** (w3404, ffu #389).
  - What happened: when a client left, `ffu-gateway`'s `client_reader` called `shutdown(Both)` on the owner's stream, and the session closed it again at once.
  - The shard's reader thread had not yet read the client's last `OP_TAGGED` frames.
    - On Windows its read then failed with os error 10053 and the buffered ops were gone.
    - On Linux the gateway saw "Broken pipe" and the shard "client N dropped: its socket failed".
  - `sim_switch`'s in-flight ops test then saw the last ~5-25 ops never stamped (ops_forwarded 17043, ops_acked 17038).
  - The fix:
    - shut down `Write` only, so the far end reads everything sent and then sees EOF;
    - then read the far end's acks until none is outstanding, it closes, or a cap passes (`drain`, 10 s);
    - only then close the stream.
  - Each half alone still failed 3 of 3.
  - For RED, plant a one-shot stall in the receiving reader near the run's end: from tick T, each reader sleeps once for `ms`. Use `FFU_PLANT_SLOW_OPS=1120:500` at 64 tps, where the senders stop at 1136 and the run ends at 1200. The held ops then wait in the socket while the client leaves, and the reader resumes before the run's end, so a lost op was lost to the close.
  - Measured: main failed 3 of 3 on Windows and 5 of 5 on biscuit; the fix passed 3 of 3 and 5 of 5 planted, then 50 of 50 unplanted in a row on ffu-biscuit-3.
  - A test that loses exactly the last ops a client sent before it hung up is this first.
- A plain `ffu-server` (no shard) at a fixed `--tps` keeps ticking between the test's last read and its kill or check:
  `server.rs`'s kill -9 test ran on past its next `--snapshot-every` snapshot when the test thread was held up 125 ms,
  and recovery replayed none of the client's ticks (ffu-lothdesktop-1, CI run 41921083432; w3109). Start it with
  `--paced` and write `until T` lines to its stdin, one tick ahead of the client, so it is parked at a known tick when
  the test acts (ffu #242; RED with `FFU_KILL9_STALL_MS=300`, GREEN at 300 ms and 2 s, 50 of 50 on Windows).
- **A `--tps 0` server's pace is its disk's**: with `--sync every` (the default) each tick waits on `sync_data`, about
  80 ticks a second on BEAST and 2 on ffu-lothdesktop-1 (measured, w3095, ffu #227). The same test crawls out of time
  on one runner and outruns the test thread on another. Run test shards at a fixed `--tps` with `--sync none` (the
  replica takes `--sync` too since ffu #223), and assert the run had not passed its end when the test acted.
  `failover.rs` does so (`FFU_FAILOVER_TPS`, `FFU_FAILOVER_SYNC`); plant a slow disk (a sleep after `sync_data`) and a
  fast one (no sync plus a held test thread) for RED. `FFU_FAILOVER_LOGS=<dir>` keeps every child's stderr.
- **A `--sync every` shard at a fixed `--tps` can go silent for over 30 s on a loaded Windows disk** (w3168, ffu #302).
  Its tick runs 16 `sync_data` calls, and `ShardServer::run` answers hellos only between ticks. A shard that is alive
  and ticking then leaves a client's Welcome read to time out: `read Welcome: ... (os error 10060)` (shard.rs's kill -9
  test, CI run 42181965847, ffu-beast-2). On BEAST's F: drive, one tick's 16 fsyncs took a median of 5.2 ms when the
  disk was idle and up to 23.5 s with 4 buffered writers loading it (measured). A 10060 means the shard is alive; a
  dead one gives 10054 or EOF.
  - Every test shard runs `--sync none`. Since #302 that flag also skips the snapshots' `sync_all`.
  - A kill of the process loses nothing written through `write()`, so `--sync none` keeps a kill -9 test's claim.
  - For RED, plant a sleep after each synced append past the restart's first tick; it then hits only the restarted
    shard.
  - `tests/shard.rs` writes each child's stderr to `<dir>.stderr-N.log` and prints that log when the test panics.
- The Windows runners have no `pwsh`, and their execution policy refuses `shell: powershell` steps: write probe steps
  in `shell: bash` or `shell: cmd` (w3095).
- **A test never picks a port and then drops it for a child process to bind later** (Ben, w3096). The process binds
  `:0` itself and reports its address (its JSON start line: `listen`, `peer_listen`, `standby_listen`, `control`), or
  it is handed a listener that is already bound. A port that has been let go can be taken by any `bind(0)` or
  `connect()` on the machine before the child binds it. `directory.rs`'s `free_port()` failed this way on BEAST
  (`bind 127.0.0.1:62923 ... (os error 10048)`, then `replica 1 did not start`, CI run 41885835149) and on
  lothdesktop. Peers whose address is not known yet get `127.0.0.1:0` (never dialled), and the test tells them the
  address afterwards on stdin (`peer ID ADDR`, `replica ADDR`; ffu #225). A restarted process takes a new port.
  Proof: a planted holder that binds the port between the pick and the child's bind fails before and passes after
  (#225 holds every restarted replica's old port), plus the loop of 50 on Windows. A general holder: a hook in the
  test's spawn that binds every `127.0.0.1:N` (N not 0) in the child's arguments that nothing holds yet. An address a
  live process holds fails to bind and is skipped, so it takes only a picked-and-dropped port (w3102: it held 5 and
  failed all 3 of main's failover tests, held none on the port-0 version). A standby reports its held peer port as
  `peer_listen` in its start line (ffu #233), so `--peer-listen 127.0.0.1:0` works there too.
- Check before a test PR merges: `grep -rn 'bind("127.0.0.1:0")' crates/*/tests crates/*/src` and read each hit. A
  listener dropped before its port goes into another process's arguments is the race above. A listener the test
  keeps, or a dead address that is meant to refuse, is fine.
- **A test polls a process on one kept connection, never a new connection per poll** (w3096). Every closed
  connection holds its client port in TIME_WAIT for minutes, and the runners on one machine share its ephemeral ports:
  status polls every 5-20 ms ran BEAST out, so `connect` failed with `os error 10048` (`--connect 127.0.0.1:N: Only one
  usage of each socket address`). Main's `rolling_deploy` and `sim_switch` passed 18 of 50 Windows runs (probe ffu
  #230); with `deploy::ControlConn` (one connection per shard; the control port answers every line on it) BEAST passed
  40 of 40 (ffu #229, measured). A 10048 on a `connect`, not a `bind`, is this. Check: `grep -rn 'deploy::request'
  crates/*/tests` finds none inside a loop. One old `deploy_ops` run left 2280 TIME_WAIT sockets on its 3 control
  ports in 30 s, and 0 with `ControlConn` (w3101, measured by diffing `netstat -an | grep TIME_WAIT` before and after
  a run, grouped by remote address). `deploy::tests::a_poll_holds_one_connection_however_many_requests_it_sends`
  asserts one accepted connection (`Control::connections()`) for 2000 polls (ffu #235).
- **A test's scratch folder or file comes from `tempfile`**, held until the test ends
  (`let guard = tempfile::Builder::new().prefix("ffu-<what>-").tempdir().unwrap(); let dir = guard.path();`; a helper
  returns the `TempDir`, not its path), never a hand-made `std::env::temp_dir().join(...)`: those were never removed and
  left about 18,500 `ffu-*` folders (11.3 GB) in biscuit's `/tmp`, which turned every biscuit job red (w3118, w3119).
  `tools/check_temp_leaks.sh <command>` runs every `cargo test` step in CI on an empty temp folder and fails on anything
  left there; run your test through it locally too (`tools/check_temp_leaks.sh cargo test -p <crate>`; ffu #248).
- Before writing an ffu fix, list the open PRs on the same files (`gh pr list -R Final-Factory/ffu --state open
  --json number,title,files`): w3096 and w3101 each wrote the same kept-connection helper at the same time, and the
  second had to rebuild on the first (ffu #229, #235).
- **A wire decoder that checks exact lengths takes every form that main and the open PRs send**. Before such a
  decoder merges, list each sender's frame lengths on main and in the open PRs on the same file. Read a trailing flag
  through the decoder, by length, never by byte position (w2895, ffu #280). P0.14b's exact `replica::Hello` and
  `HelloAnswer` decoders first knew only the 4- and 8-byte forms, missing the 16- and 20-byte owner forms. They then
  refused M2.30's trailing `LIVE` keepalive byte from ffu #277 (merged first), and a peer that sent it would have been
  dropped. The fix was `split_live`: strip the flag when `len % 4 == 1`, refuse any other odd last byte, then match the
  lengths. A test then loops over every form with and without the flag, plus a bad extra byte.
- Before blaming your change for a Windows flake, run the same probe on unchanged `main` (a probe PR with main's code
  and the same loop): w3096's #229 looked like it failed 31 of 50, and main failed 32 of 50 the same way.
- `tools/sim_switch.sh` builds sim build A from the working tree, but its planted build B from a `git worktree` of
  `HEAD` (`sim_switch.sh:49`). An uncommitted merge or edit therefore reaches A and not B, so commit before you run it
  (c11bb9a1, w3086).
- To loop one test on the Windows runners, open a draft probe PR whose `ci.yml` runs only that test
  (`cargo test -p <crate> --test <file>`) in N matrix copies: they spread over `ffu-beast*` and `ffu-lothdesktop-*`.
  Set `timeout-minutes: 40`, because a lothdesktop runner took over 25 minutes for 10 peers rounds (w2895, #210).
  Close the probe PR without merging it.
  - The same probe loops on Linux (`runs-on: [self-hosted, ffu-linux]`). Give each matrix leg its own branch through
    `actions/checkout` `ref:`, so RED (main + the plant), GREEN (the fix + the plant) and the fix alone run in one
    probe PR (w3167, ffu #299). A sandbox cannot delete remote branches, so the probe branches stay after it closes.
  - The lothdesktop runners carry the same labels as BEAST's (`self-hosted, Windows, X64, ffu-windows`), so 20 copies
    can all land on BEAST's five runners. Use 40 copies to get lothdesktop runs (w3104: 40 copies gave lothdesktop 2 or
    3 of them per round).
  - A loop of runs inside one step under bash `-e` ends at the first failing `cargo test` or `grep` and prints
    nothing about it: put `|| true` after both.
  - Failures on several BEAST runners at the same wall-clock millisecond are a stall of the whole machine, not the
    test. Check `portal_logs` (journal, grep `beast`) for a daemon update or a leftover-process kill at that time
    (w3104: three runs' A shards were released at the same moment).
- **A read timeout on a live owner is a stall, not a move** (w3136, ffu #264). BEAST's four shards once went quiet for
  10.6 s (CI run 42137090708), past `ffu-gateway`'s 10 s `upstream_timeout`. `relay` re-subscribed all 8 stations to
  the same shard and epoch at tick 97 and lost the frame in flight, so `rolling_deploy` saw "left 98 right 97". You
  can tell this case from the log: every station's "re-subscribed from shard N (epoch E, ...) to shard N (epoch E,
  ...)" line names the same shard and epoch on both sides, all at once. The fix keeps the stream unless the route
  moved, and keeps a frame the timeout cut (`read_up`, `Up::pending`). Any follower that reads with a timeout keeps
  this rule. Proof: `an_owner_silent_past_the_upstream_timeout_with_its_lease_unchanged_is_kept` (RED on main),
  then 80 of 80 `rolling_deploy` and 120 of 120 stall-test runs on Windows (probe #265). So a timed-out recv leaves
  a Windows socket readable (measured).
- `ffu-server follow` reads with a **5 s** timeout (`tools.rs`, `follow`), not the 30 s `client.rs` sets at connect. A
  test with followers fails on any client silence over 5 s, and the timeout is never the fix. Find the step that
  makes the silence (w3104, ffu #244):
  - A connect to a refused loopback port holds about 2 s on Windows. So code that dials an address it looked up keeps
    looking the route up while it dials, and drops the dial once the route moves (`ffu-gateway` `open_watching`).
  - A test acting as the operator starts the shards at once, not one after another, while clients wait
    (`sim_switch.rs` `start_all`). Four starts one after another took 4.5 s on a loaded lothdesktop runner.
  - Plant a slow start by setting `FFU_SWITCH_TO` to a `.cmd` wrapper (`@echo off`, `ping -n 3 127.0.0.1 >nul`, then
    `"<ffu-server.exe>" %*`).
  - **A Windows process start can itself take 14 to 17 s** (w3173). `sim_switch`'s four-shard test failed 1 in 50 on
    BEAST with every follower at 10060 because the test's `Command::spawn` of the first next-build shard, right after
    the A shards exited, blocked 13.8 s and 17.1 s inside CreateProcess (2 of 100 probed runs). Every other start in
    those runs took 48 ms or less, 40,598 bare starts in 20 min took 0.44 s at worst, and 7,717 starts right after
    writing fresh 2 MB files took 74 ms at worst (measured, BEAST, debug build). The gateway's own threads ran on time
    throughout, so no ffu code was in the stall. Before blaming ffu code for a switch timeout, probe the test's spawn
    and the gateway's subscribe loop with probes that stamp their own time
    (`eprintln!("@{} PROBE ..", SystemTime::now()...as_millis() % 10_000_000)`), never a timestamper reading the pipe:
    that reader can be starved exactly when the machine stalls.
  - **The stall is Defender's real-time scan queue** (w3182, trace on BEAST 2026-11-06 15:22Z). Defender scans a new
    file when it is closed and an exe when it starts, synchronously in the caller's thread. When other sandboxes
    flood it (cp of a Unity `Library/BurstCache`, a cold cargo build), every scan on the machine waits 9 to 24 s. In
    `sim_switch` three shards closed their tick-256 `snap-*.bin.tmp`, waited 11.0 s, then 1.6 s more, and stopped
    ticking, so the followers hit their 5 s timeout (measured). Trace it without admin: BEAST's
    `Performance Log Users` holds `NT AUTHORITY\INTERACTIVE`, so `xperf -start <name> -on <guids> -f x.etl -FileMode
    Circular -MaxFile 2048` with user-mode providers works (Antimalware-Engine `0A002690-…`, -RTP `8E92DEEF-…`,
    -AMFilter `CFEB0608-…`); `wpr -start CPU` (the kernel logger) is refused. Stop the trace as soon as a run fails,
    because 2 GB holds only a few minutes. `tracerpt x.etl -of CSV`, then pair each Engine `Start`/`Stop` by its scan
    id: an AMFilter `OnClose` event raised in the ffu process itself means that thread is waiting on the scan.
- **A BEAST-only flake whose runs take 2.5 times their normal time means a loaded machine** (w3173). w3167's three
  `sim_switch` failures ran 54 s against a normal 21 s while w3168's disk-hog writers ran in another sandbox. Check the
  other sandboxes' transcripts (`~/.claude/projects/F--ffw-sandboxes-slot*/*.jsonl`, the tool calls at the failure's
  UTC time) for planted load: hog writers, busy loops, Unity batch builds. A whole-machine freeze shows as many
  processes waking in the same millisecond (four A shards "exited" at one stamp, 11 to 21 s late). A leg that plants
  CPU or disk load breaks other sandboxes' tests, so it holds an exclusive bench ticket
  (`bench_queue.py timed`) like a timing leg.
- **Never create, close and rename a file inside a loop that answers peers** (w3271, ffu #328). The directory
  replica wrote `replica.bin.tmp`, closed it and renamed it inside its election loop. On ffu-lothdesktop-2 one write
  took 0.25 to 2.1 s with `--sync none` (the close is where Defender scans), past the 120 ms election floor. No leader
  settled, and clients read 10060 at directory.rs:277. The fix appends a checksummed record to one file kept open
  (`StateFile`): RED 0 of 40, GREEN 40 of 40, fix alone 96 of 96 on Windows (probe #327). A slow close or rename is
  the first suspect for any Windows stall in a loop that writes state.
- **A loose shard's taken batches are due on its next tick** (w3271, w2895; ffu #329). A test that holds one shard
  until a peer catches up must leave ticks after the hold, or keep the peer at its pace all through. The dilation
  test held A before its last tick, so the credits A took then were due on a tick that never ran ("B's sink took
  nothing", job 128216280042).
- **A probe's round logs go in a folder of its own job** (`$RUNNER_TEMP/<what>-${{ github.run_id }}-<leg>`): the ffu
  runners check out with `clean: false`, so a `round-*.log` an earlier leg left in the workspace was read into a later
  leg's summary (w3271, probe #327: 301 ms "a write took" lines came from a planted leg's stale `round-5.log`).
- **Cold Windows builds came from the shared `target/`, not from Cargo changes** (w3271, ffu #328). Every job on a
  runner shares one `target/`, and the old end step ran `cargo clean` past 20 GB. `tools/ci-runners/keep_target.sh`
  removes `target/native` and `target/release` first and leaves a mark that the next build prints, so a cold build
  says whether `target/` was emptied and by which job. Clippy is a job of its own, and the Windows test job has
  45 minutes.
- **LothDesktop under its agents' load runs ffu's multi-process tests up to 24 times slower than BEAST** (w3271,
  measured, job 128193001946: lookahead 228 s against 9 s, peers 137 s against 15 s, at 98-100% CPU with 6 to 8 of
  its 10 agents mid-turn). Every test passed. A slow or timed-out job on ffu-lothdesktop-* is the machine first:
  check `portal_logs` (journal, grep `lothdesktop`) for its CPU and busy agents at that time before you read the
  tests. Ben picked load-gated runners for it (w3271 follow-up).

## 5. Timing claims

A number is MEASURED only with its machine, build profile, building count and tick count beside it, and under the
bench ticket on FF Factory machines (ffu `CLAUDE.md`, "Timing claims"). `ffu-headless run ... --timings t.csv`,
`ffu-headless phases --start ... --ticks N` and `ffu-headless fpbench` are the timing commands.

## Checking these skills

`python3 check_ffu_skills.py [--ffu <ffu checkout>]` (beside this file) fails when an `ffu-*` skill names a Unity or
FF1 tool, or, given a checkout, a binary, subcommand, flag, agent method or `tools/` script ffu does not have. Run it
with `--ffu` after changing any `ffu-*` skill or after ffu's command line changes.

`skill-map.md` beside it says, for every ff-agents skill, what to use in an ffu checkout: an `ffu-*` skill, the same
skill (shared), or nothing yet (FF1 only, with the reason). The checker fails a skill the map leaves out, a replacement
that does not exist, and an FF1 skill whose description does not name its replacement. A new ff-agents skill needs a
row there.
