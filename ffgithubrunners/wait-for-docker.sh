#!/bin/sh
#
# Wait until ffbox-container's rootless daemon answers, or fail saying which of the three things
# went wrong.
#
# WHY THIS EXISTS. ffgithubrunners' units are SYSTEM units running as the supervisor's account,
# while the daemon lives in ffbox-container's own systemd instance. After= and Wants= do not cross
# the system/user boundary, so at boot a slot would start before the socket it needs exists.
#
# WAITING ON THE SOCKET FILE IS NOT ENOUGH. Lingering creates the runtime directory at boot and
# the socket appears a moment before the daemon behind it will answer anything, so this asks the
# daemon a question instead of looking for a file.
set -eu

SOCK=${1:?usage: wait-for-docker.sh /run/ffbox-container/docker.sock [seconds] [account]}
DEADLINE=${2:-90}
CUSER=${3:-ffbox-container}

DOCKER_HOST="unix://$SOCK"
export DOCKER_HOST

i=0
while [ "$i" -lt "$DEADLINE" ]; do
    if docker version >/dev/null 2>&1; then
        [ "$i" = 0 ] || printf 'ffgithubrunners: rootless docker answered after %ss\n' "$i"
        exit 0
    fi
    i=$((i + 1))
    sleep 1
done

printf 'ffgithubrunners: no rootless docker at %s after %ss.\n' "$SOCK" "$DEADLINE" >&2
printf '       lingering off?     loginctl show-user %s -p Linger\n' "$CUSER" >&2
printf '       daemon down?       sudo -u %s XDG_RUNTIME_DIR=/run/user/%s systemctl --user status docker\n' \
       "$CUSER" "$(id -u "$CUSER" 2>/dev/null || echo '<uid>')" >&2
printf '       never installed?   sh ffgithubrunners/02-daemon.sh\n' >&2
printf '       cannot reach it?   groups | grep %s   (new session needed after usermod -aG)\n' "$CUSER" >&2
exit 1
