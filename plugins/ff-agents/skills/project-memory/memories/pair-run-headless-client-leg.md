---
description: A pair run's headless Linux client leg - mods must match (start both legs with an empty -ffModsPath), a failed join idles so run a retrying client, and headless pointer clicks miss world objects.
---

# Pair run, headless client leg: mods, a retrying join, and clicks that miss

From w4263 (pair run for w4205's PR #3649, the waypoint and landing-zone menu; host on lothdesktop, client a
`-batchmode -nographics` Linux player on biscuit, 2026-11-15).

- **The host's mods must match the client's.** lothdesktop loads the towbot 2.0.0.0 mod; the unmodded client was
  dropped at approval with `[Reconnect] DisconnectClassified class=RemoteRemoval category=Mods reason="Mods|...|towbot:..."`,
  and the host saw only "Player not found for clientId 1" / `host-peer-lost-during-preconnect`. Start BOTH legs with
  `-ffModsPath <an empty folder in TMP>` (`ModLoader.cs`, `ModsPathArgument`) and check `Mod set: 0 mod(s)` in each log.
- **A client whose join fails idles; it does not quit** (`status error: join-timeout ... after 150s`). Don't wait on
  message_pair timing (a HOST WAITING reached the client 4 h late): run the client in a relaunch loop plus a watcher that
  kills it on that status line, under its own bench ticket. It then joins within minutes of the host listening. The
  watcher acts only after the attempt has already failed, never mid-join.
- **Headless pointer clicks don't hit world objects.** In a 640x480 `-nographics` player, `pointer.moveto`'s tile-to-screen
  projection doesn't match where `pointer.click` lands (aimed at tile (-3,1), a waypoint copy was placed at (-25,15)), and a
  click on a landing zone never selected it (`ui.deconstructstation` answered `"zone":"None"`) under nine framings
  (`camera.zoom`, `camera.focus` yaw/pitch, `ui.menu|close`). Give click steps on world objects to a windowed peer; on a
  headless one use the named selectors (`ui.selectwaypoint`, `ui.selectstation`, `ui.selecttile`). Check `pointer.moveto`'s
  answer for "under UI" / "outside the view" before clicking; the bottom of a 640x480 view is all HUD.
