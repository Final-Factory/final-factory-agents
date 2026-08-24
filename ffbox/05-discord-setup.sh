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

# EVERY BLANK THE TEMPLATE STILL CARRIES, computed in one place. --check, the end of a
# provisioning run and MANUAL STEPS all print this same list; three hand-maintained copies of
# "what is missing" is how a setup script starts lying about its own state. Prints one line per
# unfilled field with the command that fills it, and exits 1 when a REQUIRED one is still blank.
blanks() {
    FFDISCORD_HOME=$FFDISCORD_HOME FFBOX_CONFIG=$FFBOX_CONFIG \
    FFBOX_CONFIG_JSON=$FFBOX_CONFIG_JSON python3 - <<'PY'
import json
import os
import re
import sys


def read(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


home = os.environ["FFDISCORD_HOME"]
discord = read(os.path.join(home, "config.json"))
ffbox = read(os.environ["FFBOX_CONFIG_JSON"])
secrets = os.path.join(os.environ["FFBOX_CONFIG"], "secrets.env")


def in_secrets(name):
    # The units read this file through EnvironmentFile=, so a token living only there is
    # configured even though the JSON blank is still empty. Commented-out lines do not count.
    try:
        with open(secrets, "r", encoding="utf-8") as fh:
            body = fh.read()
    except OSError:
        return False
    return bool(re.search(rf"^{name}=\s*\S", body, re.MULTILINE))


def out(field, fix, required=True):
    mark = "BLANK" if required else "blank"
    print(f"[discord-setup]   {field:<26} {mark}  {fix}")
    return 1 if required else 0


missing = 0
# Both spellings are accepted everywhere, so a box still carrying the pre-rename keys must not
# be told it is unconfigured.
def filled(new_key, legacy_key, *env_names):
    if str(discord.get(new_key) or "").strip() or str(discord.get(legacy_key) or "").strip():
        return True
    return any(os.environ.get(e) or in_secrets(e) for e in env_names)


if not filled("app_token", "token", "FFDISCORD_APP_TOKEN", "FFDISCORD_TOKEN"):
    missing += out("app_token", "FFDISCORD_APP_TOKEN=<bot token> in secrets.env, "
                                "or: ffdiscord set app_token <bot token>")

# Not counted as missing: ffdiscord infers the guild when the bot is in exactly one, so a box
# that never sets it still works. Reported anyway, because inference is not something you want
# to discover the day a second guild appears.
if not filled("server_id", "guild_id", "FFDISCORD_SERVER_ID", "FFDISCORD_GUILD_ID"):
    out("server_id", "optional (inferred when the bot is in one server): "
                     "ffdiscord set server_id <server id>", required=False)

# The watch block is the list of aliases that MUST resolve: it is what 06-services.sh renders
# into the listener's --channels argument, and the listener exits 2 on an alias it cannot turn
# into a snowflake. An id that is not all digits is as unusable as an empty one.
channels = discord.get("channels") or {}
for alias in sorted(ffbox.get("watch") or {}):
    if not str(channels.get(alias) or "").strip().isdigit():
        missing += out(f"channels.{alias}",
                       f"ffdiscord set channels.{alias} <channel id>")

# The reverse mismatch is not a blank, but it is the same class of mistake: an id nothing
# watches. Reported, never counted.
for alias in sorted(set(channels) - set(ffbox.get("watch") or {})):
    print(f"[discord-setup]   channels.{alias:<15} set, but no \"watch\" entry in "
          f"{os.environ['FFBOX_CONFIG_JSON']} — nothing reads it")

sys.exit(1 if missing else 0)
PY
}

if [ "$CHECK" = 1 ]; then
    say "state dir      : $STATE_DIR $([ -d "$STATE_DIR" ] && echo present || echo MISSING)"
    say "database       : $STATE_DIR/ffwatch.db $([ -f "$STATE_DIR/ffwatch.db" ] && echo present || echo MISSING)"
    say "ffdiscord home : $FFDISCORD_HOME $([ -d "$FFDISCORD_HOME" ] && echo present || echo MISSING)"
    say "config         : $FFDISCORD_HOME/config.json $([ -f "$FFDISCORD_HOME/config.json" ] && echo present || echo MISSING)"
    say "kill switch    : $KILL_SWITCH $([ -f "$KILL_SWITCH" ] && echo ACTIVE || echo 'not set (lanes may run)')"
    say "units          : see 'sh $HERE/06-services.sh'"
    say "still to fill in:"
    blanks || true
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
    # A CPU and memory ceiling, not a licensing one: four game-ci containers in parallel were
    # measured with no licensing trouble. See ffbox/README.md.
    ("max_unity_runs", 2),
    ("catchup_secs", 900),
    # No `dev` entry: it is the lane an operator directive and a locally typed prompt both
    # take, and neither is the runaway a busy forum is. See ffwatch.py DEFAULTS.
    ("rate_limits", {"answer": 200, "triage": 100, "fix": 3}),
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
        "dev_chat": {"kind": "ask", "forum": False,
                     "venue": "private", "engage": "mention"},
    }),
):
    if key not in ffbox:
        ffbox[key] = value
        seeded.append(key)

