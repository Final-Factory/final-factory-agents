#!/bin/sh
# discord-setup.sh — provision this machine for the ffbox Discord lanes.
#
#   sh ffbox/discord-setup.sh                  provision (idempotent; safe to re-run)
#   sh ffbox/discord-setup.sh --check          report what is and is not in place, change nothing
#   sudo sh ffbox/discord-setup.sh --install-units
#                                              install the units into /etc/systemd/system from
#                                              this checkout and start them; nothing else
#   sudo sh ffbox/discord-setup.sh --install-units --no-enable
#                                              install them but leave them stopped
#   sh ffbox/discord-setup.sh --no-units       skip the systemd unit stage
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
# --install-units is meant to be run under sudo, and under sudo $HOME and `id -un` are root's.
# The units have to describe the user who actually owns the checkout, the docker group and the
# Claude credential, so recover that identity from SUDO_USER — the same trick zfsSetup.sh uses.
RUN_USER=$(id -un)
if [ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
    RUN_USER=$SUDO_USER
    HOME=$(getent passwd "$RUN_USER" | cut -d: -f6)
    HOME=${HOME%/}
fi
RUN_GROUP=$(id -gn "$RUN_USER")
FFDISCORD_HOME=${FFDISCORD_HOME:-$HOME/.config/ffdiscord}
FFBOX_CONFIG=$HOME/.config/ffbox
KILL_SWITCH=$FFBOX_CONFIG/discord.disabled
STATE_DIR=${FFWATCH_STATE_DIR:-$HOME/ffbox-state}

CHECK=0
UNITS=1
INSTALL_UNITS=0
NO_ENABLE=0
for arg in "$@"; do
    case "$arg" in
        --check)         CHECK=1 ;;
        --no-units)      UNITS=0 ;;
        --install-units) INSTALL_UNITS=1 ;;
        --no-enable)     NO_ENABLE=1 ;;
        -h|--help)       sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)               echo "discord-setup.sh: unknown option $arg" >&2; exit 2 ;;
    esac
done

say()  { printf '[discord-setup] %s\n' "$*"; }
did()  { printf '[discord-setup]   %s\n' "$*"; }

UNIT_NAMES="ffbox.target ffdiscord-listener.service ffwatch.service ffweb.service"

# The listener watches whatever the config says to watch. Reading it back from the ffwatch block
# means adding a channel there and re-installing is enough — no second place to edit, and no
# unit quietly watching a channel the classifier no longer knows about.
watched_channels() {
    CONFIG_PATH="$FFDISCORD_HOME/config.json" python3 - <<'PY'
import json, os
try:
    cfg = json.load(open(os.environ["CONFIG_PATH"], encoding="utf-8"))
except Exception:
    cfg = {}
watch = ((cfg.get("ffwatch") or {}).get("watch") or {})
print(",".join(sorted(watch)) or "ask_claude,bug_reports")
PY
}

# THE TEMPLATES IN ffbox/systemd/ ARE THE ONLY SOURCE. They are rendered into a throwaway
# directory and installed from there; nothing rendered is ever kept beside the config, because a
# second copy on disk is a second thing that can disagree with git. @PLACEHOLDERS@ exist because
# this repo can be cloned anywhere and a wrong ExecStart fails at unit start with a message
# nobody reads. Rendering never needs root — only installing does.
render_units() {
    _dest=$1
    _channels=$(watched_channels)
    mkdir -p "$_dest"
    for u in $UNIT_NAMES; do
        sed -e "s|@FFWATCH@|$HERE/ffwatch.py|g" \
            -e "s|@FFWEB@|$HERE/ffweb.py|g" \
            -e "s|@USER@|$RUN_USER|g" \
            -e "s|@GROUP@|$RUN_GROUP|g" \
            -e "s|@HOME@|$HOME|g" \
            -e "s|@CHANNELS@|$_channels|g" \
            "$HERE/systemd/$u" > "$_dest/$u"
    done
}

