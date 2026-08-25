#!/bin/sh
#
# Wait until the rootless Docker daemon answers, or fail loudly saying why it did not.
#
# WHY THIS EXISTS. ffbox's units are SYSTEM units that run as the owner, while the rootless
# daemon lives in that user's own systemd instance (user@<uid>.service). After= and Wants= do
# not cross the system/user boundary, so at boot the pipeline starts before the socket it needs
# exists. ffbox-docker.service runs this once, and every unit that touches docker orders after
# it. See design/rootless_docker_design.txt section 6.
#
# WAITING ON THE SOCKET FILE IS NOT ENOUGH. Lingering creates /run/user/<uid> at boot, and the
# socket shows up a moment before the daemon behind it will answer anything. So this asks the
# daemon a question instead of looking for a file.
set -eu

SOCK=${1:?usage: wait-for-docker.sh /run/user/<uid>/docker.sock [seconds]}
DEADLINE=${2:-90}

DOCKER_HOST="unix://$SOCK"
export DOCKER_HOST

i=0
while [ "$i" -lt "$DEADLINE" ]; do
    if docker version >/dev/null 2>&1; then
        [ "$i" = 0 ] || printf 'ffbox: rootless docker answered after %ss\n' "$i"
        exit 0
    fi
    i=$((i + 1))
    sleep 1
done

# Three things go wrong here and they have different fixes, so name all three rather than
# printing "timed out" and leaving the operator to guess.
printf 'ffbox: no rootless docker at %s after %ss.\n' "$SOCK" "$DEADLINE" >&2
printf '       lingering off?   loginctl show-user %s -p Linger\n' "$(id -un)" >&2
printf '       daemon down?     systemctl --user status docker\n' >&2
printf '       never installed? dockerd-rootless-setuptool.sh install\n' >&2
exit 1
