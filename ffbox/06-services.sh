#!/bin/sh
# 06-services.sh — install and start the ffbox services.
#
#   sh ffbox/06-services.sh              report what is installed, enabled and running
#   sudo sh ffbox/06-services.sh --install
#                                        render the units from this checkout into
#                                        /etc/systemd/system, start ffbox.target, enable it
#   sudo sh ffbox/06-services.sh --install --no-enable
#                                        install them but leave them stopped
#   sh ffbox/06-services.sh --check      exit 1 if installing would change anything (no root)
#   sudo sh ffbox/06-services.sh --install --force
#                                        install from a checkout that is NOT the one this
#                                        machine is recorded as running from, and make it the
#                                        one it runs from. See THE RECORDED CHECKOUT below.
#
# WHY THIS IS ITS OWN STAGE. The units are ffbox's, not Discord's: ffwatch is the conversation
# manager, ffweb is the page over the whole database, and only the listener is Discord-specific.
# They belong to the product, so a machine that later grows another front door does not have to
# find its unit definitions inside a script named for one of them.
#
# THE TEMPLATES IN ffbox/systemd/ ARE THE ONLY SOURCE. They are rendered into a throwaway
# directory and installed from there; nothing rendered is kept beside the config, because a
# second copy on disk is a second thing that can disagree with git. Rendering never needs root
# — only installing does.
#
# POSIX sh, like its siblings.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

HOME=${HOME%/}
UNIT_DIR=/etc/systemd/system
# WHO THE UNITS MUST DESCRIBE. Run as root, $HOME and `id -un` are root's, but the units have to
# name the user who actually owns the checkout, the rootless Docker daemon and the Claude
# credential. That user's uid is also what @DOCKERSOCK@ is built from.
#
# THREE SOURCES, most explicit first, because SUDO_USER alone is not enough:
#   FFBOX_RUN_USER  passed by a caller that already knows. ffbox-update.service runs this as
#                   root from systemd, where there is NO SUDO_USER at all — so the sudo branch
#                   below never fired and every automatic re-install rendered @USER@=root and
#                   @HOME@=/root: units pointing at a home with no config, no token and no
#                   checkout. Latent for as long as unit templates only changed by hand.
#   SUDO_USER       a human typing `sudo sh ffbox/06-services.sh --install`.
#   checkout owner  the last resort, and the same answer update_ffbox.sh derives for its git
#                   calls. If root really does own the checkout this resolves to root, which is
#                   then correct rather than a fallback.
RUN_USER=$(id -un)
if [ "$(id -u)" = 0 ]; then
    _who=${FFBOX_RUN_USER:-}
    if [ -z "$_who" ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
        _who=$SUDO_USER
    fi
    if [ -z "$_who" ]; then
        _who=$(stat -c %U "$HERE/../.git" 2>/dev/null || stat -c %U "$HERE/.." 2>/dev/null || echo root)
    fi
    if [ -n "$_who" ] && [ "$_who" != root ]; then
        RUN_USER=$_who
        HOME=$(getent passwd "$RUN_USER" | cut -d: -f6)
        HOME=${HOME%/}
    fi
fi
RUN_GROUP=$(id -gn "$RUN_USER")
FFBOX_CONFIG=$HOME/.config/ffbox
FFDISCORD_HOME=${FFDISCORD_HOME:-$FFBOX_CONFIG/discord}

# THE RECORDED CHECKOUT.
#
# registerAgents.sh writes the path of the checkout this machine runs from into
# ~/.claude/final-factory-agents-checkout. This guard exists because the units carry ABSOLUTE
# paths rendered from $HERE, so --install from the wrong clone silently repoints ffwatch, ffweb,
# the egress fence and the self-updater at that clone. Nothing complains afterwards: --check
# compares the installed units against whichever checkout you invoke it from, so it says
# "current" from the wrong one and "drift" from the right one, and neither answer names which is
# meant to be canonical.
#
# That happened on 2026-08-25. A machine with four clones of this repo spent an afternoon running
# from a scratch one because an install was run from the wrong working directory.
#
# HOME is the OWNER's here, not root's — the block above resolves it before this point, which is
# what makes the file readable at all under sudo.
REPO_ROOT=$(CDPATH= cd -- "$HERE/.." && pwd)
RECORDED_FILE="$HOME/.claude/final-factory-agents-checkout"

# The recorded path, canonicalised, or non-zero when there is nothing recorded. Canonicalised
# because a symlink or a trailing slash is the same checkout and must not read as a different one.
recorded_checkout() {
    [ -r "$RECORDED_FILE" ] || return 1
    _rec=$(head -n1 "$RECORDED_FILE" 2>/dev/null | tr -d ' \t\r\n')
    [ -n "$_rec" ] || return 1
    (CDPATH= cd -- "$_rec" 2>/dev/null && pwd) || printf '%s\n' "${_rec%/}"
}
FFBOX_CONFIG_JSON=$FFBOX_CONFIG/config.json

INSTALL=0
NO_ENABLE=0
CHECK=0
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --install)    INSTALL=1 ;;
        --no-enable)  NO_ENABLE=1 ;;
        --check)      CHECK=1 ;;
        --force)      FORCE=1 ;;
        -h|--help)    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)            echo "06-services.sh: unknown option $arg" >&2; exit 2 ;;
    esac
