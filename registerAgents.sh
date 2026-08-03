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
# Installs ff-agents + ff-speckit by default; '--plugin NAME' adds others (ff-discord), and
# '--remove --plugin NAME' drops one. Both edit a remembered plugin set under ~/.claude, so a
# later bare run keeps every plugin you asked for up to date and leaves the ones you dropped out.
#
# Needs git credentials with read access to the repo. Everything installs at USER scope, so one
# run covers every clone, worktree, and branch of FinalFactory on this machine. Restart open
# sessions afterward (Codex: /reload-plugins) so they re-discover skills.

set -eu

MP_NAME="final-factory-agents"
MP_SOURCE="Final-Factory/final-factory-agents"
DEFAULT_PLUGINS="ff-agents ff-speckit"     # installed on every machine unless explicitly removed
CHECKOUT_MARKER="$HOME/.claude/final-factory-agents-checkout"
PLUGIN_STATE="$HOME/.claude/final-factory-agents-plugins"

usage() {
  cat <<EOF
Usage: sh registerAgents.sh [options]

Registers the '${MP_NAME}' marketplace with every supported coding agent found
on this machine (Claude Code, Codex) and installs its plugins at user scope.
Idempotent — re-run any time to update.

Default plugins: ${DEFAULT_PLUGINS}
Optional extras: ff-discord (needs the ffdiscord bot token in ~/.config/ffdiscord/)

Options (alphabetical):
  (none)         Register if needed, otherwise refresh the marketplace and update
                 every remembered plugin. The normal path; safe to re-run.
  --claude       Only touch Claude Code.
  --codex        Only touch Codex.
  --help         Show this message.
  --plugin NAME  Also install NAME, on top of the defaults, and remember it — later
                 bare runs keep it updated too. Repeatable, and accepts a
                 comma-separated list:
                   sh registerAgents.sh --plugin ff-discord
                   sh registerAgents.sh --plugin ff-discord,ff-speckit
                 Re-adding a plugin you previously removed un-does the removal.
  --reinstall    Remove the marketplace and add it back from scratch, then install
                 the remembered set. Use when the local clone is stale or broken —
                 e.g. it was registered before the default branch changed, so it is
                 pinned to a branch that no longer exists and 'update' silently
                 keeps serving old content.
  --remove       With --plugin: uninstall just those plugins and forget them, so
                 later runs stop reinstalling them; the marketplace and every other
                 plugin stay. Removing a default this way sticks until you add it
                 back.
                   sh registerAgents.sh --remove --plugin ff-speckit
                 This also deletes each removed plugin's cached copy, so its skills
                 are off the disk and not just unregistered — restart any open
                 session that still has the plugin loaded.
                 Without --plugin: remove the whole marketplace (which uninstalls
                 all of its plugins) and forget the remembered set, then stop.
                 Cached versions on disk are kept there, so open sessions keep
                 working.

The remembered plugin set lives in ~/.claude/final-factory-agents-plugins and is
shared by both tools. --claude/--codex combine with the other flags, e.g.
'sh registerAgents.sh --codex --reinstall'.

After any change, restart open sessions — plugins are discovered only at session
start (in Codex, /reload-plugins does it without a restart).
EOF
}

MODE="update"
TOOLS="both"
EXTRA_PLUGINS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --reinstall)  MODE="reinstall" ;;
    --remove)     MODE="remove" ;;
    --claude)     TOOLS="claude" ;;
    --codex)      TOOLS="codex" ;;
    --plugin)
      [ $# -ge 2 ] || { echo "ERROR: --plugin needs a plugin name" >&2; exit 1; }
      # accept both '--plugin a --plugin b' and '--plugin a,b'
      EXTRA_PLUGINS="$EXTRA_PLUGINS $(printf '%s' "$2" | tr ',' ' ')"
      shift ;;
    --plugin=*)
      EXTRA_PLUGINS="$EXTRA_PLUGINS $(printf '%s' "${1#--plugin=}" | tr ',' ' ')" ;;
    --help|-h)    usage; exit 0 ;;
    *)            echo "ERROR: unknown option '$1'" >&2; echo >&2; usage >&2; exit 1 ;;
  esac
  shift
done

# '--remove --plugin X' is a different operation from '--remove': it drops X and leaves the
# marketplace (and every other plugin) in place.
if [ "$MODE" = "remove" ] && [ -n "$EXTRA_PLUGINS" ]; then
  MODE="remove-plugins"
fi

# --- remembered plugin set --------------------------------------------------------------------
# ~/.claude/final-factory-agents-plugins records what this machine asked for, so a later bare run
# updates the extras too instead of leaving them frozen at their cached version. Two lists:
#   installed: the resolved set. excluded: plugins removed on purpose, so a DEFAULT that was
#   removed does not come back on the next run. The two are kept disjoint.
# Defaults are unioned in on every run, so a plugin added to DEFAULT_PLUGINS later reaches
# machines that already have a state file.
list_has() {
  for _it in $1; do
    if [ "$_it" = "$2" ]; then return 0; fi
  done
  return 1
}
list_add() {  # echo list with $2 appended if absent
  if list_has "$1" "$2"; then printf '%s' "$1"; else printf '%s' "${1:+$1 }$2"; fi
}
list_del() {  # echo list with $2 dropped
  _out=""
  for _it in $1; do
    if [ "$_it" != "$2" ]; then _out="${_out:+$_out }$_it"; fi
  done
  printf '%s' "$_out"
}

