#!/usr/bin/env bash
#
# Install Claude Code into the ffbox image. Build-time only.
#
#   bash install-claude.sh [VERSION|latest|stable]     (default: latest)
#
# The Dockerfile passes ARG CLAUDE_VERSION, which 03-build.sh and runners/03-image.sh fill in from
# claude-version.sh. A concrete version is what makes the layer rebuild when a new release exists.
#
# Same download-then-syntax-check shape as installClaude.sh at the repo root: never pipe a
# freshly downloaded script straight into a shell, so a truncated or tampered download fails
# the parse instead of half-executing.
#
# The official installer drops a self-contained native binary at
#   $HOME/.local/share/claude/versions/<version>
# with a symlink at $HOME/.local/bin/claude. Since ffbox runs as the host user's UID rather than
# root, we resolve that symlink and install the real binary into /usr/local/bin, then throw the
# root-owned install tree away.
set -euo pipefail

version="${1:-latest}"

installer="$(mktemp)"
trap 'rm -f "$installer"' EXIT

curl -fsSLo "$installer" https://claude.ai/install.sh
bash -n "$installer"
bash "$installer" "$version"

real="$(readlink -f "${HOME}/.local/bin/claude")"
if [ ! -x "$real" ]; then
    echo "install-claude.sh: no executable found at ${HOME}/.local/bin/claude" >&2
    exit 1
fi

install -m 0755 "$real" /usr/local/bin/claude
rm -rf "${HOME}/.local/share/claude" "${HOME}/.local/bin/claude"

# An image labelled with one version and carrying another is worse than a failed build, because
# the label is what says whether the next build has anything to do.
got="$(/usr/local/bin/claude --version)"
echo "$got"
case "$version" in
    latest|stable) ;;
    *) case "$got" in
           "$version "*) ;;
           *) echo "install-claude.sh: asked for $version, got: $got" >&2; exit 1 ;;
       esac ;;
esac
