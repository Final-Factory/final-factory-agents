# lib/config.sh — every knob ffgithubrunners has, in one place. SOURCED, never executed.
#
# Three layers, least specific first, exactly as ffbox does it:
#
#   1. the defaults below
#   2. the "githubrunner" section of ~/.config/ffbox/config.json -- ONE file for the whole box
#      since 2026-09-01, when the runners' own config.json was folded into it.
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
# ONE CONFIG FILE FOR THE BOX, and this lane is a section in it rather than a file of its own.
# Until 2026-09-01 there were two: ~/.config/ffbox/config.json for ffwatch and ffweb, and this
# directory's config.json for the runners -- which meant two templates to keep in step with two
# sets of defaults, and they had already drifted (the runner template still named the image
# `ffghrunner:latest`, retired when both systems moved to one build).
#
# NO MIGRATION PATH, deliberately. There is one machine, and its config was moved by hand when
# this landed; code that reads a file nobody has is code nobody ever runs and nobody can test.
# A machine with no section gets the defaults below, which is the same answer a fresh install
# gets before 05-discord-setup.sh seeds it.
# THE SHARED CLOCK HELPERS COME FROM ffbox's OWN LIBRARY, because the deadline format is one
# format for both lanes and a second implementation of it here would be the thing that drifts.
# Sourced from here rather than left to each caller: slot.sh already loads both, but reap.sh,
# ffgithubrunners and test_pool.sh load only this file and still reach ffghr_mark_busy.
#
# Missing file is survivable the way it is in slot.sh -- warn once, no-op, carry on -- because a
# checkout without lib-workloads.sh is a broken checkout and not a reason to stop taking jobs.
# What is lost is the deadline IN the marker, and slot.sh's work_deadline then falls back to the
# container's own start, which is exactly the pre-2026-09-02 rule.
if ! command -v ffbox_clock_write >/dev/null 2>&1; then
    _ffghr_here=$(CDPATH= cd -- "$(dirname -- "${0:-.}")" && pwd 2>/dev/null) || _ffghr_here=.
    for _ffghr_wl in "$_ffghr_here/../lib-workloads.sh" "$_ffghr_here/../../lib-workloads.sh"                      "${FFGHR_LIB_WORKLOADS:-}"; do
        [ -n "$_ffghr_wl" ] && [ -r "$_ffghr_wl" ] || continue
        . "$_ffghr_wl"
        break
    done
    unset _ffghr_here _ffghr_wl
fi
if ! command -v ffbox_clock_write >/dev/null 2>&1; then
    echo "lib/config.sh: WARNING: lib-workloads.sh is missing; markers carry no deadline" >&2
    ffbox_clock_write() { printf 'staged_at=%s\n' "$(date -Is)" > "${1:?}" 2>/dev/null; }
fi

FFGHR_CONFIG=${FFGITHUBRUNNERS_CONFIG:-$FFBOX_CONFIG_DIR/config.json}
FFGHR_CONFIG_SECTION=${FFGITHUBRUNNERS_CONFIG_SECTION:-githubrunner}
FFGHR_SECRETS=${FFGITHUBRUNNERS_SECRETS:-$FFGHR_CONFIG_DIR/secrets.env}

