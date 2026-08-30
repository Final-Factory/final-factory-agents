# lib/config.sh — every knob ffgithubrunners has, in one place. SOURCED, never executed.
#
# Three layers, least specific first, exactly as ffbox does it:
#
#   1. the defaults below
#   2. ~/.config/ffbox/githubrunners/config.json, if it exists
#   3. FFGITHUBRUNNERS_* in the environment
#
# The env layer is last so a one-off can override a machine's config without editing it, which is
# how the acceptance measurements in section 14 of the design get run against a live install.
#
# JSON IS READ WITH python3, NOT jq. python3 is in every image and on every machine this runs on;
# jq is a package that may or may not be there, and a config layer that silently evaporates when
# a dependency is missing is worse than not having one. A malformed config.json is fatal here
# rather than ignored, for the same reason.
#
# Naming: short variable names in here, FFGITHUBRUNNERS_-prefixed in the environment. The prefix
# exists to keep the override visible in a unit file or a shell; it would only be noise inside
# the scripts.

# shellcheck shell=sh

# UNDER ~/.config/ffbox, not a directory of its own. ffwatch.py:134 states the rule: everything
# ffbox owns on a machine lives under ~/.config/ffbox, and a component gets a subdirectory there
# the way the Discord CLI has ~/.config/ffbox/discord. ffgithubrunners shares ffbox's two accounts,
# its daemon and its egress tooling, so it is a part of the same thing rather than a second product.
#
# ITS OWN secrets.env, THOUGH, AND NOT ffbox's. ffbox/systemd/ffweb.service reads
# ~/.config/ffbox/secrets.env as an EnvironmentFile and ffbox passes its own secrets into
# containers. A GitHub credential that can register org runners does not belong in a file with
# that blast radius, so it lives one level down where nothing of ffbox's reads it.
FFBOX_CONFIG_DIR=${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}
FFGHR_CONFIG_DIR=${FFGITHUBRUNNERS_CONFIG_DIR:-$FFBOX_CONFIG_DIR/githubrunners}
FFGHR_CONFIG=${FFGITHUBRUNNERS_CONFIG:-$FFGHR_CONFIG_DIR/config.json}
FFGHR_SECRETS=${FFGITHUBRUNNERS_SECRETS:-$FFGHR_CONFIG_DIR/secrets.env}

# Emit `_cfg_<key>=<value>` for every scalar in config.json, shell-quoted. Keys that are not
# plain identifiers are skipped rather than being allowed to inject an assignment; the file is
# ours, but eval'ing something derived from a file is worth being careful about regardless.
_ffghr_load_json() {
    [ -r "$FFGHR_CONFIG" ] || return 0
    _out=$(python3 - "$FFGHR_CONFIG" <<'PY'
import json, re, shlex, sys
try:
    with open(sys.argv[1]) as fh:
        cfg = json.load(fh)
except Exception as exc:
    sys.stderr.write("ffgithubrunners: %s: %s\n" % (sys.argv[1], exc))
    sys.exit(1)
if not isinstance(cfg, dict):
    sys.stderr.write("ffgithubrunners: %s: top level must be an object\n" % sys.argv[1])
    sys.exit(1)
for key, value in cfg.items():
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or key.startswith('_'):
        continue
    if isinstance(value, bool) or value is None:
        continue
    if isinstance(value, list):
        value = ','.join(str(v) for v in value)
    elif not isinstance(value, (str, int, float)):
        continue
    print("_cfg_%s=%s" % (key, shlex.quote(str(value))))
PY
    ) || {
        printf 'ffgithubrunners: could not read %s\n' "$FFGHR_CONFIG" >&2
        return 1
    }
    eval "$_out"
    unset _out
}
_ffghr_load_json || exit 1

# default_then_json_then_env VAR_NAME json_key default
# Assigns to VAR_NAME. The env name is always FFGITHUBRUNNERS_<json key, upper-cased>.
_ffghr_set() {
    _var=$1; _key=$2; _def=$3
    _envname="FFGITHUBRUNNERS_$(printf '%s' "$_key" | tr '[:lower:]' '[:upper:]')"
    eval "_env=\${$_envname:-}"
    eval "_json=\${_cfg_$_key:-}"
    if   [ -n "$_env" ];  then eval "$_var=\$_env"
    elif [ -n "$_json" ]; then eval "$_var=\$_json"
    else                       eval "$_var=\$_def"
    fi
    unset _var _key _def _envname _env _json
}

