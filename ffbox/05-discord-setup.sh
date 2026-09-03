#!/bin/sh
# 05-discord-setup.sh — the Discord pipeline's state: database, config, kill switch.
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
#   ~/.config/ffbox/config.json        ffwatch, ffweb, the CI runners, and the "discord"
#                                      section: token, server, channels, mentions, trust,
#                                      and which agent pool each side of that trust gets
#   ~/.config/ffbox/discord/           the Discord CLI's STATE: cursors, the doorbell, the
#                                      listener lock. Its config moved into the file above on
#                                      2026-09-01, so the alias table and the "watch" block
#                                      that gives those aliases their meaning are one edit.
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
    FFBOX_CONFIG=$FFBOX_CONFIG \
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


ffbox = read(os.environ["FFBOX_CONFIG_JSON"])
discord = ffbox.get("discord")
if not isinstance(discord, dict):
    discord = {}
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

# WHO MAY COMMAND THIS BOX. The template seeds trust.operators with an example name and an
# empty id, so a fresh machine has NOBODY trusted — no operator directive and no operator DM
# will fire. That is the right default and the wrong thing to discover from a journal line, and
# MANUAL STEPS is driven entirely by this function, so it has to be listed here or the script
# says "you are done" about a box that answers nobody.
operators = ((discord.get("trust") or {}).get("operators") or {})
if not any(str(v or "").strip().isdigit() for v in operators.values()):
    named = ", ".join(sorted(operators)) or "none"
    missing += out("trust.operators",
                   f"ffdiscord set trust.operators.<name> <user id>   (present: {named}; "
                   f"ids only, never usernames)")

# THE TWO POOL NAMES, checked against the classes that exist. Not counted as missing -- the
# template seeds both and ffwatch falls back to the same defaults on a bad value -- but a typo
# here silently sends every Discord conversation to the fenced class, or, worse the other way,
# and the journal line that says so scrolls past once at ingest.
for _pool_key, _pool_want in (("user_pool", "ffagent"), ("operator_pool", "ffdev")):
    _pool = str(discord.get(_pool_key) or "").strip()
    if _pool and _pool not in ("ffagent", "ffdev"):
        out(f"{_pool_key}", f"{_pool!r} is not an agent class; ffwatch will use {_pool_want}: "
                            f"ffdiscord set {_pool_key} <ffagent|ffdev>", required=False)

# Same table, the other half: a mention target is what "@name" expands to in a post.
if not any(str(v or "").strip().isdigit()
           for v in (discord.get("mentions") or {}).values()):
    out("mentions", "ffdiscord set mentions.<name> <user id>   "
                    "(optional until something needs to ping a human)", required=False)

# The reverse mismatch is not a blank, but it is the same class of mistake: an id nothing
# watches. Reported, never counted.
for alias in sorted(set(channels) - set(ffbox.get("watch") or {})):
    print(f"[discord-setup]   channels.{alias:<15} set, but no \"watch\" entry beside it "
          f"in {os.environ['FFBOX_CONFIG_JSON']} — nothing reads it")

sys.exit(1 if missing else 0)
PY
}

if [ "$CHECK" = 1 ]; then
    say "state dir      : $STATE_DIR $([ -d "$STATE_DIR" ] && echo present || echo MISSING)"
    say "database       : $STATE_DIR/ffwatch.db $([ -f "$STATE_DIR/ffwatch.db" ] && echo present || echo MISSING)"
    say "ffdiscord state: $FFDISCORD_HOME $([ -d "$FFDISCORD_HOME" ] && echo present || echo MISSING)"
    say "config         : $FFBOX_CONFIG_JSON $([ -f "$FFBOX_CONFIG_JSON" ] && echo present || echo MISSING)"
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