# Emit `_cfg_<key>=<value>` for every scalar in config.json, shell-quoted. Keys that are not
# plain identifiers are skipped rather than being allowed to inject an assignment; the file is
# ours, but eval'ing something derived from a file is worth being careful about regardless.
_ffghr_load_json() {
    [ -r "$FFGHR_CONFIG" ] || return 0
    _out=$(python3 - "$FFGHR_CONFIG" "$FFGHR_CONFIG_SECTION" <<'PY'
import json, os, re, shlex, sys

path, section = sys.argv[1], sys.argv[2]

try:
    with open(path) as fh:
        cfg = json.load(fh)
except Exception as exc:
    sys.stderr.write("ffgithubrunners: %s: %s\n" % (path, exc))
    sys.exit(1)
if not isinstance(cfg, dict):
    sys.stderr.write("ffgithubrunners: %s: top level must be an object\n" % path)
    sys.exit(1)
sub = cfg.get(section)
if sub is None:
    # No section: a config that predates the seeding, or one an operator trimmed. The defaults in
    # this file are the answer, and they are the same ones a fresh install starts from.
    sub = {}
if not isinstance(sub, dict):
    sys.stderr.write('ffgithubrunners: %s: "%s" must be an object\n' % (path, section))
    sys.exit(1)
# THE POOL'S TWO NUMBERS, in a "pool" object so this lane and the agent lane describe themselves
# the same way: `idle` is how many runners wait registered while nothing is happening, `max` is
# this lane's ceiling -- the most jobs that can run at once, under the box-wide
# max_concurrent_runs. Mapped onto the flat names the rest of this file uses, so nothing
# downstream has to know the shape changed.
pool = sub.get("pool")
if isinstance(pool, dict):
    if "idle" in pool:
        sub["idle_pool"] = pool["idle"]
    if "max" in pool:
        sub["slots"] = pool["max"]

for key, value in sub.items():
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
#
# TWO NUMBERS, AND THEY MEAN DIFFERENT THINGS. `slots` is the CEILING: how many supervisors run,
# and so the most jobs that can ever be in flight at once. `idle_pool` is the STANDING COST: how
# many runners are registered and waiting for work while nothing is happening.
#
# A supervisor whose turn has not come holds NOTHING — no container, no registration, nothing on
# the org page — and costs a sleeping shell. It starts a runner only when the pool is short of
# idle ones and there is room under the ceiling. See the pool section at the end of this file.
#
# idle_pool 1 with slots 1 is exactly the old behaviour, which is why both default to 1.
FFGHR_DEFAULT_SLOTS=1
FFGHR_DEFAULT_IDLE_POOL=1
_ffghr_set SLOTS            slots            "$FFGHR_DEFAULT_SLOTS"
_ffghr_set IDLE_POOL        idle_pool        "$FFGHR_DEFAULT_IDLE_POOL"
# TWO CLOCKS, AND THEY MEASURE FROM DIFFERENT MOMENTS.
#
# WATCHDOG_MINUTES bounds a JOB, from the moment that job started. 120 because main.yml's own
# timeout-minutes is 90, so a job GitHub still wants is never killed locally. Until 2026-09-02 it
# was measured from container launch instead, which meant a job landing on a runner that had been
# registered and waiting for 118 minutes had two minutes to finish; design/ffbox_clocks_design.txt
# section 4 has the whole account.
#
# IDLE_MINUTES bounds a REGISTERED RUNNER WITH NO JOB, from mint. It is a staleness-versus-churn
# trade rather than a safety bound, and what it is really for is the image: ffbox:latest is
# rebuilt within five minutes of a push and a running container keeps whatever it started with.
# On a busy repository the updater's drain gets there first and this rarely fires; on a quiet week
# it is the only thing that recycles a runner onto a rebuilt image, which is also what keeps the
# Actions runner version new enough for GitHub to keep handing it jobs.
#
# THEY DEFAULT TO THE SAME NUMBER AND THAT IS NOT A COINCIDENCE WORTH KEEPING. 120 is what the
# single clock effectively enforced, so a box that upgrades and changes nothing sees the idle
# recycling it always saw and only the job runway changes. Lowering IDLE_MINUTES below
# WATCHDOG_MINUTES is defensible and is open item (c) in the design -- but it is what makes the
# `Runner.Worker` inference load-bearing for whether a job survives, so read section 10 first.
_ffghr_set WATCHDOG_MINUTES watchdog_minutes 120
_ffghr_set IDLE_MINUTES     idle_minutes     120
# 0 IS "NEVER RECYCLE AN IDLE RUNNER", not "expire it immediately", the same coercion both pools
# apply to a pool.idle of 0: no places is a thing somebody may mean and no time is not. Negative
# is 0. And a value small enough to churn JIT registrations against GitHub's API is refused here
# rather than honoured, because the mistake is silent and the API is somebody else's.
FFGHR_MIN_IDLE_MINUTES=5
case "$IDLE_MINUTES" in
    ''|*[!0-9-]*) IDLE_MINUTES=120 ;;
esac
[ "$IDLE_MINUTES" -ge 0 ] 2>/dev/null || IDLE_MINUTES=0
if [ "$IDLE_MINUTES" -gt 0 ] && [ "$IDLE_MINUTES" -lt "$FFGHR_MIN_IDLE_MINUTES" ]; then
    echo "lib/config.sh: idle_minutes $IDLE_MINUTES is below the floor of" \
         "$FFGHR_MIN_IDLE_MINUTES; using the floor" >&2
    IDLE_MINUTES=$FFGHR_MIN_IDLE_MINUTES
fi
# ONE NAME. ffbox and the runners are the same image built from ffbox/Dockerfile; a second tag
# was only ever another name for it, and two names meant two builds that drifted apart on every
# rebuild. Pin CI to a different build by overriding this key, not by keeping a second tag alive.
_ffghr_set IMAGE            image            ffbox:latest

# NO self-hosted, permanently. It was going to come back at cutover, but routing main.yml with
# `runs-on: ffgithubrunners` is better: that label is carried only by these runners, so the two
# harnesses stay separable with no label surgery.
#
# NOTHING IN THE GAME REPO ASKS FOR self-hosted ANY MORE. deploy.yml was the last workflow that did
# and it was deleted on 2026-09-01, so the four legacy runners now serve nothing and adding the
# label back here would only widen what can land on these containers.
_ffghr_set LABELS           labels           'Linux,X64,ffgithubrunners'

# --- GitHub ---------------------------------------------------------------------------------
_ffghr_set ORG              org              Final-Factory
# Final-Factory is on the free plan, where Default is the only runner group and its id is 1.
_ffghr_set RUNNER_GROUP_ID  runner_group_id  1

# WHICH REPOSITORIES THIS HOST WILL UPLOAD AN ARTIFACT FOR, by numeric repository_id.
#
# A job hands the supervisor its Actions runtime credential and a zip, and the supervisor performs
# the upload -- which is what lets productionresultssa*.blob.core.windows.net come off the egress
# allowlist, an entry whose regex admitted eleven unregistered Azure account names anyone could
# claim. lib/artifact-upload.py reads repository_id out of the TOKEN and refuses anything not
# listed here, so a credential minted for someone else's repository cannot be aimed at this path.
#
# THE ID AND NOT THE NAME, deliberately: it is stable across a rename, and it is what the claim
# carries. Final-Factory/FinalFactory is 623631450, measured from a live job on 2026-09-02.
#
# EMPTY MEANS UPLOAD NOTHING. Fail closed: a host with no list configured refuses rather than
# uploading wherever it is pointed.
_ffghr_set ARTIFACT_REPO_IDS artifact_repository_ids ''

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
# THE SHARED SETTING, so a box holds one answer to "how big may a workspace get" rather than two
# that drift. It lives in the "container" section of config.json -- things true of a container
# whichever lane started it -- and ffbox reads the same section for the same key. A workspace_size
# inside the "githubrunner" section still overrides it, for a machine that genuinely wants CI on a
# different ceiling from the agent; nothing seeds one, because wanting that is unusual.
_ffghr_shared_cfg() {
    _sc=${FFBOX_CONFIG_JSON:-${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}/config.json}
    [ -r "$_sc" ] || return 0
    python3 -c '
import json, sys
try:
    v = (json.load(open(sys.argv[1])).get("container") or {}).get(sys.argv[2])
except Exception:
    sys.exit(0)
if v is not None and not isinstance(v, (dict, list)):
    print(v)
' "$_sc" "$1" 2>/dev/null
}
_ffghr_ws_default=$(_ffghr_shared_cfg workspace_size)
[ -n "$_ffghr_ws_default" ] || _ffghr_ws_default=40g
_ffghr_set WORKSPACE_SIZE   workspace_size   "$_ffghr_ws_default"
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

# --- the Unity machine id -----------------------------------------------------------------------
#
# WHAT UNITY'S LICENSING SERVICE THINKS THIS MACHINE IS, and the reason two Unity jobs could not
# run at once. game-ci's base image PINS /etc/machine-id to one constant for every container it
# ever builds:
#
#   images/ubuntu/base/Dockerfile:73
#     # Support forward compatibility for unity activation
#     RUN echo "576562626572264761624c65526f7578" > /etc/machine-id && ... /var/lib/dbus/machine-id
#
# (that hex is "Webber&GabLeRoux"). A .ulf licence file is bound to a machine, so pinning the id is
# what lets one downloaded licence keep working in every container. Their ACTION then undoes it for
# a personal SERIAL activation, which is bound per machine rather than per file —
# unity-test-runner v4, dist/platforms/ubuntu/entrypoint.sh:3-7, identical in unity-builder:
#
#     # Ensure machine ID is randomized for personal license activation
#     if [[ "$UNITY_SERIAL" = F* ]]; then
#       dbus-uuidgen > /etc/machine-id && ... ln -sf /etc/machine-id /var/lib/dbus/machine-id
#     fi
#
# main.yml no longer runs that action — it sources unity-license.sh directly — so nothing was
# doing this any more, every container presented as the same machine, and the second concurrent
# activation got "Found 0 entitlement groups and 0 free entitlements" and exit 198. Design open
# item (e).
#
# PER SLOT, NOT PER CONTAINER, and that is a deliberate improvement on game-ci's line. An
# activation registers a machine with Unity and only -returnlicense gives it back, so a job that
# is SIGKILLed leaks one. With a fresh random id per container every leak is permanent, because
# that machine never comes back. With an id derived from the slot, the licence sees at most $SLOTS
# machines ever, and the next job on that slot presents the same one and reuses its entitlement —
# which is exactly why sequential jobs work today on the pinned id despite leaks.
#
# SUPERSEDED 2026-09-01, AND THE DEFAULT IS NOW image. Everything above is about ONLINE activation,
# which neither lane does any more: the licence is a .ulf FILE mounted into the container
# (ffbox/unity-offline-license.sh) and resolved from local files with no call to Unity. Exit 198 was
# the activation endpoint refusing a concurrent registration, so with no call there is nothing to
# refuse and no reason to vary the id.
#
# IT WOULD NOW BREAK THE LICENCE RATHER THAN PROTECT IT. A .ulf binds to exactly one
# /etc/machine-id, so a container presenting a per-slot id matches nothing and finds no entitlement.
#
#   <32 hex>   the default, and it is OUR constant (46696e616c466163746f72792d666662, ASCII
#              "FinalFactory-ffb") rather than the image's: ffbox/unity-offline-license.sh mints the
#              licence against exactly this value, so it does not depend on a number game-ci owns.
#              KEEP IN LOCKSTEP with FFBOX_MACHINE_ID_CONST there and with ffbox/lib-workloads.sh.
#   image      leave the image's baked-in constant alone.
#   per-slot   sha256 of the host name and the slot, first 32 hex. The old default; correct only
#              for a lane that has gone back to online activation.
_ffghr_set MACHINE_ID       machine_id       46696e616c466163746f72792d666662

# Prints the id for a slot, or returns 1 when nothing should be overridden. The container's
# entrypoint validates this again before it writes anything: it is the thing that runs as root.
ffghr_machine_id() {
    _slot=${1:?ffghr_machine_id needs a slot}
    case "$MACHINE_ID" in
        ''|image|none)
            return 1 ;;
        per-slot)
            _mhost=$(hostname -s 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo host)
            printf 'ffghr-%s-slot-%s' "$_mhost" "$_slot" | sha256sum | cut -c1-32
            unset _mhost ;;
        *)
            # An id that is not 32 hex characters is not a machine id, and systemd, dbus and Unity
            # disagree about which of them says so. Refuse it here instead.
            if printf '%s' "$MACHINE_ID" | grep -qE '^[0-9a-f]{32}$'; then
                printf '%s\n' "$MACHINE_ID"
            else
                printf 'ffgithubrunners: machine_id must be per-slot, image, or 32 hex characters\n' >&2
                return 1
            fi ;;
    esac
}

