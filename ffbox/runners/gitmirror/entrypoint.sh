#!/bin/sh
# Two servers, one container: git objects over git://, LFS objects over http://.
#
# They are together because they answer the same question -- "give me the repository" -- from the
# same read-only bind mounts, and splitting them would mean two containers, two IPs and two things
# to forget to start.
set -eu

python3 /usr/local/bin/lfs-server.py &
LFS_PID=$!

# If the LFS half dies, take the container down rather than serving git objects and silently
# failing every LFS smudge. Once github.com is off the allowlist there is no fallback, so a
# half-working mirror is worse than an obviously dead one: Docker's restart policy gets a clean go.
( while kill -0 "$LFS_PID" 2>/dev/null; do sleep 5; done
  echo "[mirror] the LFS server exited -- stopping the container" >&2
  kill 1 2>/dev/null ) &

exec git daemon \
    --reuseaddr \
    --informative-errors \
    --base-path=/srv \
    --export-all \
    --listen=0.0.0.0 \
    --port=9418 \
    /srv
