---
name: visual-capture-native-resolution-and-review
description: Lower the actual built-player resolution through Settings when full-size compositing makes visual episodes invalid; capture validity and Watch playback validity are separate gates.
---

# Check native resolution when capture timing fails

Feature074 t38 launched with 1280×720 arguments, but saved display preferences produced a
2560×1382 native view. A native ARM host at roughly 90 fps still failed visual-episode cadence
and capture-overhead limits. `DisplaySettingsController.LoadFromPlayerPrefs` calls
`Screen.SetResolution`; launch arguments alone do not establish the live view.

`UnityVisualEpisodeCompositor.Capture` first captures at `Screen.width × Screen.height`,
then scales into the review bounds. The default 960×540 review image therefore does not
bound the full-size capture cost. There is no supported ffauto capture-profile override;
`visualepisode.start` accepts episode, scenario and tracker only.

Use the game's Settings → Display → Resolution control. In t38, selecting 1280×720,
verifying the live pointer bounds, then capturing without concurrent derivative-building
work produced timing-valid episodes for host, M3 and BEAST actions at the unchanged 16 UPS.
One intermediate retry still failed overhead; preserve failed attempts and check each new
manifest. Never relax the minimum cadence or overhead gate to obtain a pass.

A valid capture can still play badly in Watch. In this run normal-speed browser playback
skipped observations; quarter-speed playback could paint every observation. Check the visible
playback diagnostics, use markers and individual steps, and inspect full source frames if a
narrow browser panel clips the image. Do not attribute skipped browser paints to the game or
claim a normal-speed motion verdict from invalid playback. Restoring/resizing the browser
mid-playback can itself create skipped observations; restart that review cleanly.