# --- the Unity licence ----------------------------------------------------------------------------
#
# ONE FILE, SHARED WITH ffbox's OWN LANE, and that is the point rather than an economy: both lanes
# run containers built from the same image presenting the same /etc/machine-id, so one .ulf is
# valid in both. ffbox/unity-offline-license.sh mints and installs it; slot.sh mounts it read-only.
#
# A CI JOB'S UNITY SECRETS STILL ARRIVE FROM THE WORKFLOW, out of repository secrets, because
# main.yml names them in its env: block and changing a workflow file needs a token scope this box
# deliberately lacks. unity-license.sh prefers the mounted file, so those secrets go unused the
# moment this exists -- but they are still handed to the job, and only editing main.yml stops that.
# /opt/ffcache, NOT $FFBOX_CONFIG_DIR: the rootless daemon runs as ffbox-container and cannot
# traverse a mode-700 home, so a licence under ~/.config fails the MOUNT and the container never
# starts. See the long note in ffbox/unity-offline-license.sh.
FFGHR_UNITY_ULF=${FFGHR_UNITY_ULF:-/opt/ffcache/unity/Unity_lic.ulf}

# --- egress, per section 3 --------------------------------------------------------------------
# ffbox is on 10.80.0.0/24. These must not overlap it: both fences live in the same daemon.
# THE LOCAL GIT MIRROR. Where a job fetches the repository instead of github.com. MIRROR_URL is a
# git:// address on ffghr-net because that network is --internal: under the rootless daemon the real
# host is not reachable from it at all, so the mirror has to be a container like the proxy is.
#
# IT IS THE GIT SOURCE, not a copy of golden. It fetches GitHub directly with the App token and
# keeps its own LFS objects under <repo>/lfs/objects, so nothing here reads /opt/FinalFactory --
# which is what lets the ZFS snapshot and golden be retired rather than merely bypassed.
_ffghr_set MIRROR_DIR       mirror_dir       /opt/ffcache/mirror
_ffghr_set MIRROR_REPO      mirror_repo      FinalFactory.git
_ffghr_set MIRROR_IP        mirror_ip        10.81.0.250
_ffghr_set MIRROR_NAME      mirror_name      ffghr-gitmirror
_ffghr_set MIRROR_IMAGE     mirror_image     ffghr-gitmirror:latest
_ffghr_set MIRROR_URL       mirror_url       git://10.81.0.250/FinalFactory.git
_ffghr_set MIRROR_ORIGIN    mirror_origin    https://github.com/Final-Factory/FinalFactory
_ffghr_set MIRROR_SLUG      mirror_slug      FinalFactory
_ffghr_set MIRROR_LFS_DIR   mirror_lfs_dir   /opt/ffcache/mirror/FinalFactory.git/lfs/objects
_ffghr_set MIRROR_LFS_URL   mirror_lfs_url   http://10.81.0.250:8080/FinalFactory.git/info/lfs

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
# Four hours. The ceiling could be higher still on the evidence — section 12 measured a
# stale-but-present Library costing one re-imported asset and eighty seconds of recompile after
# THREE DAYS of drift — so this remains conservative: entries stay close enough to current that a
# restore is cheap, while a busy afternoon of pushes collapses into one archive per entry rather
# than one per hour, which is what the disk cares about. Raise it if the save still hurts.
_ffghr_set CACHE_MAX_AGE_HOURS cache_max_age_hours 4

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
    _max=$(( ${CACHE_MAX_AGE_HOURS:-4} * 3600 ))
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