if [ "$INSTALL_UNITS" = 1 ]; then
    # Deliberately the ONLY thing this mode does. Running the whole provisioning pass as root
    # would leave a root-owned state directory and a root-owned config that the service user
    # then cannot write.
    if [ "$(id -u)" != 0 ]; then
        say "--install-units writes to $UNIT_DIR and needs root. Run:"
        say "  sudo sh $HERE/discord-setup.sh --install-units"
        exit 1
    fi
    say "installing units for $RUN_USER (home $HOME) from $HERE/systemd"
    TMP=$(mktemp -d)
    trap 'rm -rf "$TMP"' EXIT
    render_units "$TMP"
    if command -v systemd-analyze >/dev/null 2>&1; then
        # Catches the classic silent mistake: a directive in the wrong section is IGNORED with
        # nothing but a log line. Filtered to OUR unit names, because verify pulls in every
        # dependency it can resolve and would otherwise bury the answer in warnings about
        # somebody else's service.
        (cd "$TMP" && systemd-analyze verify ./ffbox.target ./*.service 2>&1 \
            | grep -E 'ffbox|ffwatch|ffweb|ffdiscord' \
            | sed 's/^/[discord-setup]   verify: /') || true
    fi
    for u in $UNIT_NAMES; do
        install -m 0644 "$TMP/$u" "$UNIT_DIR/$u"
        did "$UNIT_DIR/$u"
    done
    systemctl daemon-reload
    did "daemon-reload done"

    # Installing a unit and then leaving it stopped is a half-finished job: nobody runs a setup
    # script hoping to be handed one more command. Enabling is safe even before the bot token
    # exists — with no token the listener exits and ffwatch has nothing to read — and the kill
    # switch remains the way to stop the lanes without stopping the daemons.
    if [ "$NO_ENABLE" = 1 ]; then
        did "not enabled (--no-enable). Start it with: sudo systemctl enable --now ffbox.target"
    else
        systemctl enable --now ffbox.target
        did "enabled and started ffbox.target (listener + ffwatch + ffweb)"
        for u in ffdiscord-listener.service ffwatch.service ffweb.service; do
            did "  $u: $(systemctl is-active "$u" 2>/dev/null | head -1)"
        done
        did "stop everything:  sudo systemctl stop ffbox.target"
        did "logs:             journalctl -u ffwatch -f"
    fi
    exit 0
fi

if [ "$CHECK" = 1 ]; then
    say "state dir      : $STATE_DIR $([ -d "$STATE_DIR" ] && echo present || echo MISSING)"
    say "database       : $STATE_DIR/ffwatch.db $([ -f "$STATE_DIR/ffwatch.db" ] && echo present || echo MISSING)"
    say "ffdiscord home : $FFDISCORD_HOME $([ -d "$FFDISCORD_HOME" ] && echo present || echo MISSING)"
    say "config         : $FFDISCORD_HOME/config.json $([ -f "$FFDISCORD_HOME/config.json" ] && echo present || echo MISSING)"
    say "kill switch    : $KILL_SWITCH $([ -f "$KILL_SWITCH" ] && echo ACTIVE || echo 'not set (lanes may run)')"
    say "units          : $UNIT_DIR  (source: $HERE/systemd)"
    # Rendered fresh from git into a temp dir purely to compare. Nothing is kept.
    TMP=$(mktemp -d)
    trap 'rm -rf "$TMP"' EXIT
    render_units "$TMP"
    STALE=0
    for u in $UNIT_NAMES; do
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
        if [ -f "$UNIT_DIR/$u" ] && ! cmp -s "$UNIT_DIR/$u" "$TMP/$u"; then
            st="$st, STALE (differs from what this checkout renders)"
            STALE=1
        fi
        say "  $u $st"
    done
    if [ "$STALE" = 1 ]; then
        say "re-install the stale units with:"
        say "  sudo sh $HERE/discord-setup.sh --install-units"
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
#
# This stage never writes a rendered unit anywhere but /etc/systemd/system, and it only gets
# there through --install-units. git is the source; there is no staging copy to drift.
say "units"
did "listener will watch: $(watched_channels)"

if [ "$UNITS" = 0 ]; then
    did "skipped (--no-units)"
elif ! command -v systemctl >/dev/null 2>&1; then
    did "no systemctl here; run the daemons yourself:"
    did "  ffdiscord-listener --channels $(watched_channels)"
    did "  python3 $HERE/ffwatch.py run"
    did "  python3 $HERE/ffweb.py"
else
    # A retired staging directory from an earlier version of this script. Left behind it would
    # be the one stale copy of these files on the box, which is exactly what moving the source
    # into git was meant to prevent.
    if [ -d "$FFBOX_CONFIG/systemd" ]; then
        rm -f "$FFBOX_CONFIG"/systemd/ffbox.target "$FFBOX_CONFIG"/systemd/*.service
        rmdir "$FFBOX_CONFIG/systemd" 2>/dev/null || true
        did "removed the old rendered copies under $FFBOX_CONFIG/systemd (git is the source now)"
    fi
    # Install and start it here rather than printing homework. Writing to /etc needs root, so
    # this re-invokes itself through sudo — the ONE thing this script cannot do as your user.
    # Everything above already ran, and --install-units deliberately does only the unit work,
    # so nothing under $HOME ends up root-owned.
    if [ "$(id -u)" = 0 ]; then
        sh "$HERE/discord-setup.sh" --install-units
    elif sudo -n true 2>/dev/null || [ -t 0 ]; then
        did "installing and starting the units (needs root; sudo may prompt)"
        if ! sudo sh "$HERE/discord-setup.sh" --install-units; then
            did "that failed — run it yourself:"
            did "  sudo sh $HERE/discord-setup.sh --install-units"
        fi
    else
        did "NOT INSTALLED — that needs root, and there is no terminal here to ask on. Run:"
        did "  sudo sh $HERE/discord-setup.sh --install-units"
    fi
    did "after ANY change to the units or the watch block, re-run:"
    did "  sudo sh $HERE/discord-setup.sh --install-units"
    did "  ('$0 --check' flags an installed unit that no longer matches this checkout)"
    did "web UI:  http://127.0.0.1:8787 — reach it with:"
    did "         ssh -N -L 8787:127.0.0.1:8787 $(hostname 2>/dev/null || echo thisbox)"
    did "REMINDER: exactly one ffdiscord-listener per bot, across all machines."
fi

say "done"

# What is actually left, and nothing that is not. The old closing block told everyone to install
# units "once the bot token is in config.json", which conflated two unrelated things: the units
# do not need a token, and a token does not need units.
if ! python3 -c "
import json,sys
cfg=json.load(open(sys.argv[1]))
sys.exit(0 if (cfg.get('token') or '').strip() else 1)" "$FFDISCORD_HOME/config.json" 2>/dev/null \
   && [ -z "${FFDISCORD_TOKEN:-}" ]; then
    say "NEXT: there is no bot token yet, so nothing will be read from Discord."
    say "  1. put the bot token in $FFDISCORD_HOME/config.json (or FFDISCORD_TOKEN in"
    say "     $FFBOX_CONFIG/secrets.env), plus guild_id and the channels to watch"
    say "  2. add each watched channel to the ffwatch \"watch\" block in the same file"
    say "  3. sudo sh $HERE/discord-setup.sh --install-units   # picks up the new watch list"
    say "  4. ffdiscord doctor      # verifies the token, guild and channel permissions"
else
    say "NEXT: a token is configured. Check the bot can see what you expect:"
    say "  ffdiscord doctor"
    say "  sh $HERE/discord-setup.sh --check"
fi
say ""
say "status:  python3 $HERE/ffwatch.py status"
say "web UI:  http://127.0.0.1:8787            (read-only; part of ffbox.target)"
say "         INTERNAL ONLY — it renders repo internals and raw model thinking."
say "kill switch: touch $KILL_SWITCH   (ffwatch keeps running, launches nothing)"
say "one pass by hand (stop ffwatch first):  python3 $HERE/ffwatch.py --dry-run once"