# --- what a slot is -------------------------------------------------------------------------
_ffghr_set SLOTS            slots            1
_ffghr_set WATCHDOG_MINUTES watchdog_minutes 120
# ONE NAME. ffbox and the runners are the same image built from ffbox/Dockerfile; a second tag
# was only ever another name for it, and two names meant two builds that drifted apart on every
# rebuild. Pin CI to a different build by overriding this key, not by keeping a second tag alive.
_ffghr_set IMAGE            image            ffbox:latest

# NO self-hosted, permanently. It was going to come back at cutover, but routing main.yml with
# `runs-on: ffgithubrunners` is better: that label is carried only by these runners and
# self-hosted only by the four legacy ones, so the two harnesses stay separable with no label
# surgery, and deploy.yml keeps landing on the old runners without being pinned by hand.
_ffghr_set LABELS           labels           'Linux,X64,ffgithubrunners'

# --- GitHub ---------------------------------------------------------------------------------
_ffghr_set ORG              org              Final-Factory
# Final-Factory is on the free plan, where Default is the only runner group and its id is 1.
_ffghr_set RUNNER_GROUP_ID  runner_group_id  1

# The App's two ids are NOT secrets: they identify an App, they do not authenticate as one. The
# private key is the secret, and it is a file. So the ids live in config.json with the rest of the
# configuration, and secrets.env holds only a PAT for the machines that use one.
_ffghr_set APP_ID              app_id              ''
_ffghr_set APP_INSTALLATION_ID app_installation_id ''
# Hardcoded rather than configured. 04-github.sh copies whatever key it is given to this path at
# 0600, so there is one place a key ever lives and nothing has to record where it went.
_ffghr_set APP_KEY             app_key             "$FFGHR_CONFIG_DIR/github-app.pem"

# --- the container --------------------------------------------------------------------------
_ffghr_set CONTAINER_USER   container_user   ffbox-container
_ffghr_set DOCKER_SOCK      docker_sock      /run/ffbox-container/docker.sock
_ffghr_set WORK_FOLDER      work_folder      /opt/actions-runner/_work
_ffghr_set WORKSPACE_SIZE   workspace_size   40g
# A ceiling, not an allocation: the workspace tmpfs plus about 32 GB for the editor. It exists
# for one failure, a job filling the workspace while Unity is resident on a host with 2 GB of
# swap. See section 12 of the design.
_ffghr_set MEMORY           memory           72g
# PROVISIONAL. Open item (b): this has never been measured against a real Unity import, and too
# low kills a legitimate job during asset import.
_ffghr_set PIDS_LIMIT       pids_limit       4096

# THE THREE CAPABILITIES --cap-drop=ALL TAKES THAT UNITY ACTUALLY NEEDS.
#
# Measured on 2026-08-29 by a real editmode run, which failed with
#   com.unity.jobs: TAR_ENTRY_ERROR: EPERM: operation not permitted, fchown
# after activating and resolving packages for 39 seconds. UPM extracts package tarballs as root
# and preserves the ownership recorded in them, which is a chown, then a chmod on the file it just
# gave away, then writes into directories it just gave away. That is CHOWN, then FOWNER, then
# DAC_OVERRIDE, and each was found by adding the previous one and hitting the next wall.
#
# game-ci never hit this because Docker's DEFAULT capability set includes all three; section 12's
# --cap-drop=ALL is what removed them.
#
# What stays dropped is the set that matters: SYS_ADMIN above all (the mount syscall, the kernel
# surface with no other mitigation), plus NET_RAW, MKNOD, SYS_PTRACE, SYS_MODULE and the rest.
# These three are filesystem-permission capabilities inside a container whose filesystem is
# already entirely the job's own, and none of them is a step toward leaving it.
_ffghr_set CAP_ADD          cap_add          'CHOWN,FOWNER,DAC_OVERRIDE'

# --- egress, per section 3 --------------------------------------------------------------------
# ffbox is on 10.80.0.0/24. These must not overlap it: both fences live in the same daemon.
_ffghr_set EGRESS_NET       egress_net       ffghr-net
_ffghr_set EGRESS_UPLINK    egress_uplink    ffghr-egress-net
_ffghr_set EGRESS_BRIDGE    egress_bridge    ffghr0
_ffghr_set EGRESS_SUBNET    egress_subnet    10.81.0.0/24
_ffghr_set EGRESS_IP        egress_ip        10.81.0.2
_ffghr_set EGRESS_NAME      egress_name      ffghr-egress
_ffghr_set EGRESS_IMAGE     egress_image     ffbox-egress:latest

