#!/bin/sh
# registerAgents.sh — register the final-factory-agents plugin marketplace with the coding
# agents on this machine (Claude Code and/or Codex) and install its plugins. Safe to run
# repeatedly: the first run registers + installs, later runs refresh the marketplace from
# GitHub (a git pull) and pick up any published plugin updates (a version bump in the
# manifests — see CLAUDE.md's publish workflow).
#
# Both tools read the SAME repo: Claude Code from .claude-plugin/marketplace.json, Codex from
# .agents/plugins/marketplace.json, both serving the same plugins/<name>/skills/ tree.
#
# Needs git credentials with read access to the repo. Everything installs at USER scope, so one
# run covers every clone, worktree, and branch of FinalFactory on this machine. Restart open
# sessions afterward (Codex: /reload-plugins) so they re-discover skills.

set -eu

MP_NAME="final-factory-agents"
MP_SOURCE="Final-Factory/final-factory-agents"
PLUGINS="ff-agents"                        # add ff-speckit / ff-discord here to install those too
CHECKOUT_MARKER="$HOME/.claude/final-factory-agents-checkout"

usage() {
  cat <<EOF
Usage: sh registerAgents.sh [options]

Registers the '${MP_NAME}' marketplace with every supported coding agent found
on this machine (Claude Code, Codex) and installs its plugins (${PLUGINS})
at user scope. Idempotent — re-run any time to update.

Options:
  (none)       Register if needed, otherwise refresh the marketplace and update
               installed plugins. The normal path; safe to re-run.
  --claude     Only touch Claude Code.
  --codex      Only touch Codex.
  --reinstall  Remove the marketplace and add it back from scratch, then install.
               Use when the local clone is stale or broken — e.g. it was registered
               before the default branch changed, so it is pinned to a branch that
               no longer exists and 'update' silently keeps serving old content.
  --remove     Remove the marketplace and stop. This also uninstalls its plugins.
               Cached versions on disk are kept, so open sessions keep working.
  --help       Show this message.

--claude/--codex combine with --reinstall/--remove, e.g.
'sh registerAgents.sh --codex --reinstall'.

After any change, restart open sessions — plugins are discovered only at session
start (in Codex, /reload-plugins does it without a restart).
EOF
}

MODE="update"
TOOLS="both"
while [ $# -gt 0 ]; do
  case "$1" in
    --reinstall)  MODE="reinstall" ;;
    --remove)     MODE="remove" ;;
    --claude)     TOOLS="claude" ;;
    --codex)      TOOLS="codex" ;;
    --help|-h)    usage; exit 0 ;;
    *)            echo "ERROR: unknown option '$1'" >&2; echo >&2; usage >&2; exit 1 ;;
  esac
  shift
done

want() { [ "$TOOLS" = "both" ] || [ "$TOOLS" = "$1" ]; }
have() { command -v "$1" >/dev/null 2>&1; }

# --- record where this checkout lives ---------------------------------------------------------
# This script ships inside the repo, so its own directory IS the working checkout. Recording
# that path lets the publish-skills skill find the checkout on ANY machine, wherever it was
# cloned, without hardcoded paths or environment variables. The marker lives under ~/.claude but
# is tool-agnostic — the skill body is shared, so Codex sessions read the same file.
record_checkout() {
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
}

# --- Claude Code -------------------------------------------------------------------------------
register_claude() {
  echo "== Claude Code =="

  if [ "$MODE" = "remove" ]; then
    if claude plugin marketplace list 2>/dev/null | grep -q "${MP_NAME}"; then
      echo "removing marketplace '${MP_NAME}' (this uninstalls its plugins)"
      claude plugin marketplace remove "$MP_NAME"
      echo "done. Restart Claude Code sessions to drop the plugins."
    else
      echo "marketplace '${MP_NAME}' is not registered — nothing to remove"
    fi
    return 0
  fi

  if claude plugin marketplace list 2>/dev/null | grep -q "${MP_NAME}"; then
    if [ "$MODE" = "reinstall" ]; then
      echo "reinstalling marketplace '${MP_NAME}' from ${MP_SOURCE}"
      claude plugin marketplace remove "$MP_NAME"
      claude plugin marketplace add "$MP_SOURCE"
    else
      echo "marketplace '${MP_NAME}' already registered — refreshing from GitHub"
      claude plugin marketplace update "$MP_NAME"
    fi
  else
    echo "adding marketplace '${MP_NAME}' from ${MP_SOURCE}"
    claude plugin marketplace add "$MP_SOURCE"
  fi

  # Listed AFTER the marketplace block: a reinstall drops the installs, and this reinstates them.
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
}