# --- config ---------------------------------------------------------------------------------
# ONE machine-local file, 0600, outside the repo. Seeding it must not disturb the token or the
# channel ids that are already there, so the merge is key-by-key rather than a rewrite.
say "config"
mkdir -p "$FFBOX_CONFIG"
chmod 700 "$FFBOX_CONFIG" 2>/dev/null || true

# --- migration: ~/.config/ffdiscord -> ~/.config/ffbox/discord ------------------------------
# The STATE directory, moved whole: the listener's read cursors and the doorbell are state a
# reinstall must not lose. Only when the destination does not exist — a half-merge of two live
# directories is not something a setup script should attempt.
if [ -d "$LEGACY_FFDISCORD_HOME" ] && [ ! -e "$FFDISCORD_HOME" ]; then
    mv "$LEGACY_FFDISCORD_HOME" "$FFDISCORD_HOME"
    did "migrated $LEGACY_FFDISCORD_HOME -> $FFDISCORD_HOME"
elif [ -d "$LEGACY_FFDISCORD_HOME" ]; then
    did "NOTE: $LEGACY_FFDISCORD_HOME still exists and $FFDISCORD_HOME does too."
    did "      Nothing was moved. Merge them by hand, then delete the old one."
fi
mkdir -p "$FFDISCORD_HOME"
chmod 700 "$FFDISCORD_HOME" 2>/dev/null || true

# THE OLD CONFIG NEXT DOOR, retired 2026-09-01 and cleared away here since 2026-09-02. Nothing
# has read $FFDISCORD_HOME/config.json since those settings moved into the "discord" section of
# the box's one config.json; this directory keeps only STATE (cursors, doorbell, listener lock).
# A file nobody reads that still looks like configuration is worse than no file: somebody sets
# trust.operators or a channel id in it, restarts, and cannot see why nothing changed. Renamed
# rather than deleted, because on a box whose migration never finished it may hold the only
# copy of a token.
if [ -f "$FFDISCORD_HOME/config.json" ]; then
    mv "$FFDISCORD_HOME/config.json" \
       "$FFDISCORD_HOME/config.json.retired-$(date -u +%Y%m%dT%H%M%SZ)"
    did "retired $FFDISCORD_HOME/config.json - nothing has read it since 2026-09-01;"
    did "      the live settings are the \"discord\" section of $FFBOX_CONFIG_JSON"
fi

FFBOX_CONFIG_JSON="$FFBOX_CONFIG_JSON" python3 - <<'PY'
import json
import os

# ONE FILE FOR THE BOX: ~/.config/ffbox/config.json.
#   top level + "ffagent" + "container"   ffwatch and ffweb: lanes, ceilings, the page's bind
#   "githubrunner"                        the CI runner pool
#   "discord"                             the Discord CLI's own: token, server, channels,
#                                         mentions, trust -- plus user_pool/operator_pool,
#                                         ffwatch's, which read that trust table
#
# The Discord keys had a config.json of their own next door until 2026-09-01. That put the
# "channels" alias table and the "watch" block that gives those aliases their meaning in two
# files that had to be edited together and could disagree — and every reader had to open both
# and decide which won. One file, one read, one place to look.


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


ffbox_path = os.environ["FFBOX_CONFIG_JSON"]
ffbox = read(ffbox_path)
# The Discord section, edited in place and written back with everything else at the end. A
# section that is missing, null or the wrong shape starts empty rather than raising: this
# script's whole job is to hand a half-configured box a template it can fill in.
discord = ffbox.get("discord")
if not isinstance(discord, dict):
    discord = {}