# --- the pool -----------------------------------------------------------------------------------
#
# $SLOTS supervisors run all the time, but a CONTAINER only exists while the pool needs one:
# $IDLE_POOL runners registered and waiting, plus one per job in flight, never more than $SLOTS
# altogether. A supervisor with no container is not an idle runner — it holds no registration and
# GitHub has never heard of it — so the standing cost of the harness is idle_pool, not slots.
#
# ADMISSION IS DECIDED HERE AND NOWHERE ELSE, UNDER ONE LOCK, because the decision reads a count
# that acting on the decision then changes. Two supervisors that both saw "no idle runner" a
# millisecond apart would both mint one, and the pool would overshoot by exactly as many slots as
# happened to be waiting.
FFGHR_POOL_LOCK=$FFGHR_CONFIG_DIR/.pool.lock
FFGHR_STATE_DIR=$FFGHR_CONFIG_DIR/state

# HOW OFTEN A WAITING SUPERVISOR LOOKS, and how often a supervisor with an IDLE container checks
# whether its runner has taken a job. Both are on the path between "a job was queued" and "a
# replacement runner is listening", so this is CI latency, not housekeeping: five seconds each
# means a second concurrent job waits about ten. Once a container is busy the poll drops back to
# fifteen, because from then on the loop is only waiting for a job that takes minutes.
_ffghr_set POOL_POLL_SECONDS pool_poll_seconds 5