# THE FILL-IN-THE-BLANKS TEMPLATE. JSON carries no comments, so the only way this file can
# tell a human what it wants is to already contain every key it needs, empty. A config that
# omits "app_token" and "server_id" entirely looks finished when it is not: there is nothing on
# page to fill in, and the reader has to find the shape in a README or in the CLI's docstring.
# Every blank seeded here is falsy, which is exactly what each reader already tests for
# ("if not cfg.get('token')"), so an unfilled template behaves identically to a missing key.
# RENAME, ONCE (2026-08-24). token -> app_token, guild_id -> server_id, matching what a human
# is looking at rather than what the API says: the portal issues an app and its bot token, and
# the Discord client has called a guild a server for years. Every reader still accepts the old
# names, so this migration is for legibility, not for correctness — but leaving both spellings
# on disk is how a config ends up with a token under one key and a blank under the other.
renamed = []
for new_key, legacy_key in (("app_token", "token"), ("server_id", "guild_id")):
    if legacy_key in discord:
        if not str(discord.get(new_key) or "").strip():
            discord[new_key] = discord[legacy_key]
        del discord[legacy_key]
        renamed.append(f"{legacy_key} -> {new_key}")

discord.setdefault("app_token", "")
discord.setdefault("server_id", "")
discord.setdefault("mentions", {})

# WHAT EACH VALUE IS. JSON has no comments, and a blank string does not say what shape belongs
# in it — "channels": {"agent_testing": ""} tells you an alias is wanted and nothing about the
# value. Rewritten on every run rather than setdefault: this is generated documentation, so it
# should track the code, not whatever an old run left behind.
discord["_help"] = {
    "app_token": "Discord developer portal > your app > Bot > Reset Token. NOT the "
                 "Application ID and NOT the public key. Better: leave this blank and put "
                 f"FFDISCORD_APP_TOKEN in {os.path.dirname(ffbox_path)}/secrets.env, which "
                 "keeps the secret out of this file.",
    "server_id": "Right-click the server name > Copy Server ID (Settings > Advanced > "
                 "Developer Mode must be on). Optional: it is inferred when the bot is in "
                 "exactly one server.",
    "channels": "alias -> that channel's id (right-click the channel > Copy Channel ID). The "
                f"alias must match an entry in the \"watch\" block of {ffbox_path}, which is "
                "what says what the channel MEANS; the id here says which channel it IS.",
    "mentions": "name -> user id. What @name expands to in a post.",
    "trust": "operators: name -> user id. Whose messages may command this box. Ids only, "
             "never usernames: a username is renameable, so a trust key somebody else can "
             "claim by renaming is not a trust key.",
}

# One blank per alias the ffwatch "watch" block declares, because those two tables have to
# agree: watch says what a channel MEANS, channels says which channel it IS, and an alias in
# one but not the other is the failure this seeding exists to prevent. The listener refuses to
# start on an alias it cannot resolve to a snowflake, so a blank left here fails loudly at
# startup rather than quietly watching nothing.
channels = discord.setdefault("channels", {})
for alias in sorted((ffbox.get("watch") or {})):
    channels.setdefault(alias, "")

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
if renamed:
    print("[discord-setup]   renamed keys: " + ", ".join(renamed))
