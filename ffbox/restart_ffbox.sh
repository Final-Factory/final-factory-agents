#!/bin/sh
# restart_ffbox.sh — restart the whole ffbox pipeline.
#
#   sh ffbox/restart_ffbox.sh            restart listener + ffwatch + ffweb, then report
#
# ONE HANDLE, BECAUSE THE THREE ARE ONE PRODUCT. ffbox.target Wants= all three and each unit
# carries PartOf=ffbox.target, so restarting the target propagates down. Note the `.target`
# suffix: a bare `systemctl restart ffbox` looks for ffbox.SERVICE, which does not exist.
#
# THIS IS THE STEP THAT PUBLISHES A CODE CHANGE. The units run this checkout's ffwatch.py and
# ffweb.py directly, so an edit here is live the moment the process reloads and NOT before — a
# daemon started hours ago is still executing hours-old code no matter what git says. Editing a
# unit FILE is different; that still needs `sudo sh ffbox/06-services.sh --install`.
#
# The listener failing while the other two come up is expected on a machine with no bot token.
# ffbox.target uses Wants=, not Requires=, precisely so the page and the pipeline survive it.
#
# POSIX sh, like its siblings.
set -eu

SUDO=
[ "$(id -u)" = 0 ] || SUDO=sudo

if ! command -v systemctl >/dev/null 2>&1; then
    echo "restart_ffbox: no systemctl here — nothing to restart." >&2
    exit 1
fi

echo "restarting ffbox.target (ffdiscord-listener + ffwatch + ffweb)"
$SUDO systemctl restart ffbox.target

# What is ACTUALLY running afterwards, not what we asked for. A unit that failed to come back
# is the whole reason to look, and `restart` exits 0 for a Wants= member that died.
for u in ffdiscord-listener.service ffwatch.service ffweb.service; do
    printf '  %-28s %s  (since %s)\n' "$u" \
        "$(systemctl is-active "$u" 2>/dev/null || echo inactive)" \
        "$(systemctl show "$u" -p ActiveEnterTimestamp --value 2>/dev/null)"
done
