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
- Put those exports in `$TMPDIR/rust.sh` and source it in every shell call: shell state does not persist.

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
- Fuzzing is by hand only: `tools/fuzz.sh [seconds] [target ...]` (nightly and cargo-fuzz).

## 3. The rules a sim change keeps

`crates/ffu-sim` holds no floats, unordered maps or sets, interior mutability, clock, files, threads, environment, GPU
or unsafe code, and no panics in the tick (use `get`, `checked_*`, `saturating_*`, `wrapping_*` and say why).
`tools/check_sim_rules.sh` greps comments too, so write a banned type's rule in words. Every change to a sector is an
`Op` through `Sector::submit` (adding one: `/ff-agents:ffu-add-op`). A snapshot layout change bumps
`SNAPSHOT_VERSION`, keeps the old decoder and adds a fixture in `crates/ffu-sim/tests/fixtures`; existing fixtures are
never rewritten (`tools/check_snapshot_compat.sh BASE_REF` holds it in CI). No thread count may change a hash.

## 4. Land it: PR, CI with gh, merge your own

- Push your branch, `gh pr create -R Final-Factory/ffu --base main --title ... --body-file ...`, with
  `Request: wNNN` (or `Part of: wNNN`) in the body.
- CI runs on ffu's own runners, one job at a time each: `ffu-linux` (biscuit), `ffu-windows` (BEAST), `ffu-macos`
  (the M3). A job waits while its machine is off; a queue of several minutes is normal.
- Read CI by commit, not by `gh pr checks` (a vault token cannot read checks):
  `gh run list -R Final-Factory/ffu --commit <sha>` and, on red, `gh run view <id> -R Final-Factory/ffu --log-failed | tail -80`.
  To wait, use `blocked_on` with `ci:Final-Factory/ffu#<n>` and the head, never a poll loop.
- A PR that adds or changes art (`art/`), or the code that draws the image (`crates/ffu-bake/src`, `crates/ffu-render/src`
  and `effects/`, `crates/ffu-client/src/fx.rs`, any `.wgsl`; w3097, ffu #222's baked sky), runs the evidence-gate's `pr_evidence.py --repo Final-Factory/ffu --pr <n>`
  before Ben is asked and before it merges: it wants `Reference capture:` and `Art language:` in `## Evidence`
  (ffu-drive, "Art previews"; w2895).
- Merge on green: `gh pr merge <n> -R Final-Factory/ffu --merge --match-head-commit <sha>`. "Not mergeable" means
  another PR touched the same lines (often `docs/PLAN.md`): `git merge origin/main`, keep both sides, push, wait for CI
  again. Never force-push or rebase a pushed branch.
- A conflict in a feature-gated list (`mod` lines under `#[cfg(feature = ...)]`, as in `ffu-bake/src/lib.rs`) keeps
  each side's `#[cfg]` line, and the check after it builds the crate without the feature too (`cargo check -p <crate>`):
  `--all-features` passes locally while CI's featureless build fails (w2895: ffu #149's merge dropped the `bake` gate on
  `surfaces`, and CI went red with E0433 on `png`).
- `docs/PLAN.md` is the shared board: mark your row "in progress: <session> (wNNN)" in a one-line PR before you start,
  and record its result, with measured numbers labelled, in a PR when it is done.
- A flaky test is fixed at its cause, never by a rerun, a retry or a longer timeout (Ben, w2895). In `ffu-server`'s
  tests a server running free (`--tps 0` to an `--until-tick`) can finish its whole run while the test thread is held
  up: on BEAST one 2.17 s progress read let the peers run from tick 2490 to the end with events still unsent, so
  `peers.rs` saw 93 of 100 (measured, ffu #209). Pace such a server from the test (the peers test's `Gate` lets the
  relays the test owns forward only while it is watching). Prove the fix with a planted stall that fails before and
  passes after, plus a loop of 50.
- **A `--tps 0` server's pace is its disk's**: with `--sync every` (the default) each tick waits on `sync_data`, about
  80 ticks a second on BEAST and 2 on ffu-lothdesktop-1 (measured, w3095, ffu #227). The same test crawls out of time
  on one runner and outruns the test thread on another. Run test shards at a fixed `--tps` with `--sync none` (the
  replica takes `--sync` too since ffu #223), and assert the run had not passed its end when the test acted.
  `failover.rs` does so (`FFU_FAILOVER_TPS`, `FFU_FAILOVER_SYNC`); plant a slow disk (a sleep after `sync_data`) and a
  fast one (no sync plus a held test thread) for RED. `FFU_FAILOVER_LOGS=<dir>` keeps every child's stderr.
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
  (#225 holds every restarted replica's old port), plus the loop of 50 on Windows.
- Check before a test PR merges: `grep -rn 'bind("127.0.0.1:0")' crates/*/tests crates/*/src` and read each hit. A
  listener dropped before its port goes into another process's arguments is the race above. A listener the test
  keeps, or a dead address that is meant to refuse, is fine.
- `tools/sim_switch.sh` builds sim build A from the working tree, but its planted build B from a `git worktree` of
  `HEAD` (`sim_switch.sh:49`). An uncommitted merge or edit therefore reaches A and not B, so commit before you run it
  (c11bb9a1, w3086).
- To loop one test on the Windows runners, open a draft probe PR whose `ci.yml` runs only that test
  (`cargo test -p <crate> --test <file>`) in N matrix copies: they spread over `ffu-beast*` and `ffu-lothdesktop-*`.
  Set `timeout-minutes: 40`, because a lothdesktop runner took over 25 minutes for 10 peers rounds (w2895, #210).
  Close the probe PR without merging it.

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