# A container that has taken a job. WRITTEN BY THE SUPERVISOR THAT OWNS IT — it is already awake
# watching that container — and read by every supervisor waiting for a place.
#
# THE MARKER IS ONLY EVER TRUSTED FOR A CONTAINER THAT IS STILL RUNNING, which is what makes a
# stale one harmless in both directions. A supervisor SIGKILLed before its job started leaves no
# marker, and its container is counted idle, which it is. One SIGKILLed during a job leaves a
# marker that stays true until the container exits, at which point no count includes it any more.
# reap.sh sweeps the leftovers.
ffghr_busy_marker() { printf '%s/%s.busy\n' "$FFGHR_STATE_DIR" "${1:?}"; }

# AND THE IDLE ONE, written at mint. Same directory, same sweeping rule in reap.sh, same two-key
# format: what differs is only which question the deadline in it answers.
ffghr_idle_marker() { printf '%s/%s.idle\n' "$FFGHR_STATE_DIR" "${1:?}"; }

# THE MARKER IS ALSO THE JOB'S DEADLINE, which is why it is written in lib-workloads.sh's clock
# format rather than the bare `at=` it carried until 2026-09-02. The moment a job starts was
# already being recorded here for the pool's own accounting; the work clock needs no state of its
# own, only this file read back. A supervisor restarted mid-job therefore recovers the same
# deadline its predecessor had, instead of granting a fresh 120 minutes on every restart.
#
# Nothing ever read the old `at=` key except this function, so the rename breaks no consumer; a
# marker left by an older supervisor simply has no deadline in it, and slot.sh's work_deadline
# falls back to the container's own start, which is exactly the pre-2026-09-02 rule.
ffghr_mark_busy() {
    mkdir -p "$FFGHR_STATE_DIR" 2>/dev/null || return 1
    ffbox_clock_write "$(ffghr_busy_marker "${1:?}")" "$(( ${WATCHDOG_MINUTES:-120} * 60 ))"
}