# --- host paths -------------------------------------------------------------------------------
_ffghr_set LOG_DIR          log_dir          /var/log/ffgithubrunners
_ffghr_set DAEMON_ROOT      daemon_root      /opt/ffbox_container_docker
_ffghr_set DAEMON_QUOTA     daemon_quota     64G

# --- the workspace cache ------------------------------------------------------------------------
# design/ffcache_design.txt. One tar per branch under $CACHE_DIR/entries, mounted read-only into
# every job; a job writes a candidate into its own $CACHE_DIR/staging/slot-N and the SUPERVISOR
# decides whether that becomes an entry.
#
# AN EMPTY cache_dir DISABLES THE WHOLE FEATURE, and that is the point of it being a knob: it
# restores section 5 of the runner design exactly — no bind mounts, nothing a job writes reaching
# the next job. Every consumer gates on ffghr_cache_ready, so an unprovisioned machine runs jobs
# with no cache and no error rather than failing.
_ffghr_set CACHE_DIR        cache_dir        /opt/ffcache
_ffghr_set CACHE_KEEP       cache_keep       10
# Ten entries at ~16G, plus three slots staging up to 16G each while they run: 208G worst case.
# Not a round number picked for looking round.
_ffghr_set CACHE_QUOTA      cache_quota      250G

# sync=standard, NOT disabled, and the difference from the daemon store is deliberate.
#
# `sync` governs only how ZFS handles SYNCHRONOUS write requests — fsync, fdatasync, O_SYNC,
# O_DSYNC. Measured with strace on the actual save path: tar issues 1,684 write() calls and ZERO
# fsync/fdatasync/sync/syncfs/msync/sync_file_range, and the promote is a single renameat2. With
# nothing asking for durability there is nothing for the ZIL to commit, so standard and disabled
# do identical IO here and the safer default is free.
#
# The daemon store keeps sync=disabled because there the justification is real: docker build and
# docker pull ARE fsync-heavy, and on a mirror of spinning disks with no SLOG the ZIL dominates
# them. That reasoning does not transfer to one big sequential tar, and this dataset had the
# property only because it was copied from that block.
_ffghr_set CACHE_SYNC       cache_sync       standard

# HOW STALE AN ENTRY MAY GET BEFORE A JOB IS ASKED TO REPLACE IT.
#
# Saving is the expensive half and it does not scale: three slots each writing a ~22 GB archive at
# the end of their run put three concurrent sequential writes on one 5400 RPM mirror, measured at
# 98% utilisation with the disk as the bottleneck. Restoring is nearly free by comparison, because
# reads come out of ARC on a 755 GB box.
#
# One hour. The ceiling could be far higher on the evidence — section 12 measured a
# stale-but-present Library costing one re-imported asset and eighty seconds of recompile after
# THREE DAYS of drift — so this is deliberately conservative: it keeps entries close to current
# while still collapsing a burst of pushes into a single archive, which is what the disk cares
# about. Raise it if the save is still the thing that hurts.
_ffghr_set CACHE_MAX_AGE_HOURS cache_max_age_hours 1

# Host-only, never mounted into a container: which entry each slot has been granted, so two slots
# on the same branch cannot both be told to archive it.
FFGHR_CACHE_CLAIMS=${CACHE_DIR:+$CACHE_DIR/claims}

FFGHR_CACHE_ENTRIES=${CACHE_DIR:+$CACHE_DIR/entries}
FFGHR_CACHE_STAGING=${CACHE_DIR:+$CACHE_DIR/staging}
FFGHR_CACHE_LOCK=${CACHE_DIR:+$CACHE_DIR/.prune.lock}

ffghr_cache_ready() {
    [ -n "$CACHE_DIR" ] || return 1
    [ -d "$FFGHR_CACHE_ENTRIES" ] && [ -d "$FFGHR_CACHE_STAGING" ]
}

ffghr_cache_stage_dir() { printf '%s/slot-%s\n' "$FFGHR_CACHE_STAGING" "$1"; }