REMEMBERED=""
EXCLUDED=""
if [ -f "$PLUGIN_STATE" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line=$(printf '%s' "$line" | tr -d '\r')
    case "$line" in
      installed:*) for p in ${line#installed:}; do REMEMBERED=$(list_add "$REMEMBERED" "$p"); done ;;
      excluded:*)  for p in ${line#excluded:};  do EXCLUDED=$(list_add "$EXCLUDED" "$p"); done ;;
    esac
  done < "$PLUGIN_STATE"
fi

PLUGINS=""
for p in $DEFAULT_PLUGINS $REMEMBERED; do
  if list_has "$EXCLUDED" "$p"; then continue; fi
  PLUGINS=$(list_add "$PLUGINS" "$p")
done

REMOVE_TARGETS=""
if [ "$MODE" = "remove-plugins" ]; then
  for p in $EXTRA_PLUGINS; do
    REMOVE_TARGETS=$(list_add "$REMOVE_TARGETS" "$p")
    PLUGINS=$(list_del "$PLUGINS" "$p")
    EXCLUDED=$(list_add "$EXCLUDED" "$p")
  done
else
  for p in $EXTRA_PLUGINS; do
    PLUGINS=$(list_add "$PLUGINS" "$p")
    EXCLUDED=$(list_del "$EXCLUDED" "$p")   # re-adding un-does an earlier removal
  done
fi

# Written BEFORE touching any tool: it records intent, so a run that dies halfway (network, a
# broken CLI) still leaves the next run knowing what to install.
save_plugin_state() {
  mkdir -p "$(dirname "$PLUGIN_STATE")"
  {
    echo "# registerAgents.sh — plugins remembered for this machine. Edit via"
    echo "# 'sh registerAgents.sh --plugin NAME' / '--remove --plugin NAME'."
    echo "installed: $PLUGINS"
    echo "excluded: $EXCLUDED"
  } > "$PLUGIN_STATE"
}

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

# --- uninstall leftovers -----------------------------------------------------------------------
# 'claude plugin uninstall' drops the plugin from enabledPlugins/installed_plugins.json — the
# skills stop loading — but leaves the extracted copy (skills and all) under
# plugins/cache/<marketplace>/<plugin>/<version>/. Delete it so a removed plugin's skills are
# actually off the disk. A later re-install re-extracts it from the marketplace clone.
purge_cache() {  # $1 = tool root (~/.claude, ~/.codex), $2 = plugin name
  [ -n "${2:-}" ] || return 0                       # never let an empty name widen the rm
  _dir="$1/plugins/cache/${MP_NAME}/$2"
  if [ -d "$_dir" ]; then
    rm -rf "$_dir"
    echo "  deleted cached copy: $_dir"
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

  if [ "$MODE" = "remove-plugins" ]; then
    INSTALLED=$(claude plugin list 2>/dev/null || true)
    for p in $REMOVE_TARGETS; do
      if printf '%s\n' "$INSTALLED" | grep -q "${p}@${MP_NAME}"; then
        echo "uninstalling '${p}@${MP_NAME}'"
        claude plugin uninstall "${p}@${MP_NAME}" --scope user
      else
        echo "'${p}@${MP_NAME}' is not installed — nothing to remove"
      fi
      purge_cache "${CLAUDE_CONFIG_DIR:-$HOME/.claude}" "$p"
    done
    echo "still remembered: ${PLUGINS:-(none)}"
    echo "done. Restart Claude Code sessions to drop them."
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

  if [ "$MODE" = "remove-plugins" ]; then
    INSTALLED=$(codex plugin list 2>/dev/null || true)
    for p in $REMOVE_TARGETS; do
      # `codex plugin list` includes available plugins whose status is "not installed", so a
      # name-only grep is a false positive. Match the full selector and installed status columns.
      if printf '%s\n' "$INSTALLED" |
        awk -v id="${p}@${MP_NAME}" '$1 == id && $2 ~ /^installed/ { found=1 } END { exit !found }'; then
        echo "uninstalling '${p}'"
        codex plugin remove "${p}@${MP_NAME}"
      else
        echo "'${p}' is not installed — nothing to remove"
      fi
      # Codex's cache layout is assumed to mirror Claude's; purge_cache is a no-op if it differs,
      # so this is safe either way. Ben: if a stale copy survives, fix the path here.
      purge_cache "${CODEX_HOME:-$HOME/.codex}" "$p"
    done
    echo "still remembered: ${PLUGINS:-(none)}"
    echo "done. Run /reload-plugins in open Codex sessions to drop them."
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
    # Available-but-uninstalled plugins are also listed. Check the full selector plus status so
    # first registration actually installs them.
    if printf '%s\n' "$INSTALLED" |
      awk -v id="${p}@${MP_NAME}" '$1 == id && $2 ~ /^installed/ { found=1 } END { exit !found }'; then
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
  save_plugin_state
  if [ "$MODE" = "remove-plugins" ]; then
    echo "removing: $REMOVE_TARGETS"
  fi
  echo "plugins: ${PLUGINS:-(none)}"
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

# A full marketplace removal takes the remembered set with it — the next plain run starts from
# DEFAULT_PLUGINS again, which is what someone re-registering from scratch expects.
if [ "$MODE" = "remove" ] && [ -f "$PLUGIN_STATE" ]; then
  rm -f "$PLUGIN_STATE"
  echo "forgot the remembered plugin set ($PLUGIN_STATE)"
fi