print("[discord-setup]   seeded ffwatch keys: " + (", ".join(seeded) or "(nothing new)"))
PY
did "$FFBOX_CONFIG_JSON        (ffwatch + ffweb settings)"
did "$FFDISCORD_HOME/config.json"
# The template now carries a key for everything it needs, so the useful thing to say is whether
# any of those keys are still empty. The list itself belongs to MANUAL STEPS at the end, printed
# once, next to the instructions for filling it.
if ! blanks >/dev/null 2>&1; then
    did "NOTE: not configured yet — see MANUAL STEPS at the end of this run"
fi

# --- channel ids the machine can find for itself -------------------------------------------------
# The alias is not decoration: `agent_testing` in the watch block and #agent-testing in Discord
# are already meant to be the same channel, so once a token exists the only step left is one the
# bot could have done itself by reading the server's channel list. Hand-copying an 18-digit
# snowflake is exactly the kind of transcription a setup script should not be asking for.
#
# Best effort, and never fatal. No token, no network, a name that matches two channels, or a
# channel the bot has not been given access to all leave the blank in place for a human.
say "channels"
if blanks 2>/dev/null | grep -q ' app_token  *BLANK'; then
    did "skipped: no app token yet, so the bot cannot read the server's channel list"
elif ! blanks 2>/dev/null | grep -q ' channels\.'; then
    did "every watched channel already has an id"
elif ! command -v ffdiscord >/dev/null 2>&1; then
    did "ffdiscord is not on PATH — run 'sh registerAgents.sh', or fill the ids in by hand"
else
    RESOLVE_RC=0
    # A subshell so the token this sources stays out of the rest of this script's environment.
    RESOLVE_OUT=$(
        set +e
        if [ -f "$FFBOX_CONFIG/secrets.env" ]; then
            set -a
            . "$FFBOX_CONFIG/secrets.env"
            set +a
        fi
        ffdiscord resolve-channels --write 2>&1
    ) || RESOLVE_RC=$?
    printf '%s\n' "$RESOLVE_OUT" | sed 's/^/[discord-setup]   /'
    [ "$RESOLVE_RC" = 0 ] || did "lookup did not complete; fill the rest in by hand (see below)"
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
if ! blanks >/dev/null 2>&1; then
    say "  1. Create a Discord bot (or reuse yours) at https://discord.com/developers"
    say "     - Bot > Privileged Gateway Intents: leave all three OFF. The listener asks only"
    say "       for GUILDS, GUILD_MESSAGES and DIRECT_MESSAGES, which are not privileged and"
    say "       have no toggle; MESSAGE_CONTENT is deliberately not requested."
    say "     - invite it (OAuth2 > URL Generator, scope 'bot') and give it, per channel:"
    say "       View Channels, Read Message History, Send Messages, Embed Links, Attach Files,"
    say "       plus Add Reactions + Create Public Threads + Send Messages in Threads on a forum."
    say "  2. Fill in the blanks below. Every one of them is already a key in"
    say "     $FFDISCORD_HOME/config.json, waiting empty, and the \"_help\" block in that"
    say "     file says what each value is:"
    blanks || true
    say "     (Discord: Settings > Advanced > Developer Mode, then right-click to copy an id.)"
    say "     app_token is the Bot tab's Reset Token, NOT the Application ID or public key."
    say "     Channel ids: once app_token is set, re-run this script and it looks them up by"
    say "     name, or do it directly with 'ffdiscord resolve-channels --write'."
    say "  3. Watching a channel this box does not know about yet? Add it to the ffwatch"
    say "     \"watch\" block in $FFBOX_CONFIG_JSON first, which is what says what it MEANS:"
    say '       "watch": { "agent_testing": { "kind": "ask", "forum": false,'
    say '                                     "venue": "private", "engage": "mention" } }'
    say "     kind ask/mention -> read-only answer lane; bug_report/suggestion -> triage;"
    say "     directive -> the write lane. A channel not listed here falls to the classifier,"
    say "     which fails closed to read-only. Re-run this script to get its blank."
    say "  4. ffdiscord doctor            # verifies the token, guild and channel permissions"
    say "     (reads the env, not secrets.env: 'set -a; . $FFBOX_CONFIG/secrets.env; set +a' first)"
    say "  5. sudo sh $HERE/06-services.sh --install   # picks up the new watch list"
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
