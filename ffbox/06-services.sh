#!/bin/sh
# 06-services.sh — install and start the ffbox services.
#
#   sh ffbox/06-services.sh              report what is installed, enabled and running
#   sudo sh ffbox/06-services.sh --install
#                                        render the units from this checkout into
#                                        /etc/systemd/system, start ffbox.target, enable it
#   sudo sh ffbox/06-services.sh --install --no-enable
#                                        install them but leave them stopped
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
# --install is meant to be run under sudo, and under sudo $HOME and `id -un` are root's. The
# units have to describe the user who actually owns the checkout, the docker group and the
# Claude credential, so recover that identity from SUDO_USER.
RUN_USER=$(id -un)
if [ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
    RUN_USER=$SUDO_USER
    HOME=$(getent passwd "$RUN_USER" | cut -d: -f6)
    HOME=${HOME%/}
fi
RUN_GROUP=$(id -gn "$RUN_USER")
FFBOX_CONFIG=$HOME/.config/ffbox
FFDISCORD_HOME=${FFDISCORD_HOME:-$FFBOX_CONFIG/discord}
FFBOX_CONFIG_JSON=$FFBOX_CONFIG/config.json

INSTALL=0
NO_ENABLE=0
for arg in "$@"; do
    case "$arg" in
        --install)    INSTALL=1 ;;
        --no-enable)  NO_ENABLE=1 ;;
        -h|--help)    sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)            echo "06-services.sh: unknown option $arg" >&2; exit 2 ;;
    esac
done

say()  { printf '[services] %s\n' "$*"; }
did()  { printf '[services]   %s\n' "$*"; }

UNIT_NAMES="ffbox.target ffdiscord-listener.service ffwatch.service ffweb.service"

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


cfg = read(os.environ["FFBOX_CONFIG_JSON"])
block = dict(cfg)
block.update(cfg.get("ffwatch") or {})
if "watch" not in block:                      # a machine that predates the config split
    block = (read(os.environ["LEGACY"]).get("ffwatch") or {})
print(",".join(sorted(block.get("watch") or {})) or "ask_claude,bug_reports")
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
    _webhost=$(web_bind | cut -d' ' -f1)
    _webport=$(web_bind | cut -d' ' -f2)
    mkdir -p "$_dest"
    for u in $UNIT_NAMES; do
        sed -e "s|@FFWATCH@|$HERE/ffwatch.py|g" \
            -e "s|@FFWEB@|$HERE/ffweb.py|g" \
            -e "s|@USER@|$RUN_USER|g" \
            -e "s|@GROUP@|$RUN_GROUP|g" \
            -e "s|@HOME@|$HOME|g" \
            -e "s|@CHANNELS@|$_channels|g" \
            -e "s|@FFDHOME@|$FFDISCORD_HOME|g" \
            -e "s|@WEBHOST@|$_webhost|g" \
            -e "s|@WEBPORT@|$_webport|g" \
            "$HERE/systemd/$u" > "$_dest/$u"
    done
}

if [ "$INSTALL" = 1 ]; then
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

# --- no --install: report ------------------------------------------------------------------
if ! command -v systemctl >/dev/null 2>&1; then
    say "no systemctl here. Run the daemons yourself:"
    did "ffdiscord-listener --channels $(watched_channels)"
    did "python3 $HERE/ffwatch.py run"
    did "python3 $HERE/ffweb.py"
    exit 0
fi

say "units in $UNIT_DIR  (source: $HERE/systemd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
render_units "$TMP"
STALE=0
for u in $UNIT_NAMES; do
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
    did "sudo systemctl restart ffbox.target"
else
    did "web UI: http://$(web_bind | cut -d' ' -f1):$(web_bind | cut -d' ' -f2)"
    did "logs:   journalctl -u ffwatch -f   (or -u ffdiscord-listener, -u ffweb)"
fi
