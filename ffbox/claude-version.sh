#!/bin/sh
# claude-version.sh — print the Claude Code version the next image build should install.
#
#   sh ffbox/claude-version.sh [IMAGE]
#
# Called by 03-build.sh and runners/03-image.sh, and its output becomes --build-arg CLAUDE_VERSION.
#
# WHY A VERSION AND NOT THE WORD "latest". The Dockerfile's install layer is cached on its inputs,
# and a constant input is a layer that never rebuilds: from 2026-08-25 to 2026-09-12 every rebuild
# on every update pass reused the same install, so containers ran 2.1.245 while the host had moved
# on to 2.1.269. A concrete version changes the input exactly when there is a new release, so the
# layer rebuilds then and stays cached otherwise.
#
# WHY AT BUILD TIME AND NOT IN THE CONTAINER. Containers run with DISABLE_AUTOUPDATER=1 behind a
# fence that does not list downloads.claude.ai (egress/allowlist.txt). The build runs on the host,
# outside the fence, so the image is where a new version comes in.
#
# NEVER FAILS THE BUILD. A lookup that does not answer falls back to what IMAGE already carries, so
# a flaky network keeps the current version rather than stopping an update pass. Only an image with
# no label at all gets "latest", which the installer also accepts.
#
# FFBOX_CLAUDE_VERSION=X.Y.Z overrides the lookup, for pinning by hand.
set -u

IMAGE=${1:-${FFBOX_IMAGE:-ffbox:latest}}
URL=https://downloads.claude.ai/claude-code-releases/latest

valid() { printf '%s' "$1" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$'; }

if [ -n "${FFBOX_CLAUDE_VERSION:-}" ]; then
    valid "$FFBOX_CLAUDE_VERSION" \
        || { echo "claude-version.sh: FFBOX_CLAUDE_VERSION=$FFBOX_CLAUDE_VERSION is not X.Y.Z" >&2; exit 2; }
    echo "$FFBOX_CLAUDE_VERSION"
    exit 0
fi

v=$(curl -fsSL --max-time 20 "$URL" 2>/dev/null | tr -d '[:space:]')
if valid "$v"; then
    echo "$v"
    exit 0
fi

v=$(docker image inspect "$IMAGE" \
    --format '{{index .Config.Labels "org.finalfactory.claude-version"}}' 2>/dev/null)
if valid "$v"; then
    echo "claude-version.sh: $URL did not answer; keeping the $v that $IMAGE already has" >&2
    echo "$v"
    exit 0
fi

echo "claude-version.sh: $URL did not answer and $IMAGE has no claude-version label; using latest" >&2
echo latest
