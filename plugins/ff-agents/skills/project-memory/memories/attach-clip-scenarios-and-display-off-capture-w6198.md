---
name: Attach-mode clip scenarios and a display-off capture (w6198)
description: An ffnightly scenario run against a live editor (attach mode) runs only solo scenarios read from the committed HEAD; station.state finds a flying station by its primary tile; hauler.forwardcore marks a forward core; with the display off, capture in the editor with ScreenCapture per frame.
---

w6198 (2026-11-26, slot5 on LothDesktop) needed a clip of a mobile station landing at the end of a spiral route, on its
second lap. Four traps cost a turn each:

1. **Attach mode runs only solo scenarios, read from the committed HEAD.** A scenario with peers, or one without
   `"solo": true` and `"on": "solo"` on its steps, gave an empty result against the running editor. So did an
   uncommitted scenario: the runner reads `scripts/nightly/scenarios/*.json` from HEAD. Commit it first, then run it.
2. **`station.state|x|z` finds a station by its primary tile, and that tile stays on the zone while the station flies.**
   A poll for "left the zone" on `found == false` never fires. Tell laps apart by `data.flying`: false (landed), then
   true (left), then false (landed again).
3. **Mark a forward core with the test driver `hauler.forwardcore|on|coreX|coreZ|x|z`** (op 9). The UI switch click did
   not take, and the next `station.state` at the core's tile answered not found.
4. **When `record_clip` gets no frames because the display is off** (Win32_DesktopMonitor Availability 8; gfxcapture
   and ddagrab give nothing, and SendInput did not wake it), capture inside the editor instead:
   - Hook an `EditorApplication.update` callback that, once per new `Time.frameCount`, calls
     `ScreenCapture.CaptureScreenshot(dir + "f%05d.png")` and appends the pose you judge (LocalTransform of the entity)
     to a CSV.
   - Run it with `unity-bridge.py eval-file`. Its first line `// ff-not-timing: <why>` stops the bench-ticket guard,
     since the clock only stamps frames. Keep the callback in AppDomain data so a rerun can remove the old one, and its
     status in SessionState, read by `wait-for --match done`.
   - The capture slows the editor to about 7 fps. Single-player runs at most one heartbeat per engine frame, so every
     frame is exactly one heartbeat: `ffmpeg -framerate 20` plays at game speed (20 UPS).
   - Judge motion from the CSV, not by eye. For example: a straight approach is constant yaw and a small off-line
     distance; a turn in place is the core on a circle of constant radius about a fixed centre, by a least-squares
     circle fit. Then look at the stills.
   - About 1 MB a PNG at 1483x751, 3 GB for 3000 frames: encode, publish, and delete the frames.