ffghr_mark_idle() {
    mkdir -p "$FFGHR_STATE_DIR" 2>/dev/null || return 1
    ffbox_clock_write "$(ffghr_idle_marker "${1:?}")" "$(( ${IDLE_MINUTES:-120} * 60 ))"
}

ffghr_clear_idle() {
    [ -n "${1:-}" ] || return 0
    rm -f "$(ffghr_idle_marker "$1")" 2>/dev/null || true
}

ffghr_clear_busy() {
    [ -n "${1:-}" ] || return 0
    rm -f "$(ffghr_busy_marker "$1")" 2>/dev/null || true
}

# Is this container RUNNING A JOB? This is what writes the marker, so it cannot read it.
#
# The listener spawns Runner.Worker for the job it accepted and nothing else in the container is
# called that, so its presence is the job. `-o pid,comm` rather than the default format is not
# cosmetic: the default prints full argv, and the listener's argv carries the JIT config.
ffghr_container_busy() {
    docker top "${1:?}" -o pid,comm 2>/dev/null | grep -q 'Runner\.Worker'
}

# Live job containers, by LABEL. The fence is ffghr-* too and ffbox shares this daemon, so a name
# prefix is the wrong filter; ffghr.slot is set by slot.sh on the containers this counts.
ffghr_pool_containers() {
    docker ps --filter label=ffghr.slot --format '{{.Names}}' 2>/dev/null || true
}

# "<total> <idle>" over those containers.
ffghr_pool_counts() {
    _total=0; _idle=0
    for _c in $(ffghr_pool_containers); do
        _total=$((_total + 1))
        [ -e "$(ffghr_busy_marker "$_c")" ] || _idle=$((_idle + 1))
    done
    printf '%s %s\n' "$_total" "$_idle"
    unset _c _total _idle
}

# May a slot start a runner right now? CALL WITH THE POOL LOCK HELD.
#
# The two conditions are the whole feature: room under the ceiling, and a pool that is short of
# idle runners. A job in flight makes the pool short by one, which is what starts the next runner.
ffghr_pool_admit() {
    _counts=$(ffghr_pool_counts)
    _ptotal=${_counts% *}
    _pidle=${_counts#* }
    [ "$_ptotal" -lt "$SLOTS" ] && [ "$_pidle" -lt "$IDLE_POOL" ]
}

# A number, or the default. Everything here is arithmetic under `set -e`, where a config that says
# "six" is not a wrong answer but a dead supervisor.
_ffghr_num() {
    eval "_nv=\${$1:-}"
    case "$_nv" in
        ''|*[!0-9]*) eval "$1=\$2" ;;
        *) [ "$_nv" -ge 1 ] || eval "$1=\$2" ;;
    esac
    unset _nv
}
_ffghr_num POOL_POLL_SECONDS 5

