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
- Merge on green: `gh pr merge <n> -R Final-Factory/ffu --merge --match-head-commit <sha>`. "Not mergeable" means
  another PR touched the same lines (often `docs/PLAN.md`): `git merge origin/main`, keep both sides, push, wait for CI
  again. Never force-push or rebase a pushed branch.
- `docs/PLAN.md` is the shared board: mark your row "in progress: <session> (wNNN)" in a one-line PR before you start,
  and record its result, with measured numbers labelled, in a PR when it is done.

## 5. Timing claims

A number is MEASURED only with its machine, build profile, building count and tick count beside it, and under the
bench ticket on FF Factory machines (ffu `CLAUDE.md`, "Timing claims"). `ffu-headless run ... --timings t.csv`,
`ffu-headless phases --start ... --ticks N` and `ffu-headless fpbench` are the timing commands.

## Checking these skills

`python3 check_ffu_skills.py [--ffu <ffu checkout>]` (beside this file) fails when an `ffu-*` skill names a Unity or
FF1 tool, or, given a checkout, a binary, subcommand, flag, agent method or `tools/` script ffu does not have. Run it
with `--ffu` after changing any `ffu-*` skill or after ffu's command line changes.