seeded = []
for key, value in (
    # Left as "~/ffbox-state" unless overridden, so the file stays portable between machines
    # with different home paths.
    ("state_dir", os.environ.get("FFWATCH_STATE_DIR", "~/ffbox-state")),
    # THE BOX'S CONTAINER CEILING, and it stays at the top level because it is not the agent's
    # alone: agent runs, staged pool containers and ffgithubrunners' CI jobs all count against it.
    # See ffbox/lib-workloads.sh, which is what actually refuses.
    ("max_concurrent_runs", 6),
    ("catchup_secs", 900),
    # --- the agent containers -------------------------------------------------------------
    # Everything that governs a RUN rather than the pipeline around it: the clocks it is held
    # to, the branch its workspace starts from, and the warm pool it may be dispatched into.
    # ffwatch flattens this section over the top level, so a key here is read exactly as it
    # was before it moved.
    ("ffagent", {
        # Where a run's clone starts. Must match the first key of ffwatch's publish_bases,
        # which is what the agent is told to branch from by default; disagreeing costs a
        # cross-base checkout and a full Unity reimport inside every container.
        "base_ref": "master",
        # THREE CLOCKS, and conflating them makes a slow Unity import look like a hung agent.
        # agent_secs is the model's working time, measured from the .agent-started marker;
        # warmup_secs covers everything before it; kill_grace_secs is how long a container
        # gets to finish after it is told to stop.
        "agent_secs": 1800,
        "warmup_secs": 3600,
        "kill_grace_secs": 10,
        # THE POOL, in the same shape the runners use. idle is how many containers fill a
        # workspace before any request exists, so one that arrives finds a warm one: 1.2s from
        # dispatch to the agent starting, against 40s cold, and 0 is off. Each staged container
        # counts against max_concurrent_runs above AND holds a Unity seat, taken after it syncs
        # and before it goes idle.
        #
        # max is THIS LANE's ceiling on containers, runs and staged ones together, underneath
        # the box-wide max_concurrent_runs that CI counts against too. Both have to hold: the
        # lane cap stops the agent filling a shared box on its own, the box cap stops the two
        # lanes together overcommitting it.
        #
        # -1 means "no ceiling of my own" and is coerced to max_concurrent_runs, so the default
        # is to use the whole box when CI is quiet. A negative idle is coerced to 0, which is
        # off. Zero is left alone on both: it means no places, which is a thing somebody may
        # actually want to say.
        "pool": {"idle": 1, "max": -1},
        # What a staged container waits before retiring. Passed in at stage time, so the
        # deadline it enforces is the one configured when it was staged.
        "idle_agent_ttl_secs": 14400,
        # Which branch the pool stages. null follows base_ref, and there is deliberately no
        # second answer to configure: a pool staged on a branch no turn asks for serves nothing.
        "pool_ref": None,
        # THE FENCE. ffbox-net is a Docker --internal bridge with no default route, whose only
        # other occupant is the egress proxy: a run on it reaches the names in
        # ffbox/egress/allowlist.txt and nothing else, no LAN and not this host. ffagent serves
        # text written by strangers in a Discord forum, so this is the one that stays shut.
        "network": "ffbox-net",
    }),
    # THE SECOND AGENT CLASS. Same keys as "ffagent" above and the same meanings: the two are
    # separate config sections with no inheritance between them, so ffdev reads THIS and never
    # ffagent's numbers. Editing one does not move the other, which is the point -- they exist
    # in order to diverge, and as of 2026-09-02 they do, on the network.
    #
    # idle 1 / max 3: one ffdev container waits warm, and at most three exist at once, runs and
    # staged ones together, underneath the box-wide max_concurrent_runs that CI counts against
    # too. 3 rather than -1 because dev turns are the long ones.
    #
    # A conversation picks its class when it is opened -- the dropdown on the web page's new
    # prompt box, `ffwatch submit --agent ffdev`, or, for a Discord conversation, the
    # "user_pool"/"operator_pool" pair in the "discord" section, which picks by whether the
    # account that opened it is in trust.operators -- and every later turn of it runs in the
    # same kind of container.
    ("ffdev", {
        "base_ref": "master",
        "agent_secs": 1800,
        "warmup_secs": 3600,
        "kill_grace_secs": 10,
        "pool": {"idle": 1, "max": 3},
        "idle_agent_ttl_secs": 14400,
        "pool_ref": None,
        # NO FENCE, DELIBERATELY. "bridge" is the ordinary NATted docker bridge: the whole
        # internet, no allowlist, no SNI filter. A dev turn has to be able to read documentation,
        # search the web and fetch a package, and an allowlist that must be edited every time it
        # needs a new host is not a fence, it is a queue.
        #
        # Know what it costs before changing ffagent to match: this is not the fence minus DNS
        # filtering, it is no fence. A container on the bridge also reaches this machine's own
        # LAN address -- measured 2026-08-25, port 22 answered -- because rootless Docker
        # disables the host loopback and not the host's IP. ffdev is trusted the way a
        # developer's shell on this box is trusted, which is what it is for.
        "network": "bridge",
    }),
    # Turns per rolling 24 hours, keyed on TRUST TIER — who wrote the text, not which lane it
    # took. One budget across every kind of turn a player can cause. `operator` is null, which
    # ffwatch reads as no limit: an operator directive and a locally typed prompt are not the
    # runaway a busy forum is. See ffwatch.py DEFAULTS.
    # Tier keys cap TURNS per rolling 24 hours, keyed on who wrote the text rather than which
    # lane it took; "send" caps what reaches the wire, and is separate because one run that loops
    # writing intents would spray a thread no matter how few turns it took. Anything here that is
    # not "send" is a tier. `operator` is null, which ffwatch reads as no limit.
    ("rate_limits", {"player": 5, "operator": None,
                     "send": {"per_hour": 60, "per_conversation_hour": 12}}),
    # The page. It is behind a login and served over TLS, but 127.0.0.1 is still the default:
    # it renders raw model thinking, and one hardcoded password is a thin thing to hold a LAN
    # off with. Widening it stays a deliberate edit, made here where it is reviewable.
    ("web_host", "127.0.0.1"),
    ("web_port", 8787),
    # approve_before_send holds every reply at 'pending' until `ffwatch approve <id>` releases
    # it — turn it on for the first days on a live server.
    ("approve_before_send", False),
    ("max_send_attempts", 5),
    # ONE EXAMPLE ROW, NOT A SHIPPED CHANNEL LIST. This block is the only thing in the system
    # that names a channel — ffwatch's DEFAULTS["watch"] is empty on purpose — so what gets
    # seeded here is what a fresh machine reads. It used to seed the four Final Factory
    # channels, which meant every box swept #dev-chat whether or not that box was for it.
    # Rename the example to your channel's alias, or delete it; nothing is watched until you do.
    #
    # venue and engage are declared, never inferred from Discord permissions. See
    # design/trusted_ingress_design.txt sections 4 and 5. The example is deliberately the
    # QUIET, CAUTIOUS pair — public withholds internals, mention wakes nothing unless the bot
    # is addressed — so a half-finished config errs the safe way.
    ("watch", {
        "example_channel": {"kind": "ask", "forum": False, "venue": "public",
                            "engage": "mention", "ping": False},
    }),
    # ONE FILE FOR THE BOX. ffgithubrunners used to keep its own config.json beside its secrets,
    # which meant two templates, two sets of defaults to keep in step, and they had drifted --
    # the runner template still named the image `ffghrunner:latest`, retired when both systems
    # moved to one build. These are lib/config.sh's real defaults, and everything absent from
    # here falls back to that file, so this seeds the knobs an operator turns rather than all
    # forty-odd internal paths.
    #
    # THE FULL SET IS DELIBERATELY NOT HERE. slots and idle_pool are the two anybody changes;
    # the mirror addresses, network names, log directory and daemon root are infrastructure that
    # lib/config.sh owns and nothing should be tempted to fork into a config file.
    # --- what is true of a container whichever lane started it ----------------------------
    # THE SAME LIMITS FOR BOTH LANES, which they did not have until 2026-09-01: a CI job ran
    # under --memory and --pids-limit and an agent run ran under neither, so an agent container
    # was bounded only by the box and one that leaked took the machine with it.
    #
    # memory is a ceiling rather than an allocation -- the workspace tmpfs plus about 32 GB for
    # the editor -- and the tmpfs counts against it, which is the point: a run that fills its
    # ramdrive hits its own limit instead of the host's. A copy of any of these inside
    # "githubrunner" still overrides for CI alone, and nothing seeds one.
    ("container", {
        "workspace_size": "40g",
        "memory": "72g",
        "pids_limit": 4096,
    }),
    ("githubrunner", {
        # THE SAME TWO NUMBERS, and they mean different things. max is the CEILING: the most
        # jobs that can run at once, under the box-wide max_concurrent_runs. idle is the
        # STANDING COST: how many runners sit registered and waiting while nothing is happening.
        # A slot with no container holds no registration and GitHub has never heard of it, so a
        # quiet machine carries idle runners, not max of them.
        "pool": {"idle": 1, "max": 1},
        "watchdog_minutes": 120,
        "image": "ffbox:latest",
        "labels": ["Linux", "X64", "ffgithubrunners"],
        "org": "Final-Factory",
        "runner_group_id": 1,
        # The App's two ids, written here by 04-github.sh. They identify an App, they do not
        # authenticate as one, so they are configuration rather than secrets; the private key is
        # a file beside secrets.env. Null when a PAT is used instead.
        "app_id": None,
        "app_installation_id": None,
        # The container limits are NOT here: memory, pids_limit and workspace_size are the same
        # question for both lanes and live in "container" below. A copy of any of them in this
        # section still overrides, for a machine that wants CI on a different ceiling.
        "machine_id": "per-slot",
        "cache_dir": "/opt/ffcache",
        "cache_keep": 10,
        "cache_quota": "250G",
        "cache_sync": "standard",
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

# WHICH POOL DISCORD TRAFFIC LANDS IN, split by who is speaking. A message whose Discord-
# authenticated author is in trust.operators opens its conversation in operator_pool; everybody
# else opens one in user_pool. Real class names, not blanks, because there is a right answer
# here and a blank would mean "whatever ffwatch's built-in default is" -- the same value, said
# somewhere nobody can see it. setdefault, so a box that has already pointed these somewhere
# else is left alone.
#
# ffagent for strangers is the fenced class (ffbox-net, the egress allowlist, nothing else) and
# ffdev for operators is the unfenced one (the ordinary bridge, the whole internet), so this
# pair is a trust boundary and not a scheduling preference. Pointing user_pool at ffdev hands
# every stranger in the forum a container with the network a developer's shell has.
discord.setdefault("user_pool", "ffagent")
discord.setdefault("operator_pool", "ffdev")

# WHAT EACH VALUE IS. JSON has no comments, and a blank string does not say what shape belongs
# in it — "channels": {"agent_testing": ""} tells you an alias is wanted and nothing about the
# value. Rewritten on every run rather than setdefault: this is generated documentation, so it
# should track the code, not whatever an old run left behind.
discord["_help"] = {
    "app_token": "Discord developer portal > your app > Bot > Reset Token. NOT the "
                 "Application ID and NOT the public key. Better: leave this blank and put "
                 f"FFDISCORD_APP_TOKEN in {os.path.dirname(ffbox_path)}/secrets.env, which "
                 "keeps the secret out of this file (which is why this file is 0600).",
    "server_id": "Right-click the server name > Copy Server ID (Settings > Advanced > "
                 "Developer Mode must be on). Optional: it is inferred when the bot is in "
                 "exactly one server.",
    "channels": "alias -> that channel's id (right-click the channel > Copy Channel ID). The "
                "alias must match an entry in the \"watch\" block at the top level of this "
                "file, which is what says what the channel MEANS; the id here says which "
                "channel it IS. Leave the id blank and the first command that uses the alias "
                "looks it up by name on the server and writes the id back here, so "
                "agent_testing finds #agent-testing on its own. Nothing is watched unless it "
                "is in both tables.",
    "mentions": "name -> user id. What @name expands to in a post.",
    "trust": "operators: name -> user id. Whose messages may command this box. Ids only, "
             "never usernames: a username is renameable, so a trust key somebody else can "
             "claim by renaming is not a trust key. Blank until you fill it in, which means "
             "NOBODY is an operator and every message is treated as a player's.",
    "user_pool": "The agent class a Discord conversation opened by somebody who is NOT in "
                 "trust.operators runs in, and every later turn of it. \"ffagent\", the "
                 "fenced class, unless you have a reason: it is what serves text written by "
                 "strangers, and its network reaches the egress allowlist and nothing else.",
    "operator_pool": "The agent class a Discord conversation opened by an account in "
                     "trust.operators runs in. \"ffdev\", which is unfenced -- the ordinary "
                     "docker bridge, the whole internet -- because an operator directive is "
                     "dev work and is trusted the way a shell on this box is. The class is "
                     "settled by WHO OPENED the conversation and never moves afterwards, so "
                     "an operator answering in a player's thread does not promote it.",
    "example_rows": "Every table above ships one example row so the shape is visible. Rename "
                    "it to the real alias or name and fill in the id, or delete the row. An "
                    "example row is blank, and blank is what every reader treats as absent.",
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
#
# AN EXAMPLE NAME AND A BLANK ID, not real people. Seeding real snowflakes made this box trust
# two specific accounts by default, which is a decision that belongs to whoever runs the box,
# not to the script that installs it. A blank is falsy, and every reader already filters for a
# numeric id, so an unfilled template grants nobody anything: config_warnings says "NOBODY is
# an operator" until a real id is typed in.
#
# The same id is what "@name" expands to in a post, so both tables get the row and there is
# only one place to fill in.
EXAMPLE_OPERATOR = "example_user"
trust = discord.setdefault("trust", {})
operators = trust.setdefault("operators", {})
if not operators:
    operators.setdefault(EXAMPLE_OPERATOR, "")
if not discord["mentions"]:
    discord["mentions"].setdefault(EXAMPLE_OPERATOR, "")

# The ffbox config gets its own one-line map, for the same reason the Discord one does: JSON
# carries no comments, "watch" is the single most consequential block on the machine, and a
# reader should not have to find ffwatch.py to learn what "engage" does.
ffbox["_help"] = {
    "watch": "alias -> {\"kind\": ask|bug_report|suggestion, \"forum\": true for a forum "
             "channel, \"venue\": public|private, \"engage\": all|mention, \"ping\": true "
             "to let a reply there @-mention a human}. THE ONLY PLACE A "
             "CHANNEL IS NAMED — nothing is built in, so this box reads exactly what is listed "
             "here and nothing else. The alias needs a matching row in the \"channels\" "
             "table of the \"discord\" section of this file, which says which channel it IS. "
             "venue private means "
             "internals may be said out loud there; engage mention means only a message that "
             "@-mentions the bot (or replies to it) is considered. Both fall closed when "
             "omitted, and ffwatch logs which entry made it choose. ping is false unless "
             "stated: mark your escalation channel true, and nothing else. AN ALIAS ADDED "
             "HERE IS WATCHED FROM NOW: ffwatch records the moment it appears, and nothing "
             "posted before that can produce a reply. The history is still read and kept as "
             "context for whatever is said next -- it just never gets answered. Taking an "
             "alias back out is recorded too, so putting it back later joins the channel "
             "afresh from that moment rather than from the first time it was listed.",
    "max_concurrent_runs": "The ceiling on CONTAINERS, and it is the box's rather than one "
             "lane's: agent runs, staged pool containers and ffgithubrunners' CI jobs all count "
             "against it. They share a daemon, each holds a workspace of tens of GiB, and RAM is "
             "what runs out. The \"githubrunner\" section's \"slots\" caps how many of its "
             "places may be busy, underneath this one.",
    "container": "The limits every container gets, whichever lane started it. workspace_size "
             "caps the in-RAM workspace; memory is the cgroup ceiling for the whole container "
             "(that workspace plus about 32 GB for the editor, and the tmpfs counts against it, "
             "so a run that fills its ramdrive hits its own limit rather than the host's); "
             "pids_limit bounds runaway process creation. Both lanes hold the same kind of "
             "container on the same daemon, so these are one answer rather than two that drift "
             "-- until 2026-09-01 a CI job had all three and an agent run had none of them. A "
             "copy of any of them inside \"githubrunner\" overrides for CI alone.",
    "ffagent": "What governs a RUN rather than the pipeline around it, flattened over the top "
             "level when ffwatch reads it. base_ref is where a run's clone starts. agent_secs, "
             "warmup_secs and kill_grace_secs are three separate clocks: the model's working "
             "time from the .agent-started marker, everything before it, and how long a "
             "container gets to finish after it is told to stop -- conflating them makes a slow "
             "Unity import look like a hung agent. pool.idle is how many containers fill a "
             "workspace before any request exists (1.2s to dispatch against 40s cold); each one "
             "counts against max_concurrent_runs and holds a Unity seat. pool.max is this lane's own "
             "ceiling on containers, runs and staged ones together, and it sits under the "
             "box-wide max_concurrent_runs -- both have to hold before anything starts. -1 "
             "means no ceiling of its own and is read as max_concurrent_runs, so the default is "
             "to use the whole box while CI is quiet; a negative idle is read as 0, off. Zero "
             "is left alone on both, and means no places. idle_agent_ttl_secs is how long a staged container waits before "
             "retiring, and pool_ref which branch it stages (null follows base_ref). network is "
             "the docker network the container is created on: \"ffbox-net\" is the fenced one, "
             "an --internal bridge whose only other occupant is the egress proxy, so the run "
             "reaches the names in ffbox/egress/allowlist.txt and nothing else -- no LAN and not "
             "this host. ffagent serves text written by strangers, so it stays on it.",
    "ffdev": "The second AGENT CLASS: the same keys as \"ffagent\" and the same meanings, read "
             "for a conversation that was started as ffdev instead. The two sections are "
             "independent -- there is no inheritance, so a box with no \"ffdev\" block here gets "
             "ffwatch's built-in ffdev defaults rather than whatever ffagent is set to, and "
             "editing ffagent's clocks does not move ffdev's. They ship with the same numbers "
             "except the pool AND the network, which is where they already diverge: ffdev's "
             "network is \"bridge\", the ordinary docker bridge, so an ffdev turn has the whole "
             "internet with no allowlist and no SNI filter and can search the web and fetch "
             "packages, while ffagent stays fenced on ffbox-net. That is not the fence minus DNS "
             "filtering, it is no fence -- a container on the bridge reaches this machine's own "
             "LAN address too -- so ffdev is trusted the way a developer's shell on this box is, "
             "and only the class a Discord forum can reach is kept behind the proxy. Each class "
             "is staged into a pool of "
             "its own and holds a ceiling of its own (pool.max), both underneath the box-wide "
             "max_concurrent_runs that CI counts against as well; neither class can take the "
             "other's warm container. A conversation's class is chosen when it is OPENED -- the "
             "dropdown on the web page's new-prompt box, or `ffwatch submit --agent ffdev` -- "
             "and every later turn of that conversation runs in the same kind of container, so "
             "there is no dropdown when replying. A DISCORD conversation has no dropdown "
             "either: it is opened by the \"user_pool\"/\"operator_pool\" pair in the "
             "\"discord\" section, which reads trust.operators to decide whether the account "
             "that opened it is a stranger or an operator. "
             "Set pool.idle to 0 to turn this class's pool off; it still runs, cold, like "
             "ffagent with no pool.",
    "discord": "What the ffdiscord CLI and the Gateway listener read: app_token, server_id, "
             "the channels alias -> id table, mentions, and trust.operators; plus the "
             "user_pool/operator_pool pair, which is ffwatch's and says which agent class a "
             "Discord conversation opens in depending on which side of trust.operators its "
             "author falls. It had a "
             "config.json of its own in the discord/ directory beside this file until "
             "2026-09-01, which put that alias table and the \"watch\" block that gives the "
             "aliases their meaning in two files that had to be edited together. The "
             "directory is still there and still holds Discord STATE: read cursors, the "
             "doorbell, the listener's lock. The section carries its own \"_help\" saying "
             "what each field is, and `ffdiscord set <key> <value>` writes into it.",
    "githubrunner": "ffgithubrunners' settings, which lived in githubrunners/config.json until "
             "2026-09-01 -- one file per box, so there is one place to look. Anything absent "
             "falls back to the default in ffbox/runners/lib/config.sh, and "
             "FFGITHUBRUNNERS_<KEY> in the environment beats both. The two anybody changes are in "
             "\"pool\": max (the ceiling: the most CI jobs at once, under the box-wide "
             "max_concurrent_runs above) and idle (the standing cost: runners registered and "
             "waiting while nothing is happening -- a slot with no container holds no "
             "registration and GitHub has never heard of it). `ffgithubrunners slots N` and "
             "`idle N` write them here. The mirror addresses, network names and daemon paths are NOT "
             "seeded on purpose: they are infrastructure lib/config.sh owns.",
}

# `ping` arrived after boxes were already configured, and stage 5 only seeds "watch" when the
# whole key is absent — so an existing entry would never grow the key, and ping_allowed would
# read a missing key as False. That is the safe direction, but it is also a silent change to
# whichever channel used to be allowed to reach a human. Writing the explicit default makes it
# visible in the file, which is the only place anybody would look for it.
pinged = [a for a, e in sorted((ffbox.get("watch") or {}).items())
          if isinstance(e, dict) and "ping" not in e]
for alias in pinged:
    ffbox["watch"][alias]["ping"] = False

ffbox["discord"] = discord
write(ffbox_path, ffbox)

if renamed:
    print("[discord-setup]   renamed keys: " + ", ".join(renamed))
print("[discord-setup]   seeded keys: " + (", ".join(seeded) or "(nothing new)"))
if pinged:
    print("[discord-setup]   added \"ping\": false to watch entries: " + ", ".join(pinged)
          + "\n[discord-setup]     (a reply there cannot @-mention a human until you set it "
            "true; nothing could, before this key existed on the entry)")
PY
did "$FFBOX_CONFIG_JSON        (ffwatch, ffweb, the runners, and the \"discord\" section)"
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
    say "  2. Fill in the blanks below. Every one of them is already a key in the"
    say "     \"discord\" section of $FFBOX_CONFIG_JSON, waiting empty, and that"
    say "     section's \"_help\" block says what each value is:"
    blanks || true
    say "     (Discord: Settings > Advanced > Developer Mode, then right-click to copy an id.)"
    say "     app_token is the Bot tab's Reset Token, NOT the Application ID or public key."
    say "     Channel ids: once app_token is set, re-run this script and it looks them up by"
    say "     name, or do it directly with 'ffdiscord resolve-channels --write'."
    say "  3. Watching a channel this box does not know about yet? Add it to the ffwatch"
    say "     \"watch\" block in the same file first, which is what says what it MEANS:"
    say '       "watch": { "agent_testing": { "kind": "ask", "forum": false, "venue": "private",'
    say '                                     "engage": "mention", "ping": false } }'
    say "     kind says what the channel IS (ask, bug_report, suggestion); every turn gets the"
    say "     same capabilities whichever it is. A channel NOT listed here produces no events"
    say "     at all — the watch block is the list. Re-run this script to get its blank."
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