done

say()  { printf '[services] %s\n' "$*"; }
did()  { printf '[services]   %s\n' "$*"; }

UNIT_NAMES="ffbox.target ffdiscord-listener.service ffwatch.service ffweb.service"
# The updater is rendered and installed with the rest, but it is NOT part of ffbox.target
# and is enabled separately — it has to survive a broken ffbox to be able to fix one.
# See design/self_update_design.txt section 3.
UPDATE_UNITS="ffbox-update.service ffbox-update.timer"
# Same treatment, same reason, different lifetime: the egress filter is what keeps a run off this
# host and off the internet, so it is enabled outside ffbox.target and a stop of the target
# leaves it standing.
EGRESS_UNITS="ffbox-egress.service"
# The rootless Docker gate. First in every loop below, because everything else that touches
# docker orders after it. Not part of ffbox.target either: a stop of the pipeline should not
# un-gate it. See design/rootless_docker_design.txt section 6.
DOCKER_UNITS="ffbox-docker.service"

# The listener watches whatever the config says to watch. Reading it back from the ffwatch block
# means adding a channel there and re-installing is enough — no second place to edit, and no
# unit quietly watching a channel the classifier no longer knows about.
# The page's bind address, from the same config block, so the unit and a by-hand run agree.
web_bind() {
    FFBOX_CONFIG_JSON="$FFBOX_CONFIG_JSON" LEGACY="$FFDISCORD_HOME/config.json" python3 - <<'PY'
import json, os


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


cfg = read(os.environ["FFBOX_CONFIG_JSON"])
block = dict(read(os.environ["LEGACY"]).get("ffwatch") or {})   # the pre-split location
block.update(cfg)
block.update(cfg.get("ffwatch") or {})
print("%s %s" % (block.get("web_host") or "127.0.0.1", block.get("web_port") or 8787))
PY
}

watched_channels() {
    FFBOX_CONFIG_JSON="$FFBOX_CONFIG_JSON" LEGACY="$FFDISCORD_HOME/config.json" python3 - <<'PY'
import json, os


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


legacy = read(os.environ["LEGACY"])
cfg = read(os.environ["FFBOX_CONFIG_JSON"])
block = dict(cfg)
block.update(cfg.get("ffwatch") or {})
if "watch" not in block:                      # a machine that predates the config split
    block = (legacy.get("ffwatch") or {})

# No fallback list. A default channel here is one nobody chose and everybody inherits, which
# is the bug this whole path was rewritten to remove: the watch block is the only thing that
# names a channel. Empty prints nothing, and render_units drops the flag entirely.
#
# Only aliases that ALREADY RESOLVE are rendered. The listener exits 2 on an alias it cannot
# turn into a snowflake, and systemd would restart it into that same exit until StartLimitBurst
# gave up — so a template whose ids are still blank (the example row, a channel added to watch
# an hour before anyone copied its id) would take the whole doorbell down, mentions and
# operator DMs included, rather than degrade. Those aliases are listed by `blanks` and in
# MANUAL STEPS; they are not a reason for the daemon to be dead.
channels = legacy.get("channels") or {}
ready = [a for a in sorted(block.get("watch") or {})
         if str(channels.get(a) or "").strip().isdigit()]
print(",".join(ready))
PY
}

