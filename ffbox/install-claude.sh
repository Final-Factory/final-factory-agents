#!/usr/bin/env bash
#
# Install Claude Code into the ffbox image. Build-time only.
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

installer="$(mktemp)"
trap 'rm -f "$installer"' EXIT

curl -fsSLo "$installer" https://claude.ai/install.sh
bash -n "$installer"
bash "$installer"

real="$(readlink -f "${HOME}/.local/bin/claude")"
if [ ! -x "$real" ]; then
    echo "install-claude.sh: no executable found at ${HOME}/.local/bin/claude" >&2
    exit 1
fi

install -m 0755 "$real" /usr/local/bin/claude
rm -rf "${HOME}/.local/share/claude" "${HOME}/.local/bin/claude"

/usr/local/bin/claude --version
