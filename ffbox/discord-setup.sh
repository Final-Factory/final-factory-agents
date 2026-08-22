#!/bin/sh
# discord-setup.sh — provision this machine for the ffbox Discord lanes.
#
#   sh ffbox/discord-setup.sh            provision (idempotent; safe to re-run)
#   sh ffbox/discord-setup.sh --check    report what is and is not in place, change nothing
#   sh ffbox/discord-setup.sh --no-units skip the systemd units
#
# Everything here is re-runnable. It never overwrites a secrets file, never replaces an
# existing config value, and never starts a unit that is already running. Re-run it after
# moving this checkout: the ffwatch unit carries an absolute path that is rendered here.
#
# POSIX sh, like its siblings setup.sh and zfsSetup.sh — the documented invocation is
# `sh ffbox/discord-setup.sh`, and on Ubuntu that is dash, which has no `set -o pipefail`.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# A trailing slash on $HOME turns every path below into //-doubled noise, and those paths get
# baked into unit files a human has to read.
HOME=${HOME%/}

STATE_DIR=${FFWATCH_STATE_DIR:-$HOME/ffbox-state}
FFDISCORD_HOME=${FFDISCORD_HOME:-$HOME/.config/ffdiscord}
FFBOX_CONFIG=$HOME/.config/ffbox
KILL_SWITCH=$FFBOX_CONFIG/discord.disabled
# SYSTEM units, not user units. A build server reboots with nobody logged in, and a user unit
# only runs while its user has a session unless `loginctl enable-linger` was remembered. These
# run as $RUN_USER instead, which is the same identity that owns the docker group membership,
# the NOPASSWD zfs rules and the Claude credential.
UNIT_DIR=/etc/systemd/system
RUN_USER=$(id -un)
RUN_GROUP=$(id -gn)

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
    say "units          : $UNIT_DIR  (rendered copies in $FFBOX_CONFIG/systemd)"
    STALE=0
    for u in ffbox.target ffdiscord-listener.service ffwatch.service ffweb.service; do
        st=$([ -f "$UNIT_DIR/$u" ] && echo installed || echo 'NOT INSTALLED')
        if command -v systemctl >/dev/null 2>&1 && [ -f "$UNIT_DIR/$u" ]; then
            # head -1: is-enabled can print a hint line under its verdict, and a newline in
            # the middle of a status line makes the report unreadable.
            st="$st, $(systemctl is-enabled "$u" 2>/dev/null | head -1 || echo unknown)"
            st="$st, $(systemctl is-active "$u" 2>/dev/null | head -1 || echo inactive)"
        fi
        # Re-running this script re-renders the staging copies but cannot write /etc, so an
        # installed unit can silently lag behind a config change. Say so rather than leaving a
        # trap: the symptom otherwise is a listener that keeps watching yesterday's channels.
        if [ -f "$UNIT_DIR/$u" ] && [ -f "$FFBOX_CONFIG/systemd/$u" ] \
           && ! cmp -s "$UNIT_DIR/$u" "$FFBOX_CONFIG/systemd/$u"; then
            st="$st, STALE (differs from the rendered copy)"
            STALE=1
        fi
        say "  $u $st"
    done
    if [ "$STALE" = 1 ]; then
        say "re-install the stale units with:"
        say "  sudo install -m 0644 $FFBOX_CONFIG/systemd/ffbox.target \
$FFBOX_CONFIG/systemd/*.service $UNIT_DIR/ && sudo systemctl daemon-reload"
        say "  sudo systemctl restart ffbox.target"
    fi
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
    # The sender. approve_before_send holds every reply at 'pending' until
    # `ffwatch approve <id>` releases it — turn it on for the first days on a live server.
    ("approve_before_send", False),
    ("send_limits", {"per_hour": 60, "per_conversation_hour": 12}),
    ("max_send_attempts", 5),
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

# --- systemd units -------------------------------------------------------------------------------
# One handle for the operator: `sudo systemctl enable --now ffbox.target` brings up the doorbell
# listener, the conversation manager and the web UI, now and on every boot. The services carry
# PartOf=ffbox.target, so stopping the target stops all three.
say "units"

