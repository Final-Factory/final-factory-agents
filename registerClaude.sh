#!/bin/sh
# registerClaude.sh — register the final-factory-agents plugin marketplace with Claude Code
# and install the ff-agents plugin. Safe to run repeatedly: first run registers + installs,
# later runs refresh the marketplace from GitHub (a git pull) and pick up any published
# plugin updates (a version bump in the manifests — see CLAUDE.md's publish workflow).
#
# It also self-heals a stale marketplace clone. Claude Code clones the repo once and pins it
# to whatever the default branch was at that moment; a later default-branch change (or a
# deleted branch) leaves the clone stranded, still reporting successful updates while serving
# frozen content. This script detects that and re-registers.
#
# Needs git credentials with read access to the repo. Marketplace + plugins install at
# USER scope, so one run covers every clone, worktree, and branch of FinalFactory on this
# machine. Restart open Claude Code sessions afterward so they re-discover skills.

set -eu

MP_NAME="final-factory-agents"
MP_SOURCE="Final-Factory/final-factory-agents"
PLUGINS="ff-agents"                        # add ff-speckit / ff-discord here to install those too
CHECKOUT_MARKER="$HOME/.claude/final-factory-agents-checkout"

# --- record where this checkout lives -------------------------------------------------------
# This script ships inside the repo, so its own directory IS the working checkout. Recording
# that path lets the publish-skills skill find the checkout on ANY machine, wherever it was
# cloned, without hardcoded paths or environment variables.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$SCRIPT_DIR/.claude-plugin/marketplace.json" ]; then
  # Prefer a native path (git-bash `pwd -W` yields D:/... which both shell and file tools accept)
  NATIVE_DIR=$(cd "$SCRIPT_DIR" && { pwd -W 2>/dev/null || pwd; })
  mkdir -p "$(dirname "$CHECKOUT_MARKER")"
  printf '%s\n' "$NATIVE_DIR" > "$CHECKOUT_MARKER"
  echo "recorded checkout location: $NATIVE_DIR"
else
  echo "note: not running from a final-factory-agents checkout — skipping checkout marker" >&2
fi

# --- helpers ----------------------------------------------------------------------------------
# Path of Claude Code's managed clone for our marketplace ("" if not registered).
marketplace_clone_dir() {
  claude plugin marketplace list --json 2>/dev/null \
    | sed -n "/\"name\": \"${MP_NAME}\"/,/}/p" \
    | sed -n 's/.*"installLocation": *"\(.*\)".*/\1/p' \
    | tr '\\' '/' | tr -s '/'
}

# True when the managed clone is a git repo sitting on the remote's CURRENT default branch.
# Unreachable remote => treated as healthy, so being offline never causes churn.
marketplace_clone_is_current() {
  dir="$1"
  [ -n "$dir" ] || return 1
  [ -d "$dir" ] || return 1
  git -C "$dir" rev-parse --git-dir >/dev/null 2>&1 || return 1

  cur=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null) || return 1
  [ -n "$cur" ] || return 1

  def=$(git -C "$dir" ls-remote --symref origin HEAD 2>/dev/null \
        | sed -n 's|^ref: refs/heads/\(.*\)[[:space:]]HEAD$|\1|p')
  [ -n "$def" ] || return 0

  [ "$cur" = "$def" ]
}

# --- marketplace ---------------------------------------------------------------------------
if claude plugin marketplace list 2>/dev/null | grep -q "${MP_NAME}"; then
  CLONE_DIR=$(marketplace_clone_dir)
  if marketplace_clone_is_current "$CLONE_DIR"; then
    echo "marketplace '${MP_NAME}' already registered — refreshing from GitHub"
    claude plugin marketplace update "$MP_NAME"
  else
    echo "marketplace '${MP_NAME}' clone is stale (wrong or deleted branch) — re-registering"
    claude plugin marketplace remove "$MP_NAME"
    claude plugin marketplace add "$MP_SOURCE"
  fi
else
  echo "adding marketplace '${MP_NAME}' from ${MP_SOURCE}"
  claude plugin marketplace add "$MP_SOURCE"
fi

# --- plugins --------------------------------------------------------------------------------
# Listed AFTER the marketplace block: a re-register drops the installs, and this reinstates them.
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