# The box-wide ceiling, from the TOP level of the shared config -- not from the "container"
# section _ffghr_shared_cfg reads, and not from this lane's own section. It is the one number both
# lanes count against, so it belongs to neither of them.
_ffghr_box_cfg() {
    _bc=${FFBOX_CONFIG_JSON:-${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}/config.json}
    [ -r "$_bc" ] || return 0
    python3 -c '
import json, sys
try:
    v = json.load(open(sys.argv[1])).get(sys.argv[2])
except Exception:
    sys.exit(0)
if v is not None and not isinstance(v, (dict, list)):
    print(v)
' "$_bc" "$1" 2>/dev/null
}

# THE TWO POOL NUMBERS, COERCED THE SAME WAY THE AGENT LANE COERCES ITS OWN, because a box that
# holds one answer should not need two rules for reading it:
#
#   idle < 0   ->  0. Off. Not a negative number of registered runners.
#   max  < 0   ->  max_concurrent_runs, the box ceiling. "No ceiling of my own", so this lane may
#                  use the whole box when the other one is quiet.
#
# NOT _ffghr_num's rule, which sends anything below 1 to the DEFAULT -- under that, a -1 meaning
# "defer to the box" would silently become 1 and CI would run one job at a time while the config
# said otherwise. Non-numeric still falls back to the default: a config that says "three" must
# not take a supervisor down.
_ffghr_coerce_pool() {
    case "${SLOTS:-}" in
        ''|*[!0-9-]*) SLOTS=$FFGHR_DEFAULT_SLOTS ;;
        -*) SLOTS=$(_ffghr_box_cfg max_concurrent_runs)
            case "$SLOTS" in ''|*[!0-9]*) SLOTS=$FFGHR_DEFAULT_SLOTS ;; esac ;;
    esac
    # ZERO IS LEFT ALONE, on both lanes, and it means what it says: no places, so this lane
    # takes nothing. Sending it to the default instead would be the same silent override that
    # makes a -1 unreadable, and `drain` is the flag for pausing, not a number nobody meant.
    [ "$SLOTS" -ge 0 ] 2>/dev/null || SLOTS=$FFGHR_DEFAULT_SLOTS
    case "${IDLE_POOL:-}" in
        ''|*[!0-9-]*) IDLE_POOL=$FFGHR_DEFAULT_IDLE_POOL ;;
        -*) IDLE_POOL=0 ;;
    esac
    [ "$IDLE_POOL" -ge 0 ] 2>/dev/null || IDLE_POOL=0
}
_ffghr_coerce_pool

# Re-read the two pool knobs. A waiting supervisor sits in its loop for as long as the machine is
# quiet — hours — and an operator who raises idle_pool should not have to restart units for it to
# take effect. Environment overrides still win, because _ffghr_set applies them last.
#
# A config.json that has gone unreadable leaves the current values alone rather than killing the
# supervisor: `ffgithubrunners idle N` writes through a temporary file and renames, so the only
# way to see a half-written one is to edit it by hand while a slot is waiting.
ffghr_reload_limits() {
    # A key DELETED from config.json since the last load would otherwise keep its old value:
    # _ffghr_load_json only ever assigns _cfg_*, it never clears one that has gone away.
    unset _cfg_slots _cfg_idle_pool 2>/dev/null || true
    _ffghr_load_json 2>/dev/null || return 0
    _ffghr_set SLOTS     slots     "$FFGHR_DEFAULT_SLOTS"
    _ffghr_set IDLE_POOL idle_pool "$FFGHR_DEFAULT_IDLE_POOL"
    _ffghr_coerce_pool
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

unset _cfg_slots _cfg_idle_pool _cfg_watchdog_minutes _cfg_image _cfg_labels _cfg_org 2>/dev/null || true
