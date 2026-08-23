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
# EVERYTHING ffbox owns on this machine lives under one directory (moved 2026-08-22):
#
#   ~/.config/ffbox/secrets.env        tokens and the Unity account
#   ~/.config/ffbox/config.json        ffwatch and ffweb settings
#   ~/.config/ffbox/discord/           the Discord CLI's own home: config.json (token, guild,
#                                      channels), cursors, the doorbell, the listener lock
#   ~/.config/ffbox/discord.disabled   the kill switch
#
# The pre-move ~/.config/ffdiscord is migrated below rather than left to rot: two config files
# where one is read and the other is edited is the worst outcome available.
FFBOX_CONFIG=$HOME/.config/ffbox
FFDISCORD_HOME=${FFDISCORD_HOME:-$FFBOX_CONFIG/discord}
FFBOX_CONFIG_JSON=$FFBOX_CONFIG/config.json
LEGACY_FFDISCORD_HOME=$HOME/.config/ffdiscord
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
mkdir -p "$FFBOX_CONFIG"
chmod 700 "$FFBOX_CONFIG" 2>/dev/null || true

# --- migration: ~/.config/ffdiscord -> ~/.config/ffbox/discord ------------------------------
# Moved whole, cursors and doorbell included, because the listener's read cursors are state a
# reinstall must not lose. Only when the destination does not exist: a half-merge of two live
# config directories is not something a setup script should attempt.
if [ -d "$LEGACY_FFDISCORD_HOME" ] && [ ! -e "$FFDISCORD_HOME" ]; then
    mv "$LEGACY_FFDISCORD_HOME" "$FFDISCORD_HOME"
    did "migrated $LEGACY_FFDISCORD_HOME -> $FFDISCORD_HOME"
elif [ -d "$LEGACY_FFDISCORD_HOME" ]; then
    did "NOTE: $LEGACY_FFDISCORD_HOME still exists and $FFDISCORD_HOME does too."
    did "      Nothing was moved. Merge them by hand, then delete the old one."
fi
mkdir -p "$FFDISCORD_HOME"
chmod 700 "$FFDISCORD_HOME" 2>/dev/null || true
CONFIG_PATH="$FFDISCORD_HOME/config.json" FFBOX_CONFIG_JSON="$FFBOX_CONFIG_JSON" python3 - <<'PY'
import json
import os

# TWO FILES, EACH OWNING WHAT IT IS FOR.
#   ~/.config/ffbox/config.json     ffwatch and ffweb: lanes, ceilings, the page's bind address
#   ~/.config/ffbox/discord/config.json   the Discord CLI's own: token, guild, channels, mentions
#
# They used to be one file, with the ffwatch settings in a block inside the Discord CLI's
# config, which meant a root-run installer had to read a user's Discord directory to find out
# where the WEB PAGE should listen. Anything still in that block is moved here, once.


def read(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        try:
            loaded = json.load(fh)
        except json.JSONDecodeError:
            raise SystemExit(f"{path} is not valid JSON; fix it before re-running")
    return loaded if isinstance(loaded, dict) else {}


def write(path, data):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


discord_path = os.environ["CONFIG_PATH"]
ffbox_path = os.environ["FFBOX_CONFIG_JSON"]
discord = read(discord_path)
ffbox = read(ffbox_path)

moved = sorted(k for k in (discord.get("ffwatch") or {}) if k not in ffbox)
for key, value in (discord.get("ffwatch") or {}).items():
    ffbox.setdefault(key, value)
if "ffwatch" in discord:
    del discord["ffwatch"]

seeded = []
for key, value in (
    # Left as "~/ffbox-state" unless overridden, so the file stays portable between machines
    # with different home paths.
    ("state_dir", os.environ.get("FFWATCH_STATE_DIR", "~/ffbox-state")),
    ("base_ref", "develop"),
    ("agent_secs", 900),
    ("warmup_secs", 3600),
    ("kill_grace_secs", 10),
    ("max_concurrent_runs", 2),
    ("max_unity_runs", 1),
    ("catchup_secs", 900),
    ("rate_limits", {"answer": 200, "triage": 100, "fix": 3, "dev": 25}),
    # The page. It is behind a login and served over TLS, but 127.0.0.1 is still the default:
    # it renders raw model thinking, and one hardcoded password is a thin thing to hold a LAN
    # off with. Widening it stays a deliberate edit, made here where it is reviewable.
    ("web_host", "127.0.0.1"),
    ("web_port", 8787),
    # approve_before_send holds every reply at 'pending' until `ffwatch approve <id>` releases
    # it — turn it on for the first days on a live server.
    ("approve_before_send", False),
    ("send_limits", {"per_hour": 60, "per_conversation_hour": 12}),
    ("max_send_attempts", 5),
    # venue and engage are declared here, not inferred from Discord permissions. See
    # design/trusted_ingress_design.txt sections 4 and 5, and the same table in ffwatch's
    # DEFAULTS. An existing config keeps whatever it already says; ffwatch's own defaults fill
    # a missing key and warn about it at startup.
    ("watch", {
        "ask_claude": {"kind": "ask", "forum": False,
                       "venue": "public", "engage": "all"},
        "bug_reports": {"kind": "bug_report", "forum": True,
                        "venue": "public", "engage": "all"},
        "suggestions": {"kind": "suggestion", "forum": True,
                        "venue": "public", "engage": "all"},
    }),
):
    if key not in ffbox:
        ffbox[key] = value
        seeded.append(key)

discord.setdefault("channels", {})
discord.setdefault("mentions", {})

# WHO IS AN OPERATOR. Snowflake ids, never usernames: a username is renameable, so a trust key
# somebody else can claim by renaming is not a trust key. These two live in the DISCORD config
# rather than the ffbox one because the Gateway listener has to answer the same question and
# reads no other file (design/trusted_ingress_design.txt section 3).
#
# setdefault at every level, so a machine that has already edited either table is left alone.
OPERATORS = {"ben": "226422780445458432", "lothsahn": "193210319093497857"}
trust = discord.setdefault("trust", {})
operators = trust.setdefault("operators", {})
for name, uid in OPERATORS.items():
    operators.setdefault(name, uid)
    # The same ids are what "@ben" expands to in a post, so seed the mention table from them
    # rather than leaving two places to fill in by hand and get inconsistent.
    discord["mentions"].setdefault(name, uid)

write(ffbox_path, ffbox)
write(discord_path, discord)
if moved:
    print("[discord-setup]   moved out of the Discord config: " + ", ".join(moved))
print("[discord-setup]   seeded ffwatch keys: " + (", ".join(seeded) or "(nothing new)"))
PY
did "$FFBOX_CONFIG_JSON        (ffwatch + ffweb settings)"
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
