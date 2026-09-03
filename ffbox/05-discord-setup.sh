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
# EVERYTHING ffbox owns on this machine lives under one directory:
#
#   ~/.config/ffbox/secrets.env        tokens and the Unity account
#   ~/.config/ffbox/config.json        ffwatch, ffweb, the CI runners, and the "discord"
#                                      section: token, server, channels, mentions, trust,
#                                      and which agent pool each side of that trust gets
#   ~/.config/ffbox/discord/           the Discord CLI's STATE, and only state: the read
#                                      cursors, the doorbell, the listener lock
#   ~/.config/ffbox/discord.disabled   the kill switch
#
# ONE CONFIG FILE, and the alias table sits in it beside the "watch" block that gives those
# aliases their meaning: two files where one is read and the other is edited is the worst
# outcome available.
FFBOX_CONFIG=$HOME/.config/ffbox
FFDISCORD_HOME=${FFDISCORD_HOME:-$FFBOX_CONFIG/discord}
FFBOX_CONFIG_JSON=$FFBOX_CONFIG/config.json
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
# A key is filled if the file has it OR the environment does: the units read secrets.env
# through EnvironmentFile=, so a token living only there is configured even though the JSON
# blank is still empty.
def filled(key, *env_names):
    if str(discord.get(key) or "").strip():
        return True
    return any(os.environ.get(e) or in_secrets(e) for e in env_names)


if not filled("app_token", "FFDISCORD_APP_TOKEN"):
    missing += out("app_token", "FFDISCORD_APP_TOKEN=<bot token> in secrets.env, "
                                "or: ffdiscord set app_token <bot token>")

# Not counted as missing: ffdiscord infers the guild when the bot is in exactly one, so a box
# that never sets it still works. Reported anyway, because inference is not something you want
# to discover the day a second guild appears.
if not filled("server_id", "FFDISCORD_SERVER_ID"):
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

# --- the Discord CLI's state directory ------------------------------------------------------
# STATE ONLY: the listener's read cursors, the doorbell socket and the listener lock. There is
# no config here — the "discord" section of the file above is the whole of it.
mkdir -p "$FFDISCORD_HOME"
chmod 700 "$FFDISCORD_HOME" 2>/dev/null || true

FFBOX_CONFIG_JSON="$FFBOX_CONFIG_JSON" python3 - <<'PY'
import json
import os

