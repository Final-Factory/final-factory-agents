#!/usr/bin/env bash
# ci_local.sh [options] [PR] [BODY_FILE]: run every step of ffu CI's lint and check jobs here, before a push (w4917).
#
# Run it from an ffu checkout (an ffu slot: `eval "$(ffu-slot take ...)"`), after merging origin/main in, as CI tests a
# pull request merged into main. It reads .github/workflows/ci.yml at your HEAD (ci_local.py), so the steps cannot
# drift from CI's; a step it cannot read stops it with exit 2 and names the step. Each step prints one line,
# PASS, FAIL or SKIP (runner upkeep, with the reason), and logs to $TMPDIR/step-<job>-<NN>-<name>.log; a failed step
# prints its last lines. Every step runs, after a failure too, so one run names every red. A step that runs past its
# `timeout-minutes`, else CI_LOCAL_STEP_MINUTES (default 60), is ended and prints TIMEOUT, so no step hangs the run
# (w4987: a test of tools/ci-runners/postmerge_culprit.py hung for 20 min and more on BEAST). Every step runs with
# PYTHONUTF8=1, as CI's Linux Python writes UTF-8 (w4987: the PR body's emoji stopped the row-doc step on Windows).
#
#   PR         the pull request number: row_numbers.py and check_row_docs.py check as on that PR, and its body is read
#              with gh unless BODY_FILE is given
#   BODY_FILE  the PR body (the file you give `ff-pr push --body-file`); with it and no PR, the steps check as on a new
#              pull request. With neither, they check as on a push to main (check_row_docs.py then has nothing to read)
#   --jobs J   the jobs to run, comma-separated (default lint,check; check holds the whole cargo test --workspace)
#   --list     print the plan and run nothing
#   --all      also run the steps that pass only on Linux (sweep_target_test.sh)
#   --ci-cargo-env  keep the workflow's CARGO_INCREMENTAL and CARGO_PROFILE_DEV_DEBUG (left out by default: they
#              change how cargo builds, not what passes, and flipping them rebuilds your warm target)
#   --base B   the base branch (default main)
#
# Exit 0 when every step passed, 1 when one failed, 2 when the plan could not be made. Linux, macOS, Git Bash.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
jobs=lint,check list=0 extra=() pr="" body=""
while [ $# -gt 0 ]; do
  case "$1" in
    --jobs) jobs=$2; shift 2 ;;
    --base) extra+=(--base "$2"); shift 2 ;;
    --list) list=1; shift ;;
    --all | --ci-cargo-env) extra+=("$1"); shift ;;
    -h | --help) sed -n '2,22p' "$0"; exit 0 ;;
    -*) echo "ci_local.sh: unknown option $1" >&2; exit 2 ;;
    *)
      if [ -z "$pr" ] && [[ "$1" =~ ^[0-9]+$ ]]; then pr=$1
      elif [ -z "$body" ]; then body=$1
      else echo "ci_local.sh: one PR and one BODY_FILE at most" >&2; exit 2; fi
      shift ;;
  esac
done

repo=$(git rev-parse --show-toplevel 2> /dev/null) || { echo "ci_local.sh: run it inside an ffu checkout" >&2; exit 2; }
[ -f "$repo/.github/workflows/ci.yml" ] && [ -f "$repo/tools/check_sim_rules.sh" ] \
  || { echo "ci_local.sh: $repo is not an ffu checkout (no ci.yml or tools/check_sim_rules.sh)" >&2; exit 2; }

