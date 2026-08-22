#!/bin/sh
# 05-discord-setup.sh — the Discord lanes' state: database, config, kill switch.
#
# Normally you do not run this: `sh ffbox/setup.sh` runs it as stage 5. It needs no root and
# starts nothing — the systemd units belong to 06-services.sh, because ffwatch and ffweb are
# ffbox's daemons rather than Discord's and should not live inside a script named for one front
# door.
#
#   sh ffbox/05-discord-setup.sh          provision (idempotent; safe to re-run)
#   sh ffbox/05-discord-setup.sh --check  report what is and is not in place, change nothing
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

# Run as yourself. This stage writes only under $HOME, so running it with sudo would leave a
# root-owned state directory the service user cannot write.
if [ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
    echo "05-discord-setup.sh: run this WITHOUT sudo — it writes to \$HOME only." >&2
    echo "                     (the units are 06-services.sh, which does need root)" >&2
    exit 2
fi
STATE_DIR=${FFWATCH_STATE_DIR:-$HOME/ffbox-state}
FFDISCORD_HOME=${FFDISCORD_HOME:-$HOME/.config/ffdiscord}
FFBOX_CONFIG=$HOME/.config/ffbox
KILL_SWITCH=$FFBOX_CONFIG/discord.disabled

CHECK=0
for arg in "$@"; do
    case "$arg" in
        --check)   CHECK=1 ;;
        -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)         echo "05-discord-setup.sh: unknown option $arg" >&2; exit 2 ;;
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
    say "units          : see 'sh $HERE/06-services.sh'"
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

say "done"

# What is actually left, and nothing that is not. Every line here is a step a human has to take;
# anything the script could do itself, it already did.
say ""
say "MANUAL STEPS REMAINING"
if ! python3 -c "
import json,sys
cfg=json.load(open(sys.argv[1]))
sys.exit(0 if (cfg.get('token') or '').strip() else 1)" "$FFDISCORD_HOME/config.json" 2>/dev/null \
   && [ -z "${FFDISCORD_TOKEN:-}" ]; then
    say "  1. Create a Discord bot (or reuse yours) at https://discord.com/developers"
    say "     - enable the GUILDS and GUILD_MESSAGES intents; MESSAGE_CONTENT is NOT needed"
    say "     - invite it to your server and give it access to the channels you want watched"
    say "  2. Put the token in $FFDISCORD_HOME/config.json as \"token\""
    say "     (or FFDISCORD_TOKEN in $FFBOX_CONFIG/secrets.env — host side only, never in git)"
    say "  3. Add \"guild_id\" and each channel to \"channels\", e.g."
    say '       "channels": { "agent_testing": "<channel id>" }'
    say "     (Discord: Settings > Advanced > Developer Mode, then right-click to copy an id)"
    say "  4. Tell ffwatch what each watched channel MEANS, in the ffwatch \"watch\" block:"
    say '       "watch": { "agent_testing": { "kind": "ask", "forum": false } }'
    say "     kind ask/mention -> read-only answer lane; bug_report/suggestion -> triage;"
    say "     directive -> the write lane. A channel not listed here falls to the classifier,"
    say "     which fails closed to read-only."
    say "  5. ffdiscord doctor            # verifies the token, guild and channel permissions"
    say "  6. sudo sh $HERE/06-services.sh --install   # picks up the new watch list"
else
    say "  1. ffdiscord doctor            # verifies the token, guild and channel permissions"
    say "  2. sudo sh $HERE/06-services.sh --install   # (re)install the units and start them"
fi
say "  Optional but recommended for the first days on a live server:"
say "    - approve_before_send: true in the ffwatch block holds every reply for review"
say "    - touch $KILL_SWITCH   to stop ffwatch launching runs at all"
say ""
say "status:  python3 $HERE/ffwatch.py status"
say "units:   sh $HERE/06-services.sh"
say "one pass by hand (stop ffwatch first):  python3 $HERE/ffwatch.py --dry-run once"