# THE ONE REGEX, AND IT IS THE WHOLE PATH-TRAVERSAL DEFENCE. A job proposes a name; this decides
# whether that string is a name at all. It lives here rather than being written out in slot.sh and
# reap.sh separately, because two copies of a security check is one copy too many.
#
#   <sanitized branch>@<scope>.tar
#
# The branch field cannot contain '@': main.yml sanitizes with s/[^a-zA-Z0-9._-]/-/g, so the split
# on the FIRST '@' is unambiguous. '--' would not do — feature/foo--bar keeps its dashes.
ffghr_cache_name_ok() {
    case "${1:-}" in
        ""|*..*|*/*|.*) return 1 ;;
    esac
    printf '%s' "$1" | grep -qE '^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+\.tar$'
}

ffghr_cache_branch_of() { printf '%s' "${1%%@*}"; }

# Run a cache mutation under the one lock in the system. Three slots can finish together and
# reap.sh can fire in the middle of it; the read path never takes this, because promotion is a
# rename and a reader cannot observe a partial entry.
ffghr_cache_with_lock() {
    [ -n "$FFGHR_CACHE_LOCK" ] || return 1
    (
        flock -w 120 9 || { printf 'ffcache: could not take %s within 120s\n' "$FFGHR_CACHE_LOCK" >&2; exit 1; }
        "$@"
    ) 9>>"$FFGHR_CACHE_LOCK"
}

# Bump an entry's LRU clock. The name came from a job, so it is validated exactly like a promotion
# candidate before anything is touched.
#
# THE CLOCK IS A SIDECAR FILE, NOT THE ARCHIVE'S OWN mtime, AND THAT IS NOT A REFINEMENT.
# An archive is written by the JOB, so on the host it is owned by uid 1020 with the container's
# 0644. `touch` on a file you do not own needs WRITE permission on it, and group is r--, so the
# supervisor gets EPERM: measured on the first real promotion,
#   touch: cannot touch '.../ffghr-smoke@6000.3.19f1.tar': Permission denied
# Nothing here can chown or chmod it either, both of which also require ownership. Every entry
# from now on is job-owned, so the LRU would silently degrade to "last WRITTEN" and a branch that
# restores without saving would age out despite being in daily use.
#
# The sidecar is created by the SUPERVISOR in a directory the supervisor owns, so it always works,
# and it says what it means: the archive's mtime is when it was built, the marker's is when it was
# last used.
# ffghr_cache_should_archive <entry name> <slot> -> 0 grant, 1 deny.
#
# Runs UNDER THE CACHE LOCK, so two slots that started together on the same branch cannot both be
# told to archive it. That is the whole point: the save is the expensive half and it does not
# scale, so exactly one job per entry per interval does it.
#
# A claim is what makes the grant survive the decision. Without one, the second slot would look at
# the same still-stale entry a second later and grant itself too — the entry only becomes fresh
# when the first job finishes, tens of minutes later.
ffghr_cache_should_archive() {
    _name=$1; _slot=$2
    _entry="$FFGHR_CACHE_ENTRIES/$_name"
    _claim="$FFGHR_CACHE_CLAIMS/$_name"
    _now=$(date +%s)
    _max=$(( ${CACHE_MAX_AGE_HOURS:-6} * 3600 ))
    mkdir -p "$FFGHR_CACHE_CLAIMS" 2>/dev/null || return 1

    # A claim older than the watchdog belongs to a job that is gone; teardown removes them, but a
    # supervisor killed with SIGKILL leaves one behind and nothing else would ever clear it.
    if [ -f "$_claim" ]; then
        _age=$(( _now - $(stat -c %Y "$_claim" 2>/dev/null || echo 0) ))
        if [ "$_age" -lt $(( ${WATCHDOG_MINUTES:-120} * 60 )) ]; then
            return 1
        fi
        rm -f "$_claim" 2>/dev/null || true
    fi

    if [ -f "$_entry" ]; then
        _eage=$(( _now - $(stat -c %Y "$_entry" 2>/dev/null || echo 0) ))
        [ "$_eage" -ge "$_max" ] || return 1
    fi

    printf 'slot=%s pid=%s at=%s\n' "$_slot" "$$" "$(date -Is)" > "$_claim" 2>/dev/null || return 1
    return 0
}

ffghr_cache_release_claim() {
    [ -n "${1:-}" ] && [ -n "$FFGHR_CACHE_CLAIMS" ] || return 0
    rm -f "$FFGHR_CACHE_CLAIMS/$1" 2>/dev/null || true
}

ffghr_cache_marker() { printf '%s.used\n' "$FFGHR_CACHE_ENTRIES/$1"; }

ffghr_cache_touch() {
    ffghr_cache_name_ok "${1:-}" || return 1
    [ -f "$FFGHR_CACHE_ENTRIES/$1" ] || return 1
    touch -- "$(ffghr_cache_marker "$1")"
}

# Keep the $CACHE_KEEP newest entries by mtime, delete the rest. Call under the lock.
# Prints one line per deletion so the caller can log what actually changed.
ffghr_cache_prune() {
    [ -d "$FFGHR_CACHE_ENTRIES" ] || return 0
    _keep=${CACHE_KEEP:-10}
    case "$_keep" in ''|*[!0-9]*) _keep=10 ;; esac
    # -maxdepth 1 so a directory somebody drops in here is never walked into. Newest first by
    # mtime, then everything past the keep count goes.
    # Ordered by the MARKER's mtime where there is one, falling back to the archive's own for an
    # entry nothing has restored since it was written. `rm` needs write on the DIRECTORY, not on
    # the file, so deleting a job-owned archive works where touching it does not.
    for _f in "$FFGHR_CACHE_ENTRIES"/*@*.tar; do
        [ -f "$_f" ] || continue
        _m="$_f.used"
        [ -f "$_m" ] || _m="$_f"
        printf '%s %s\n' "$(stat -c %Y "$_m" 2>/dev/null || echo 0)" "$_f"
    done | sort -rn | tail -n +$((_keep + 1)) | cut -d' ' -f2- \
        | while IFS= read -r _f; do
              [ -n "$_f" ] || continue
              rm -f -- "$_f" "$_f.used" && printf 'pruned %s\n' "$(basename -- "$_f")"
          done
    unset _f _m
    unset _keep
}

# Promote whatever one slot left in its staging directory. Call under the lock.
# $1 = staging directory. Prints what it did; returns 0 even when there was nothing to do, because
# a job that did not ask for a save is the normal case and not a failure.
ffghr_cache_promote() {
    _stage=${1:?ffghr_cache_promote needs a staging directory}
    [ -d "$_stage" ] || { unset _stage; return 0; }

    # The LRU bump first, so a job that restored and then failed before saving still counts as a
    # use. Unconditional and idempotent: a job that also saved simply touches its entry twice.
    if [ -f "$_stage/used" ]; then
        _used=$(head -c 256 "$_stage/used" 2>/dev/null | tr -d '\r\n')
        if ffghr_cache_touch "$_used"; then
            printf 'bumped %s\n' "$_used"
        else
            printf 'ignored an unusable used marker\n'
        fi
        unset _used
    fi

    [ -f "$_stage/ffcache.tar" ] && [ -f "$_stage/ffcache.name" ] || { unset _stage; return 0; }

    _name=$(head -c 256 "$_stage/ffcache.name" 2>/dev/null | tr -d '\r\n')
    if ! ffghr_cache_name_ok "$_name"; then
        printf 'REJECTED a proposed entry name\n'
        unset _stage _name
        return 0
    fi

    # Rule 2, one entry per branch, and it deletes across scopes on purpose: an editor upgrade
    # replaces a branch's entry rather than accumulating beside it.
    _branch=$(ffghr_cache_branch_of "$_name")
    for _old in "$FFGHR_CACHE_ENTRIES/$_branch"@*.tar; do
        [ -f "$_old" ] || continue
        [ "$(basename -- "$_old")" = "$_name" ] || printf 'replaced %s\n' "$(basename -- "$_old")"
        rm -f -- "$_old" "$_old.used"
    done

    # rename(2) within one dataset: atomic and instantaneous, which is what keeps every lock off
    # the read path.
    if mv -f -- "$_stage/ffcache.tar" "$FFGHR_CACHE_ENTRIES/$_name"; then
        touch -- "$(ffghr_cache_marker "$_name")"
        printf 'promoted %s (%s)\n' "$_name" "$(du -h "$FFGHR_CACHE_ENTRIES/$_name" 2>/dev/null | cut -f1)"
    else
        printf 'WARNING: could not promote %s\n' "$_name"
    fi
    unset _stage _name _branch _old
    return 0
}

# The flag files behind `drain` and `slot stop|start`, per section 11. slot.sh checks these
# before it mints a JIT config; nothing here talks to the system manager, which is why no
# account needs a sudoers entry.
FFGHR_DRAIN_FLAG=$FFGHR_CONFIG_DIR/drain
ffghr_slot_stop_flag() { printf '%s/slot-%s.stop\n' "$FFGHR_CONFIG_DIR" "$1"; }
ffghr_is_drained() {
    [ -e "$FFGHR_DRAIN_FLAG" ] && return 0
    [ -n "${1:-}" ] && [ -e "$(ffghr_slot_stop_flag "$1")" ] && return 0
    return 1
}

# Everything that speaks to docker in this system speaks to ffbox-container's daemon, and none of
# it should ever pick the caller's default socket up by accident.
DOCKER_HOST="unix://$DOCKER_SOCK"
export DOCKER_HOST

unset _cfg_slots _cfg_watchdog_minutes _cfg_image _cfg_labels _cfg_org 2>/dev/null || true