# THE TEMPLATES IN ffbox/systemd/ ARE THE ONLY SOURCE. They are rendered into a throwaway
# directory and installed from there; nothing rendered is ever kept beside the config, because a
# second copy on disk is a second thing that can disagree with git. @PLACEHOLDERS@ exist because
# this repo can be cloned anywhere and a wrong ExecStart fails at unit start with a message
# nobody reads. Rendering never needs root — only installing does.
render_units() {
    _dest=$1
    # The whole ARGUMENT, not just its value: an empty watch block must render an ExecStart
    # with no --channels at all, because `--channels` with nothing after it is an argparse
    # error and the unit would crash-loop instead of watching nothing.
    _channels=$(watched_channels)
    if [ -n "$_channels" ]; then
        _channels_arg="--channels $_channels"
    else
        _channels_arg=""
    fi
    _webhost=$(web_bind | cut -d' ' -f1)
    _webport=$(web_bind | cut -d' ' -f2)
    # The rootless daemon's socket carries the OWNER's uid, not this process's: --install runs
    # under sudo, so `id -u` here would be 0 and every unit would point at root's runtime
    # directory, which does not exist. Ask for the uid of the user the units run as.
    _uid=$(id -u "$RUN_USER" 2>/dev/null || echo "")
    if [ -z "$_uid" ]; then
        echo "06-services.sh: cannot resolve a uid for '$RUN_USER'" >&2
        exit 1
    fi
    _dockersock="/run/user/$_uid/docker.sock"
    mkdir -p "$_dest"
    for u in $DOCKER_UNITS $UNIT_NAMES $UPDATE_UNITS $EGRESS_UNITS; do
        sed -e "s|@FFWATCH@|$HERE/ffwatch.py|g" \
            -e "s|@UPDATE@|$HERE/update_ffbox.sh|g" \
            -e "s|@EGRESS@|$HERE/egress/ffbox-egress.sh|g" \
            -e "s|@REPO@|$(CDPATH= cd -- "$HERE/.." && pwd)|g" \
            -e "s|@FFWEB@|$HERE/ffweb.py|g" \
            -e "s|@USER@|$RUN_USER|g" \
            -e "s|@GROUP@|$RUN_GROUP|g" \
            -e "s|@HOME@|$HOME|g" \
            -e "s|@CHANNELS_ARG@|$_channels_arg|g" \
            -e "s|@FFDHOME@|$FFDISCORD_HOME|g" \
            -e "s|@WEBHOST@|$_webhost|g" \
            -e "s|@WEBPORT@|$_webport|g" \
            -e "s|@DOCKERSOCK@|$_dockersock|g" \
            -e "s|@WAITDOCKER@|$HERE/wait-for-docker.sh|g" \
            "$HERE/systemd/$u" > "$_dest/$u"
    done
}

# --check answers ONE question, in an exit code: would installing right now change anything.
#
# It exists because the rendered units depend on the CONFIG as well as on this checkout — the
# listener's --channels comes from the ffwatch watch block — so "did any file in git change"
# cannot answer it. Somebody adding a channel by hand leaves the units stale with no commit to
# notice, and the symptom is a listener still watching yesterday's channels. The updater runs
# this on every pass and reinstalls when it says so.
#
# No root needed: rendering is free, and only installing writes.
if [ "$CHECK" = 1 ]; then
    TMP=$(mktemp -d)
    trap 'rm -rf "$TMP"' EXIT
    render_units "$TMP"
    _drift=""
    for u in $DOCKER_UNITS $UNIT_NAMES $UPDATE_UNITS $EGRESS_UNITS; do
        if [ ! -f "$UNIT_DIR/$u" ]; then
            _drift="$_drift $u(missing)"
        elif ! cmp -s "$UNIT_DIR/$u" "$TMP/$u"; then
            _drift="$_drift $u"
        fi
    done
    if _rec=$(recorded_checkout) && [ "$_rec" != "$REPO_ROOT" ]; then
        # Without this the exit code is answering a question nobody asked: drift against a
        # checkout the machine does not run from is expected, not a problem to fix.
        say "NOTE: this checkout ($REPO_ROOT) is not the recorded one ($_rec)."
        say "      Any drift below is drift against a clone the machine does not run from."
    fi
    if [ -n "$_drift" ]; then
        say "units differ from what this checkout and config render:$_drift"
        exit 1
    fi
    say "units are current"
    exit 0
