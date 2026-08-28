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
_ffghr_set IMAGE            image            ffghrunner:latest

# The design's default set. Section 13 step 1 installs WITHOUT self-hosted so nothing routes here
# by accident while the old runners are still serving main.yml, which is why config.json.example
# ships the shorter list; step 3 is where self-hosted comes back.
_ffghr_set LABELS           labels           'self-hosted,Linux,X64,ffgithubrunners'

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
