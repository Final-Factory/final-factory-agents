#!/bin/sh
# discord-setup.sh — provision this machine for the ffbox Discord lanes.
#
#   sh ffbox/discord-setup.sh            provision (idempotent; safe to re-run)
#   sh ffbox/discord-setup.sh --check    report what is and is not in place, change nothing
#   sh ffbox/discord-setup.sh --no-units skip the systemd user units
#
# Everything here is re-runnable. It never overwrites a secrets file, never replaces an
# existing config value, and never starts a unit that is already running. Re-run it after
# moving this checkout: the ffwatch unit carries an absolute path that is rendered here.
#
# POSIX sh, like its siblings setup.sh and zfsSetup.sh — the documented invocation is
# `sh ffbox/discord-setup.sh`, and on Ubuntu that is dash, which has no `set -o pipefail`.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

STATE_DIR=${FFWATCH_STATE_DIR:-$HOME/ffbox-state}
FFDISCORD_HOME=${FFDISCORD_HOME:-$HOME/.config/ffdiscord}
FFBOX_CONFIG=$HOME/.config/ffbox
KILL_SWITCH=$FFBOX_CONFIG/discord.disabled
UNIT_DIR=$HOME/.config/systemd/user

CHECK=0
UNITS=1
for arg in "$@"; do
    case "$arg" in
        --check)    CHECK=1 ;;
        --no-units) UNITS=0 ;;
        -h|--help)  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)          echo "discord-setup.sh: unknown option $arg" >&2; exit 2 ;;
    esac
done

say()  { printf '[discord-setup] %s\n' "$*"; }
did()  { printf '[discord-setup]   %s\n' "$*"; }

if [ "$CHECK" = 1 ]; then
    say "state dir      : $STATE_DIR $([ -d "$STATE_DIR" ] && echo present || echo MISSING)"
    say "database       : $STATE_DIR/ffwatch.db $([ -f "$STATE_DIR/ffwatch.db" ] && echo present || echo MISSING)"
    say "ffdiscord home : $FFDISCORD_HOME $([ -d "$FFDISCORD_HOME" ] && echo present || echo MISSING)"
    say "config         : $FFDISCORD_HOME/config.json $([ -f "$FFDISCORD_HOME/config.json" ] && echo present || echo MISSING)"
    say "kill switch    : $KILL_SWITCH $([ -f "$KILL_SWITCH" ] && echo ACTIVE || echo 'not set (lanes may run)')"
    say "units          : $UNIT_DIR"
    for u in ffdiscord-listener.service ffwatch.service; do
        say "  $u $([ -f "$UNIT_DIR/$u" ] && echo installed || echo 'not installed')"
    done
    exit 0
fi

# --- state directory and schema ----------------------------------------------------------------
say "state"
mkdir -p "$STATE_DIR" "$STATE_DIR/blobs" "$STATE_DIR/conversations"
# `ffwatch init` is itself idempotent — every statement in the schema is IF NOT EXISTS — so this
# is the same call whether the database is new or five months old.
python3 "$HERE/ffwatch.py" --state-dir "$STATE_DIR" init
did "$STATE_DIR"

# --- ffdiscord config ---------------------------------------------------------------------------
# The ffwatch block lives inside the config the Discord CLI already uses, following 059's
# pattern: one machine-local file, 0600, outside the repo. Seeding it must not disturb the token
# or the channel ids that are already there, so the merge is key-by-key rather than a rewrite.
say "config"
mkdir -p "$FFDISCORD_HOME"
chmod 700 "$FFDISCORD_HOME" 2>/dev/null || true
CONFIG_PATH="$FFDISCORD_HOME/config.json" python3 - <<'PY'
import json
import os

path = os.environ["CONFIG_PATH"]
cfg = {}
if os.path.exists(path):
    with open(path, "r", encoding="utf-8") as fh:
        try:
            cfg = json.load(fh)
        except json.JSONDecodeError:
            raise SystemExit(f"{path} is not valid JSON; fix it before re-running")