# --- Codex ---------------------------------------------------------------------------------------
# The 'codex plugin' CLI landed around v0.121 and settled by v0.137; on anything older those
# subcommands do not exist, so fall back to printing the in-session slash commands.
codex_manual_steps() {
  echo "Run these inside a Codex session instead:"
  echo
  echo "  /plugin marketplace add ${MP_SOURCE}"
  for p in $PLUGINS; do echo "  /plugin install ${p}@${MP_NAME}"; done
  echo "  /reload-plugins"
}

register_codex() {
  echo "== Codex =="

  if ! codex plugin marketplace list >/dev/null 2>&1; then
    echo "this Codex build has no 'codex plugin' CLI (needs ~v0.121+)" >&2
    codex_manual_steps
    return 0
  fi

  # Marketplaces register personally under ~/.codex. Separately, a Codex session started INSIDE
  # this checkout also auto-discovers the repo-local .agents/plugins/marketplace.json; the
  # registration below is what every OTHER repo on the machine sees.
  MARKETPLACES=$(codex plugin marketplace list 2>/dev/null || true)

  if [ "$MODE" = "remove" ]; then
    if printf '%s\n' "$MARKETPLACES" | grep -q "${MP_NAME}"; then
      echo "removing marketplace '${MP_NAME}' (this uninstalls its plugins)"
      codex plugin marketplace remove "$MP_NAME"
      echo "done. Run /reload-plugins in open Codex sessions to drop the plugins."
    else
      echo "marketplace '${MP_NAME}' is not registered — nothing to remove"
    fi
    return 0
  fi

  if printf '%s\n' "$MARKETPLACES" | grep -q "${MP_NAME}"; then
    if [ "$MODE" = "reinstall" ]; then
      echo "reinstalling marketplace '${MP_NAME}' from ${MP_SOURCE}"
      codex plugin marketplace remove "$MP_NAME"
      codex plugin marketplace add "$MP_SOURCE"
    else
      echo "marketplace '${MP_NAME}' already registered — refreshing from GitHub"
      codex plugin marketplace upgrade "$MP_NAME"
    fi
  else
    echo "adding marketplace '${MP_NAME}' from ${MP_SOURCE}"
    codex plugin marketplace add "$MP_SOURCE"
  fi

  # Codex has no per-plugin update command — 'marketplace upgrade' above IS the refresh, and an
  # already-listed plugin is served from the newly pulled marketplace clone.
  INSTALLED=$(codex plugin list 2>/dev/null || true)
  for p in $PLUGINS; do
    if printf '%s\n' "$INSTALLED" | grep -q "${p}"; then
      echo "'${p}' already installed — refreshed by the marketplace upgrade above"
    else
      echo "installing '${p}@${MP_NAME}'"
      codex plugin add "${p}@${MP_NAME}"
    fi
  done

  echo "done. Run /reload-plugins in open Codex sessions to pick up the plugins."
}

# --- drive ----------------------------------------------------------------------------------------
if [ "$MODE" != "remove" ]; then
  record_checkout
  echo
fi

RAN=0
if want claude; then
  if have claude; then
    register_claude; RAN=1; echo
  else
    echo "claude CLI not on PATH — skipping Claude Code" >&2
    echo
  fi
fi

if want codex; then
  if have codex; then
    register_codex; RAN=1; echo
  else
    echo "codex CLI not on PATH — skipping Codex" >&2
    echo
  fi
fi

if [ "$RAN" -eq 0 ]; then
  echo "ERROR: no supported agent CLI found on PATH (looked for: claude, codex)" >&2
  exit 1
fi
