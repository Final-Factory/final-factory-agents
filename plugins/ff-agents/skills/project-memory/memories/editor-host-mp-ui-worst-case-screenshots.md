---
name: editor-host-mp-ui-worst-case-screenshots
description: Recipe for worst-case screenshots of multiplayer UI (name tags, peer status, chat lines) - the editor hosts, headless built clients of the same version join, views are injected in the editor, the language is switched per process, and ScreenCapture of the focused Game view is used because the composited capture drops the name-tag canvas.
---

# Worst-case screenshots of multiplayer UI: editor host + headless clients

Name tags and other per-peer UI only draw for OTHER players, so they need real clients. Proven in 087
(2026-09-28, BEAST); the frames are in `specs/087-slow-client-catchup/proofs/ui/`.

1. **Host from the editor.** Write `.ff-local-automation.json` at the project root (gitignored):
   `Enabled`, `AutoStartInEditor: true`, `Role: "Host"`, `Port`, `SaveName`, `TargetClientCount`,
   `OutlivePairBreak: true`, `EnableDeterminismAudit: false`, `ExitPlayModeOnComplete: false`, a long
   `PostConnectDelayMs`, and `PreConnectCommand: "ffauto:player.setposition|2|-2"`. New characters
   spawn at the world origin, and `player.setposition` is refused once anyone has joined. The editor's
   poller presses Play itself and consumes the arm. Check first that `main.unity` is the active scene.
2. **Join headless built clients of the SAME game version.** A build from before a version bump is
   refused at approval: the host logs `Player not found for clientId N` and ends with
   `host-peer-lost-during-preconnect`. Client line: `finalfactory.exe -batchmode -nographics
   -ffAutomationRole client -ffAutomationHost 127.0.0.1 -ffAutomationPort <port>
   -ffAutomationReclaimIdentity <unique> -ffAutomationPostConnectDelayMs 1800000`.
3. **Keep every editor call short.** A client's liveness watchdog trips after 5 s without a heartbeat,
   and a long call (a 4K composited capture, a synchronous build, a menu that opens a modal) starves
   the host. Set Free Aspect first (`Final Factory/Dev/GameView Free Aspect`) so the host renders at the
   docked size, not 4K.
4. **Inject the worst case** into the presentation views the host's RPC fills, e.g.
   `PeerSyncStatus.ReplaceAll(...)`. UI that recomposes only on change needs the view cleared in one
   call and set in the next, one frame apart.
5. **Switch the language** with `LocalizationSettings.SelectedLocale = LocalizationSettings.AvailableLocales.GetLocale("pt-BR")`.
   This project's startup selectors are command line, system and specific, so nothing is persisted.
   Pick the locale by measuring the table rows; pt-BR was longest overall, German for long sentences.
6. **Capture with `ScreenCapture.CaptureScreenshot` on the focused Game view** (drive-game Channel B,
   no `Step()` while frames advance). The composited `manage_camera` capture did not draw the
   name-tag canvas (sort order -100).
7. Measure too: `Canvas.ForceUpdateCanvases()`, then `isTextOverflowing` and preferred against rect
   size on every new text.

`Tools/Localization/Validate Font Coverage` opens a modal with its verdict. A bridge call to it times
out and is retried (six runs), so read `Localization/FontCoverageReport.txt` instead.

Play mode can write runtime values into a Resources material (`VfxBeam_Mining.mat` changed here);
`git checkout --` it afterwards. Remove the automation config when done.

Related: [[ui-screenshot-worst-case-before-done]], [[dontsave-bootstrap-hosts-outlive-editor-play]],
[[timed-out-execute-code-can-run-again]].