fi

if [ "$INSTALL" = 1 ]; then
    if _rec=$(recorded_checkout); then
        if [ "$_rec" != "$REPO_ROOT" ] && [ "$FORCE" = 0 ]; then
            say "REFUSING: this is not the checkout this machine runs from."
            say "  this checkout: $REPO_ROOT"
            say "  recorded:      $_rec"
            say "The units carry absolute paths, so installing from here would repoint ffwatch,"
            say "ffweb, the egress fence and the self-updater at this directory. Either install"
            say "from the recorded checkout:"
            say "  sudo sh $_rec/ffbox/06-services.sh --install"
            say "or, to make THIS one what the machine runs from, say so and then record it:"
            say "  sudo sh $HERE/06-services.sh --install --force"
            say "  sh $REPO_ROOT/registerAgents.sh"
            exit 1
        fi
        if [ "$_rec" != "$REPO_ROOT" ]; then
            say "WARNING: --force — repointing the runtime from $_rec to $REPO_ROOT."
            say "         Run 'sh $REPO_ROOT/registerAgents.sh' afterwards, or the recorded"
            say "         path stays wrong and the next install refuses for the wrong reason."
        fi
    else
        say "nothing recorded at $RECORDED_FILE — installing from $REPO_ROOT"
    fi
    if [ "$(id -u)" != 0 ]; then
        say "--install writes to $UNIT_DIR and needs root. Run:"
        say "  sudo sh $HERE/06-services.sh --install"
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
        (cd "$TMP" && systemd-analyze verify ./ffbox.target ./*.service ./*.timer 2>&1 \
            | grep -E 'ffbox|ffwatch|ffweb|ffdiscord' \
            | sed 's/^/[discord-setup]   verify: /') || true
    fi
    # WHICH UNITS ACTUALLY CHANGED, and which were already running, decided BEFORE the files
    # are overwritten. `systemctl enable --now` starts what is stopped; it does NOT restart what
    # is already running, so without this a re-install leaves the old process alive with the old
    # command line — which is exactly how ffweb stayed on 127.0.0.1 through two correct installs.
    CHANGED=""
    WAS_ACTIVE=""
    for u in $DOCKER_UNITS $UNIT_NAMES $UPDATE_UNITS $EGRESS_UNITS; do
        cmp -s "$TMP/$u" "$UNIT_DIR/$u" 2>/dev/null || CHANGED="$CHANGED $u"
        case "$u" in
            *.target) continue ;;
        esac
        systemctl is-active --quiet "$u" 2>/dev/null && WAS_ACTIVE="$WAS_ACTIVE $u"
    done

    for u in $DOCKER_UNITS $UNIT_NAMES $UPDATE_UNITS $EGRESS_UNITS; do
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
        # SEPARATELY, and on purpose: enabling the timer through ffbox.target would tie the
        # updater's lifetime to the thing it updates. A stop of the target must leave this
        # firing, because a bad commit that stops ffwatch is exactly when the next one matters.
        # Before the pipeline, not after: ffwatch's first sweep can launch a container, and that
        # container has nowhere to resolve a name from until this is up.
        # BEFORE egress and before the pipeline: both talk to the rootless daemon, and this is
        # the unit that knows whether the daemon is there at all. A failure here is the one
        # worth reading, so let it be the first thing that fails.
        systemctl enable --now ffbox-docker.service \
            || did "WARNING: ffbox-docker.service failed — the rootless daemon is not answering.
                    Nothing below this line will work. $HERE/wait-for-docker.sh says why."
        did "enabled ffbox-docker.service (waits for the rootless Docker socket)"
        systemctl enable --now ffbox-egress.service \
            || did "WARNING: ffbox-egress.service failed — ffbox will refuse to start a run"
        did "enabled ffbox-egress.service (internal network + SNI allowlist)"
        systemctl enable --now ffbox-update.timer
        did "enabled ffbox-update.timer (fetch + fast-forward + restart, every 5min)"
        did "  next update check: $(systemctl show ffbox-update.timer -p NextElapseUSecRealtime --value 2>/dev/null)"
        # Restart only what changed AND was already up: a unit just started by enable --now is
        # already running the new file, and ffwatch in particular should not be interrupted for
        # nothing — a restart terminal-fails any run in flight, which the recovery pass then
        # requeues.
        for u in $CHANGED; do
            case " $WAS_ACTIVE " in
                *" $u "*)
                    systemctl restart "$u"
                    did "restarted $u — its unit changed while it was running"
                    ;;
            esac
        done
        for u in ffdiscord-listener.service ffwatch.service ffweb.service; do
            did "  $u: $(systemctl is-active "$u" 2>/dev/null | head -1)"
        done
        did "stop everything:  sudo systemctl stop ffbox.target"
        did "logs:             journalctl -u ffwatch -f"
    fi
    exit 0
fi

# --- no --install: report ------------------------------------------------------------------
if ! command -v systemctl >/dev/null 2>&1; then
    say "no systemctl here. Run the daemons yourself:"
    _c=$(watched_channels)
    did "ffdiscord-listener${_c:+ --channels $_c}"
    did "python3 $HERE/ffwatch.py run"
    did "python3 $HERE/ffweb.py"
    exit 0
fi

say "units in $UNIT_DIR  (source: $HERE/systemd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
render_units "$TMP"
STALE=0
for u in $DOCKER_UNITS $UNIT_NAMES $UPDATE_UNITS $EGRESS_UNITS; do
    st=$([ -f "$UNIT_DIR/$u" ] && echo installed || echo 'NOT INSTALLED')
    if [ -f "$UNIT_DIR/$u" ]; then
        st="$st, $(systemctl is-enabled "$u" 2>/dev/null | head -1 || echo unknown)"
        st="$st, $(systemctl is-active "$u" 2>/dev/null | head -1 || echo inactive)"
        # Re-rendering is free; installing needs root. An installed unit can therefore lag
        # behind a config change silently, and the symptom is a listener still watching
        # yesterday's channels.
        if ! cmp -s "$UNIT_DIR/$u" "$TMP/$u"; then
            st="$st, STALE (differs from what this checkout renders)"
            STALE=1
        fi
    fi
    did "$u: $st"
done

if [ ! -f "$UNIT_DIR/ffbox.target" ]; then
    say "NEXT: install and start them with"
    did "sudo sh $HERE/06-services.sh --install"
elif [ "$STALE" = 1 ]; then
    say "NEXT: the installed units no longer match this checkout. Re-install with"
    did "sudo sh $HERE/06-services.sh --install"
else
    did "web UI: https://$(web_bind | cut -d' ' -f1):$(web_bind | cut -d' ' -f2)  (sign in as Ben or Lothsahn)"
    did "logs:   journalctl -u ffwatch -f   (or -u ffdiscord-listener, -u ffweb)"
    did "update: $(systemctl is-active ffbox-update.timer 2>/dev/null || echo inactive), next $(systemctl show ffbox-update.timer -p NextElapseUSecRealtime --value 2>/dev/null || echo '?')"
    did "        sudo systemctl start ffbox-update.service   (update now)"
fi

# A unit file newer than the process running under it means somebody installed and did not
# restart. systemd reports that as "active" and nothing else complains, so the daemon serves the
# OLD configuration indefinitely — which is how ffweb stayed on 127.0.0.1 through two correct
# installs. --install restarts what it changes now; this catches the hand-edited case.
for u in ffdiscord-listener.service ffwatch.service ffweb.service; do
    [ -f "$UNIT_DIR/$u" ] || continue
    systemctl is-active --quiet "$u" 2>/dev/null || continue
    started=$(systemctl show "$u" -p ActiveEnterTimestamp --value 2>/dev/null)
    [ -n "$started" ] || continue
    started_epoch=$(date -d "$started" +%s 2>/dev/null || echo 0)
    unit_epoch=$(stat -c %Y "$UNIT_DIR/$u" 2>/dev/null || echo 0)
    if [ "$unit_epoch" -gt "$started_epoch" ] 2>/dev/null; then
        say "WARNING: $u is running with an OLDER unit than the one installed."
        did "it started $started; the unit file is newer. Restart it with"
        did "  sudo systemctl restart $u"
    fi
done
