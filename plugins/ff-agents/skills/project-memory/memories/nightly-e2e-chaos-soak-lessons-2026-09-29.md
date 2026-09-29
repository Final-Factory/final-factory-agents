---
name: nightly-e2e-chaos-soak-lessons-2026-09-29
description: "What the e2e round-2 chaos soak (075, BEAST, 2026-09-29) taught about driving built players: the agent channel refuses every command while single player is paused behind the Esc menu and ffauto:wait counts paused time; the Esc menu is destroyed and re-instantiated, so find its Save panel through TitleScreenManager._mainMenu; build_player.sh discards tracked-file edits made during a build; overlapping lab runs on one machine share LocalLow desyncReports; late joiners and the audit invulnerability grant."
metadata:
  type: project
---

Source: e2e round 2 worker 3 (chaos soak + Ben's three examples), PR #757 (`e2e-r2-chaos`), proofs in
`specs/075-nightly-e2e-regression/proofs/w13-chaos-2026-09-29.md`. Companions: [[nightly-e2e-lab-lessons-2026-09-28]],
[[nightly-e2e-windows-lab-lessons-2026-09-29]].

**A paused single player takes no agent commands, and `ffauto:wait` never ends there.** The 068 agent channel answers
every request with `state_not_playable: commands need a running game; the game is 'paused'` while single player sits
behind the Esc menu (UiController.PauseGame), and a chain's `ffauto:wait` is scaled time (AutomationChainExecutor:
UniTask.Delay), so it does not elapse either. A verb that opens the menu in single player must finish its own work:
`ui.savegame|<name>|resume` waits in frames for the save, then presses Esc itself; `ui.loadgame|<name>` opens the Load
panel and picks and presses in one call. The runner waits by the lab's clock (`ffnightly.py` step `poll`).

**The Esc menu is destroyed on close and instantiated on open** (TitleScreenManager.ShowMenu). A scene-wide
`FindAnyObjectByType<SaveGamePanel>` can return another instance than the one `MainMenuPanel.HandleLoadPressed` enables,
which never lists a save ("0 listed"). Take `TitleScreenManager._mainMenu`, then its `_saveGamePanel`.

**`build_player.sh` throws away concurrent edits.** It ends with `git checkout -- <file>` on every tracked file that
changed during the build, which is meant for the build's own ProjectSettings rewrites, so an edit you made in that
checkout while it built is silently gone. Commit first, or touch only untracked files until it finishes.

**Overlapping lab runs on one machine fail each other.** Every built player on a machine shares
`LocalLow/Never Games/finalfactory`. The runner's verdict oracle reads every new file in `desyncReports/`, so
another sandbox's desync (or a deliberate injection, e.g. `loot.preparedeath` run with clients connected) fails your
run. Saves are safe since `own_save_names`. Run verdict-bearing proofs alone on the machine, and check a surprising
report's `sessionGuid` and session-reset times against your run; a `_client` report during a single-player run is
never yours.

**Late joiners and `-ffAutomationInvulnerablePlayers`.** Before 0610e1ba5 the host authored the grant once for the
players present at start. A late joiner waited for its own grant and threw after InvulnerableGrantObserveTimeoutSeconds
(120 s), and its automation quit (runner: ConnectionResetError, env). Any older late-join failure that is more than two
minutes after the join is probably this. Fixed by GrantLateJoinersAsync (re-authors the idempotent op for new players).

**Chaos plans cannot see deaths or capacity.** An outcome oracle in a pre-generated plan needs a runtime escape: the
spawner kills a whole fleet (Frenzy on count 0), and a Station Core with a full belt holds at most 8 connectors (a put
adds nothing). ffnightly's `value` and `greater` asserts take `unless` for this.
