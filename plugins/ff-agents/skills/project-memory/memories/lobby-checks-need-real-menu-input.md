---
name: lobby-checks-need-real-menu-input
description: "A check that hosts or browses a Steam lobby goes through the title menu, and no automation reaches it: the agent channel refuses commands off a running game, ui.* has no menu panels, -ffAutomationHost makes no Steam lobby. A Mac with a locked screen drops synthetic clicks, so it cannot host one. Check the lock state first."
metadata:
  type: project
---

# Lobby checks need real menu input (w2460, 2026-10-28)

w2460 was a pair run for w2450 (PR #2757, which greys out other-version games in the Lobby Browser). Leg 1 was the host
on m5. It built a bumped 1.0.0.99 player of 5b21c3638c, and the player ran: it showed "Build 99 (v1.0.0.99)" and
"Connected to Steam as user slims". It still could not host, so neither check ran.

**No automation reaches the multiplayer menus.**

- The agent channel (`-ffAgentControl true`) answers every command on the title screen with
  `state_not_playable`: "commands need a running game; the game is 'menu'". The gate is
  `AgentRequestRouter.cs:430` (`CurrentState() != "playing"`), so `pointer.*`, `ui.*` and `console.run` all fail there.
- The `ui.*` panel registry (`AutomationUiDriver.cs`, `Panels`) has no title, Multiplayer, Host or Lobby Browser panel.
- `-ffAutomationHost` hosts over relay or local IP and never creates a Steam lobby. The only caller of
  `HostNewMultiplayerGame` is the host form (`MultiplayerSetupController.cs:702`), and only that path reaches
  `CreateLobby` (`NetworkedGameManager.cs:772`). Browsing lobbies is UI-only too (`LobbyBrowser.cs`).

So every leg of a lobby check needs real mouse and keyboard input on the player's window: the host creating a
public game, and the client browsing and joining. On Windows that is `scripts/agent/osdrive.py` (Windows-only).

**A Mac with a locked screen cannot do it.** On a locked screen, `CGSessionCopyCurrentDictionary()` has
`CGSSessionScreenIsLocked = 1`. `CGWarpMouseCursorPosition` plus mouse-moved events did move the hover highlight on the
Multiplayer button. Mouse-down/up events never pressed it, whether posted with `CGEventPostToPid` or globally at
`.cghidEventTap`, and with click state 1 and a 200 ms hold too. System Events listed no windows for the player. The
player's log still said `focused=True`.

**How to apply:**

- Before a Mac leg needs the menus, read the lock state (Swift, a few lines):
  `(CGSessionCopyCurrentDictionary() as? [String: Any])?["CGSSessionScreenIsLocked"]`. If it is locked, say so and
  fail the leg early. Don't build first: in w2460 the leg built two players before it found the lock.
- When you plan a pair check on lobbies, the host form or the Lobby Browser, put every leg on a machine with an
  unlocked interactive session and a real-input driver. Unlocking is a person's act on their own Mac, so another
  machine is the usual way out.
- To find the window, use `CGWindowListCopyWindowInfo` for the player's pid. The bounds are in points: on a Retina
  Mac, divide the screenshot's pixels by 2 and add the title bar, which was 28 pt in w2460.