# The listener watches whatever the config says to watch. Reading it back from the ffwatch block
# means adding a channel there and re-running this script is enough — no second place to edit,
# and no unit quietly watching a channel the classifier no longer knows about.
CHANNELS=$(CONFIG_PATH="$FFDISCORD_HOME/config.json" python3 - <<'PY'
import json, os
try:
    cfg = json.load(open(os.environ["CONFIG_PATH"], encoding="utf-8"))
except Exception:
    cfg = {}
watch = ((cfg.get("ffwatch") or {}).get("watch") or {})
print(",".join(sorted(watch)) or "ask_claude,bug_reports")
PY
)
did "listener will watch: $CHANNELS"

if [ "$UNITS" = 0 ]; then
    did "skipped (--no-units)"
elif ! command -v systemctl >/dev/null 2>&1; then
    did "no systemctl here; run the daemons yourself:"
    did "  ffdiscord-listener --channels $CHANNELS"
    did "  python3 $HERE/ffwatch.py run"
    did "  python3 $HERE/ffweb.py"
else
    # The templates in ffbox/systemd/ are what git carries; the rendered copies land HERE, in a
    # stable place the operator can install from. @PLACEHOLDERS@ are rendered rather than
    # shipped resolved because this repo can be cloned anywhere and a wrong ExecStart fails at
    # unit start with a message nobody reads. Rendering never needs root — only installing does.
    STAGE=$FFBOX_CONFIG/systemd
    mkdir -p "$STAGE"
    for u in ffbox.target ffdiscord-listener.service ffwatch.service ffweb.service; do
        sed -e "s|@FFWATCH@|$HERE/ffwatch.py|g" \
            -e "s|@FFWEB@|$HERE/ffweb.py|g" \
            -e "s|@USER@|$RUN_USER|g" \
            -e "s|@GROUP@|$RUN_GROUP|g" \
            -e "s|@HOME@|$HOME|g" \
            -e "s|@CHANNELS@|$CHANNELS|g" \
            "$HERE/systemd/$u" > "$STAGE/$u"
    done
    # Installing into /etc needs root. Try without a password first so an automated re-run is
    # quiet; fall back to printing the two commands rather than blocking on a prompt nobody is
    # watching. Nothing here starts or enables anything — that stays an operator decision.
    did "rendered into $STAGE"
    if command -v systemd-analyze >/dev/null 2>&1; then
        # Catches the classic silent mistake: a directive in the wrong section is IGNORED with
        # nothing but a log line, which is the same as not writing it at all.
        # Filtered to OUR unit names: verify pulls in every dependency it can resolve, so on a
        # box with other services in /etc/systemd/system the useful line is buried in warnings
        # about somebody's Minecraft unit.
        (cd "$STAGE" && systemd-analyze verify ./ffbox.target ./*.service 2>&1 \
            | grep -E 'ffbox|ffwatch|ffweb|ffdiscord' \
            | sed 's/^/[discord-setup]   verify: /') || true
    fi
    if sudo -n true 2>/dev/null; then
        sudo install -m 0644 "$STAGE"/ffbox.target "$STAGE"/*.service "$UNIT_DIR/"
        sudo systemctl daemon-reload
        did "installed into $UNIT_DIR"
    else
        did "NOT INSTALLED — that needs root. Run these two, or hand them to whoever has sudo:"
        did "  sudo install -m 0644 $STAGE/ffbox.target $STAGE/*.service $UNIT_DIR/"
        did "  sudo systemctl daemon-reload"
    fi
    did "systemd reads units from $UNIT_DIR; the copies above are only a staging area, so"
    did "re-run those two commands after every change here — \`--check\` flags the drift."
    did "start everything:  sudo systemctl enable --now ffbox.target"
    did "stop everything:   sudo systemctl stop ffbox.target"
    did "  (the .target suffix is required — a bare 'ffbox' means ffbox.service, which is"
    did "   not a unit we ship)"
    did "web UI:       http://127.0.0.1:8787 — reach it with:"
    did "              ssh -N -L 8787:127.0.0.1:8787 $(hostname 2>/dev/null || echo thisbox)"
    did "logs:         journalctl -u ffwatch -f       (or -u ffdiscord-listener, -u ffweb)"
    did "REMINDER: exactly one ffdiscord-listener per bot, across all machines."
fi

say "done"
say "status:  python3 $HERE/ffwatch.py status"
say "web UI:  http://127.0.0.1:8787            (read-only; runs as part of ffbox.target)"
say "         INTERNAL ONLY — it renders repo internals and raw model thinking."
say "one pass by hand (stop the unit first):  python3 $HERE/ffwatch.py --dry-run once"