block = cfg.setdefault("ffwatch", {})
seeded = []
for key, value in (
    # Left as "~/ffbox-state" unless overridden, so the config file stays portable between
    # machines with different home paths.
    ("state_dir", os.environ.get("FFWATCH_STATE_DIR", "~/ffbox-state")),
    ("base_ref", "develop"),
    ("agent_secs", 900),
    ("warmup_secs", 3600),
    ("kill_grace_secs", 10),
    ("max_concurrent_runs", 2),
    ("max_unity_runs", 1),
    ("catchup_secs", 900),
    ("rate_limits", {"answer": 200, "triage": 100, "fix": 3, "dev": 25}),
    ("watch", {
        "ask_claude": {"kind": "ask", "forum": False},
        "bug_reports": {"kind": "bug_report", "forum": True},
        "suggestions": {"kind": "suggestion", "forum": True},
    }),
):
    if key not in block:
        block[key] = value
        seeded.append(key)

cfg.setdefault("channels", {})
cfg.setdefault("mentions", {})

tmp = f"{path}.{os.getpid()}.tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, indent=2, sort_keys=True)
    fh.write("\n")
os.chmod(tmp, 0o600)
os.replace(tmp, path)
print("[discord-setup]   seeded ffwatch keys: " + (", ".join(seeded) or "(nothing new)"))
PY
did "$FFDISCORD_HOME/config.json"
if ! python3 -c "
import json,sys
cfg=json.load(open(sys.argv[1]))
sys.exit(0 if cfg.get('token') else 1)" "$FFDISCORD_HOME/config.json" 2>/dev/null; then
    did "NOTE: no bot token configured yet. Set one with:  ffdiscord set token <bot token>"
    did "      (or put FFDISCORD_TOKEN in $FFBOX_CONFIG/secrets.env — host side only)"
fi

# --- kill switch ---------------------------------------------------------------------------------
say "kill switch"
mkdir -p "$FFBOX_CONFIG"
chmod 700 "$FFBOX_CONFIG" 2>/dev/null || true
if [ -f "$KILL_SWITCH" ]; then
    did "ACTIVE: $KILL_SWITCH exists, so ffwatch will refuse to launch anything"
else
    did "create $KILL_SWITCH to stop ffwatch launching runs; delete it to resume"
fi
# Deliberately not created or removed here: the switch is an operator decision, and a setup
# script that clears it would re-arm the lanes behind someone's back.

# The secrets file belongs to ffbox/setup.sh and holds live tokens. Never touch it.
if [ -f "$FFBOX_CONFIG/secrets.env" ]; then
    did "secrets file present at $FFBOX_CONFIG/secrets.env (left untouched)"
else
    did "no secrets file yet — run 'sh ffbox/setup.sh' to install the template"
fi

# --- systemd user units --------------------------------------------------------------------------
say "units"
if [ "$UNITS" = 0 ]; then
    did "skipped (--no-units)"
elif ! command -v systemctl >/dev/null 2>&1 || ! systemctl --user show-environment >/dev/null 2>&1; then
    did "systemctl --user is unavailable here; run the two daemons yourself:"
    did "  ffdiscord-listener --channels ask_claude,bug_reports"
    did "  python3 $HERE/ffwatch.py run"
else
    mkdir -p "$UNIT_DIR"
    install -m 0644 "$HERE/systemd/ffdiscord-listener.service" \
        "$UNIT_DIR/ffdiscord-listener.service"
    # @FFWATCH@ is rendered rather than shipped resolved, because this repo can be cloned
    # anywhere and a wrong ExecStart fails at unit start with a message nobody reads.
    sed "s|@FFWATCH@|$HERE/ffwatch.py|g" "$HERE/systemd/ffwatch.service" \
        > "$UNIT_DIR/ffwatch.service"
    chmod 0644 "$UNIT_DIR/ffwatch.service"
    systemctl --user daemon-reload
    did "installed into $UNIT_DIR"
    did "enable with:  systemctl --user enable --now ffdiscord-listener ffwatch"
    did "logs:         journalctl --user -u ffwatch -f"
    did "REMINDER: exactly one ffdiscord-listener per bot, across all machines."
fi

say "done"
say "status:  python3 $HERE/ffwatch.py status"
say "one pass by hand (stop the unit first):  python3 $HERE/ffwatch.py --dry-run once"