native() { if command -v cygpath > /dev/null; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
tmp=${TMPDIR:-/tmp}
run_dir="$tmp/ci-local-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$run_dir"

# Windows: python3 may be the WindowsApps Store stub (exit 49), and CI's steps call python3 by that name.
PY=python3
if ! python3 -c '' > /dev/null 2>&1; then
  real=$(command -v python) && python -c '' > /dev/null 2>&1 \
    || { echo "ci_local.sh: no working python3 or python on PATH" >&2; exit 2; }
  mkdir -p "$run_dir/pybin"
  printf '#!/bin/sh\nexec "%s" "$@"\n' "$real" > "$run_dir/pybin/python3"
  chmod +x "$run_dir/pybin/python3"
  export PATH="$run_dir/pybin:$PATH"
  PY=python
fi

# cargo and cmake on PATH, as CI's setup steps put them (left out of the plan as runner setup): the toolchain in
# CARGO_HOME or ~/.cargo, else FF Factory's shared one under $FF_WORKER_ROOT/tools (lothdesktop); on Windows cmake for
# SDL3's build from there, else Visual Studio's, as the Windows jobs' first step finds it with vswhere.
unixp() { if command -v cygpath > /dev/null; then cygpath -u "$1"; else printf '%s\n' "$1"; fi; }
tools=""; [ -n "${FF_WORKER_ROOT:-}" ] && tools="$(unixp "$FF_WORKER_ROOT")/tools"
if ! command -v cargo > /dev/null; then
  for c in "${CARGO_HOME:-$HOME/.cargo}" ${tools:+"$tools/cargo"}; do
    c=$(unixp "$c")
    if [ -x "$c/bin/cargo" ] || [ -x "$c/bin/cargo.exe" ]; then
      export PATH="$c/bin:$PATH" CARGO_HOME="$c"
      r="$(dirname "$c")/rustup"
      if [ -z "${RUSTUP_HOME:-}" ] && [ -d "$r/toolchains" ] && [ ! -d "$HOME/.rustup/toolchains" ]; then
        export RUSTUP_HOME="$r"
      fi
      break
    fi
  done
fi
command -v cargo > /dev/null || { echo "ci_local.sh: cargo is not on PATH; see ffu-build-test, the toolchain" >&2; exit 2; }
if ! command -v cmake > /dev/null && command -v cygpath > /dev/null; then
  for d in ${tools:+"$tools"/cmake-*/bin}; do
    [ -x "$d/cmake.exe" ] && { export PATH="$d:$PATH"; break; }
  done
  if ! command -v cmake > /dev/null; then
    vswhere="$(unixp "${ProgramFiles:-C:/Program Files} (x86)")/Microsoft Visual Studio/Installer/vswhere.exe"
    [ -x "$vswhere" ] && vs=$("$vswhere" -latest -products '*' -property installationPath | tr -d '\r') \
      && export PATH="$(unixp "$vs")/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin:$PATH"
  fi
  command -v cmake > /dev/null || echo "note: no cmake on PATH; ffu-client's SDL3 build will fail" >&2
fi

[ -n "$body" ] && body=$(native "$(cd "$(dirname "$body")" && pwd)/$(basename "$body")")
args=(plan --repo "$(native "$repo")" --out "$(native "$run_dir")" --jobs "$jobs" ${extra[@]+"${extra[@]}"})
[ -n "$pr" ] && args+=(--pr "$pr")
[ -n "$body" ] && args+=(--body-file "$body")
"$PY" "$here/ci_local.py" "${args[@]}" || exit 2

if ! git -C "$repo" merge-base --is-ancestor origin/main HEAD 2> /dev/null; then
  echo "note: HEAD does not hold origin/main; CI tests your PR merged into main, so merge origin/main in first" >&2
fi
had_captures=0; [ -e "$repo/lavapipe-captures" ] && had_captures=1

# The step timeout: coreutils timeout (Linux, Git Bash; gtimeout from Homebrew's coreutils on macOS), else none.
step_minutes=${CI_LOCAL_STEP_MINUTES:-60}
tmo=$(command -v timeout || command -v gtimeout || true)
[ -z "$tmo" ] && [ "$list" = 0 ] && echo "note: no timeout or gtimeout on PATH; a step that hangs is not ended" >&2

fails=0 n=0
while IFS=$'\t' read -r verdict slug third name mins; do
  n=$((n + 1))
  if [ "$verdict" = SKIP ]; then
    printf 'SKIP  %-52s %s\n' "$slug" "($third)"
    continue
  fi
  if [ "$list" = 1 ]; then
    printf 'RUN   %-52s %s\n' "$slug" "$name"
    continue
  fi
  log="$tmp/step-$slug.log"
  start=$(date +%s)
  m=$step_minutes; [ "${mins:--}" != - ] && m=$mins
  if [ -n "$tmo" ]; then
    "$tmo" -k 30 "${m}m" bash --noprofile --norc "$third" < /dev/null > "$log" 2>&1
  else
    bash --noprofile --norc "$third" < /dev/null > "$log" 2>&1
  fi
  rc=$?
  secs=$(($(date +%s) - start))
  if [ "$rc" = 0 ]; then
    printf 'PASS  %-52s %5ss  %s\n' "$slug" "$secs" "$name"
  elif [ -n "$tmo" ] && { [ "$rc" = 124 ] || [ "$rc" = 137 ]; }; then
    fails=$((fails + 1))
    printf 'TIMEOUT %-50s %5ss  ended after %s min  %s\n' "$slug" "$secs" "$m" "$name"
    echo "      log: $log; its last lines:"
    tail -n 30 "$log" | sed 's/^/      | /'
  else
    fails=$((fails + 1))
    printf 'FAIL  %-52s %5ss  exit %s  %s\n' "$slug" "$secs" "$rc" "$name"
    echo "      log: $log; its last lines:"
    tail -n 30 "$log" | sed 's/^/      | /'
  fi
done < "$run_dir/plan.tsv"

# The check job's lavapipe step makes lavapipe-captures/ in the checkout; keep it beside the logs, not in your tree.
if [ "$had_captures" = 0 ] && [ -d "$repo/lavapipe-captures" ]; then
  mv "$repo/lavapipe-captures" "$run_dir/" && echo "lavapipe captures: $run_dir/lavapipe-captures"
fi

[ "$list" = 1 ] && exit 0
if [ "$fails" = 0 ]; then
  echo "ci_local: every step passed ($n in the plan; scripts in $run_dir)"
  exit 0
fi
echo "ci_local: $fails step(s) failed; logs at $tmp/step-<name>.log, scripts in $run_dir"
exit 1
