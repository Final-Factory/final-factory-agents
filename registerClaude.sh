#!/bin/sh
# registerClaude.sh — register the final-factory-agents plugin marketplace with Claude Code
# and install the ff-agents plugin. Safe to run repeatedly: first run registers + installs,
# later runs refresh the marketplace from its source and pick up any published plugin
# updates (a version bump in the manifests — see CLAUDE.md's publish workflow).
#
# Prerequisite: set the FINAL_FACTORY_AGENTS_DIR environment variable to the local
# checkout of the final-factory-agents repo before running (see error text below for how).
#
# Marketplace + plugins install at USER scope, so one run covers every clone, worktree,
# and branch of FinalFactory on this machine. Restart open Claude Code sessions afterward
# so they re-discover skills.

set -eu

MP_NAME="final-factory-agents"
PLUGINS="ff-agents"                        # add ff-speckit / ff-discord here to install those too

# --- resolve the repo location from the environment --------------------------------------
MP_SOURCE="${FINAL_FACTORY_AGENTS_DIR:-}"

if [ -z "$MP_SOURCE" ]; then
  echo "ERROR: the FINAL_FACTORY_AGENTS_DIR environment variable is not set." >&2
  echo "Set it to your checkout of the final-factory-agents repo, then re-run. Examples:" >&2
  echo "  PowerShell (persistent):  [Environment]::SetEnvironmentVariable('FINAL_FACTORY_AGENTS_DIR', 'D:\\work\\final-factory-agents', 'User')" >&2
  echo "  cmd (persistent):         setx FINAL_FACTORY_AGENTS_DIR D:\\work\\final-factory-agents" >&2
  echo "  POSIX shell (this shell): export FINAL_FACTORY_AGENTS_DIR=/d/work/final-factory-agents" >&2
  echo "New terminals are needed after setx/SetEnvironmentVariable for the value to appear." >&2
  exit 1
fi

if [ ! -d "$MP_SOURCE" ]; then
  echo "ERROR: FINAL_FACTORY_AGENTS_DIR points at '$MP_SOURCE', which is not a directory." >&2
  echo "Fix the environment variable to reference your checkout of the final-factory-agents repo." >&2
  exit 1
fi

if [ ! -f "$MP_SOURCE/.claude-plugin/marketplace.json" ]; then
  echo "ERROR: '$MP_SOURCE' exists but is not the final-factory-agents repo" >&2
  echo "(missing .claude-plugin/marketplace.json). Point FINAL_FACTORY_AGENTS_DIR at the repo root." >&2
  exit 1
fi

# --- marketplace ------------------------------------------------------------------------
if claude plugin marketplace list 2>/dev/null | grep -q "${MP_NAME}"; then
  echo "marketplace '${MP_NAME}' already registered — refreshing from source"
  claude plugin marketplace update "$MP_NAME"
else
  echo "adding marketplace '${MP_NAME}' from ${MP_SOURCE}"
  claude plugin marketplace add "$MP_SOURCE"
fi

# --- plugins ----------------------------------------------------------------------------
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