# ONE FILE FOR THE BOX: ~/.config/ffbox/config.json.
#   top level + "pools" + "container"     ffwatch and ffweb: pools, ceilings, the page's bind
#   "githubrunner"                        the CI runner pool
#   "discord"                             the Discord CLI's own: token, server, channels,
#                                         mentions, trust -- plus user_pool/operator_pool,
#                                         ffwatch's, which read that trust table
#
# ONE FILE, ONE READ, ONE PLACE TO LOOK. The "channels" alias table and the "watch" block that
# gives those aliases their meaning belong in the same document: split across two, they could
# disagree, and every reader had to open both and decide which won.


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
    # --- the pools --------------------------------------------------------------------------
    # ONE SECTION HOLDING ONE BLOCK PER AGENT CLASS, since 2026-09-02. Everything that governs a
    # RUN rather than the pipeline around it: the clocks it is held to, the branch its workspace
    # starts from, the warm pool it may be dispatched into, and the network it is put on.
    # ffwatch flattens the ffagent block over the top level, so a key here is read exactly as it
    # was before it moved.
    #
    # The two blocks sat at the top level of this file beside "watch" and "web_port" until the
    # move, which read as though a pool were another pipeline setting.
    ("pools", {
      "ffagent": {
        # Where a run's clone starts. Must match the first key of ffwatch's publish_bases,
        # which is what the agent is told to branch from by default; disagreeing costs a
        # cross-base checkout and a full Unity reimport inside every container.
        "base_ref": "master",
        # FOUR CLOCKS, and conflating them makes a slow Unity import look like a hung agent.
        # They run in this order and each is measured from its own marker, so a run can spend
        # all of every one of them:
        #   warmup_secs   from `docker run`: clone, container start, Unity activation, the
        #                 Library delta. A staged spare has already paid it.
        #   agent_secs    the model's working time, from <out>/.agent-started -- the number a
        #                 person waiting on a reply is actually waiting on.
        #   verify_secs   the harness's own EditMode run afterwards, from <out>/.verify-started.
        #                 Its own clock since it landed, so a fifteen-minute test suite is never
        #                 charged to the agent's budget and recorded as a hung agent; per pool
        #                 since 2026-09-03, so a dev lane can allow a longer suite than the
        #                 player-facing one without moving the other lane's number.
        #   kill_grace_secs   how long a container gets to finish after it is told to stop.
        #                 FLOORED AT 120 wherever a Unity seat may be held (see
        #                 lib-workloads.sh's FFBOX_LICENCE_STOP_FLOOR), because PID 1's trap
        #                 hands the licence back and that is an editor launch. Lowering this
        #                 below 120 cannot strand a seat; raising it above 120 is honoured.
        #
        # ALL FOUR APPLY TO CONTAINERS MADE AFTERWARDS, NEVER RETROACTIVELY. A run is created
        # with its ceilings written into <out>/clock, and that file is what the host compares
        # against for the life of the run -- so editing a number here changes the next run and
        # not the one that is working now. The same is true of the network, the capability list
        # and the workspace size, all of which are fixed when a container is created; a run that
        # is carried across an update keeps everything it started with. This is deliberate: a
        # clock that could be shortened underneath a working run would be a way to kill it by
        # editing a file.
        "agent_secs": 1800,
        "warmup_secs": 3600,
        "verify_secs": 1800,
        "kill_grace_secs": 10,
        # THE POOL, in the same shape the runners use. idle is how many containers fill a
        # workspace before any request exists, so one that arrives finds a warm one: 1.2s from
        # dispatch to the agent starting, against 40s cold, and 0 is off. Each staged container
        # counts against max_concurrent_runs above AND holds a Unity seat, taken after it syncs
        # and before it goes idle.
        #
        # max is THIS POOL's ceiling on containers, runs and staged ones together, underneath
        # the box-wide max_concurrent_runs that CI counts against too. Both have to hold: the
        # pool cap stops one class filling a shared box on its own, the box cap stops the pools
        # together overcommitting it.
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
        # THE FENCE, and the word says the policy rather than a docker network name -- ffwatch
        # is the one place that knows "limited" means ffbox-net, a Docker --internal bridge with
        # no default route whose only other occupant is the egress proxy. A run on it reaches
        # the names in ffbox/egress/allowlist.txt and nothing else, no LAN and not this host.
        # ffagent serves text written by strangers in a Discord forum, so this is the pool that
        # stays shut.
        "network": "limited",
      },
      # THE SECOND AGENT CLASS. Same keys as "ffagent" above and the same meanings: the two are
      # separate blocks with no inheritance between them, so ffdev reads THIS and never
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
      "ffdev": {
        "base_ref": "master",
        "agent_secs": 1800,
        "warmup_secs": 3600,
        "verify_secs": 1800,
        "kill_grace_secs": 10,
        "pool": {"idle": 1, "max": 3},
        "idle_agent_ttl_secs": 14400,
        "pool_ref": None,
        # NO FENCE, DELIBERATELY. "full" is the ordinary NATted docker bridge: the whole
        # internet, no allowlist, no SNI filter. A dev turn has to be able to read documentation,
        # search the web and fetch a package, and an allowlist that must be edited every time it
        # needs a new host is not a fence, it is a queue.
        #
        # Know what it costs before changing ffagent to match: this is not the fence minus DNS
        # filtering, it is no fence. A container on the bridge also reaches this machine's own
        # LAN address -- measured 2026-08-25, port 22 answered -- because rootless Docker
        # disables the host loopback and not the host's IP. ffdev is trusted the way a
        # developer's shell on this box is trusted, which is what it is for.
        "network": "full",
      },
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
    # ONE KEY OUT OF THE CLUSTERING BLOCK, and deliberately not the other seven. ffwatch
    # deep-merges this section, so a config naming one key inherits the rest of DEFAULTS
    # ["cluster"] rather than replacing it -- which means the shipped file can put the one
    # tunable a person actually reaches for on page and leave the candidacy arithmetic to the
    # code. This is how often a long-running conversation's session is compacted, counted in
    # turns from the last seam: past it the turn runs /compact against the session it was about
    # to resume, and then resumes it. Overridable per `watch` entry, like everything in here.
    ("cluster", {"compact_turns": 12}),
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
        #
        # machine_id IS NOT SEEDED EITHER, and it used to be, as "per-slot". That was the
        # default when this seeding was written and it stopped being one hours later, on the
        # same day. The box now activates ONE Unity Personal licence on the HOST, against the
        # pinned constant in lib/config.sh, and every container mounts that one .ulf -- a .ulf
        # binds to exactly one /etc/machine-id, so a container presenting a per-slot id would
        # match nothing and find no entitlement. (The activation itself is online and has to be:
        # Unity withdrew manual activation for Personal licences in 2023. See "Unity licensing"
        # in ffbox/README.md.) It is infrastructure lib/config.sh owns, like the mirror
        # addresses, so the file should not carry a second answer to it at all.
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
# app_token and server_id match what a HUMAN is looking at rather than what the API says: the
# developer portal issues an app and its bot token, and the Discord client has called a guild a
# server for years. Discord's own paths still say "guild", which is why /guilds/... is all over
# the CLI — the names here cover what somebody types, not what goes on the wire.
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
# ffagent for strangers is the "limited" pool (behind the egress fence, the allowlist, nothing
# else) and ffdev for operators is the "full" one (the whole internet, no filter), so this pair
# is a trust boundary and not a scheduling preference. Pointing user_pool at ffdev hands every
# stranger in the forum a container with the network a developer's shell has.
discord.setdefault("user_pool", "ffagent")
discord.setdefault("operator_pool", "ffdev")

# THE HELP IS NOT IN THE FILE, since 2026-09-03. There were two generated "_help" blocks, one
# here and one at the top level, rewritten on every run: between them they were longer than
# every value they described, and a paragraph of prose stored as a JSON string is close to
# unreadable in the one place it lives. ffbox/config.md is the reference now, and it covers
# every key in the file rather than the ones somebody had got round to writing a line for.
#
# POPPED RATHER THAN LEFT ALONE, so a box configured before the move loses the stale copy on
# the next run instead of carrying documentation that no longer tracks the code. Nothing reads
# it either way -- ffwatch drops top-level keys it does not know, and lib/config.sh skips any
# key starting with an underscore -- so this is only about what a human opens the file to.
stripped_help = [name for name, block in (("discord", discord), ("top level", ffbox))
                 if block.pop("_help", None) is not None]

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

print("[discord-setup]   seeded keys: " + (", ".join(seeded) or "(nothing new)"))
if stripped_help:
    print("[discord-setup]   removed the generated \"_help\" block from: "
          + ", ".join(stripped_help)
          + "\n[discord-setup]     (every setting is documented in ffbox/config.md now)")
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
    say "     \"discord\" section of $FFBOX_CONFIG_JSON, waiting empty, and"
    say "     $HERE/config.md says what each value is:"
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
