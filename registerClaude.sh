#!/bin/sh
# registerClaude.sh — register the final-factory-agents plugin marketplace with Claude Code
# and install the ff-agents plugin. Safe to run repeatedly: first run registers + installs,
# later runs refresh the marketplace from GitHub (a git pull) and pick up any published
# plugin updates (a version bump in the manifests — see CLAUDE.md's publish workflow).
#
# Needs git credentials with read access to the repo. Marketplace + plugins install at
# USER scope, so one run covers every clone, worktree, and branch of FinalFactory on this
# machine. Restart open Claude Code sessions afterward so they re-discover skills.

set -eu

MP_NAME="final-factory-agents"
MP_SOURCE="Final-Factory/final-factory-agents"
PLUGINS="ff-agents"                        # add ff-speckit / ff-discord here to install those too

# --- marketplace ---------------------------------------------------------------------------
if claude plugin marketplace list 2>/dev/null | grep -q "${MP_NAME}"; then
  echo "marketplace '${MP_NAME}' already registered — refreshing from GitHub"
  claude plugin marketplace update "$MP_NAME"
else
  echo "adding marketplace '${MP_NAME}' from ${MP_SOURCE}"
  claude plugin marketplace add "$MP_SOURCE"
fi

# --- plugins --------------------------------------------------------------------------------
INSTALLED=$(claude plugin list 2>/dev/null || true)
for p in $PLUGINS; do
  if printf '%s\n' "$INSTALLED" | grep -q "${p}@${MP_NAME}"; then
    echo "checking '${p}@${MP_NAME}' for updates"
    claude plugin update "${p}@${MP_NAME}" --scope user
  else
    echo "installing '${p}@${MP_NAME}'"
    claude plugin install "${p}@${MP_NAME}" --scope user
  fi
done

echo "done. Restart Claude Code sessions to pick up the plugins."
