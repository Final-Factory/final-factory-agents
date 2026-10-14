---
name: modded-multiplayer-testing-and-refusal-screen
description: "Testing the mod-set handshake (spec 083, w1252) on one Windows PC: -ffModsPath per peer, the modsExpected scenario flag, a DeckTour that reaches the join-refusal screen, the real-click traps (DPI-scaled client coordinates, other sandboxes' topmost windows), the fixture logs a new fingerprint surface needs, and the localization row that ends in a colon."
metadata:
  node_type: memory
  type: project
  modified: 2026-10-13T19:10:00Z
---

**Lesson (w1252, 2026-10-13, Windows development players of 79a6d8fb on beast).** Phases A and B of modded multiplayer
(FinalFactory PR #1692) took four detours that are not in the code.

## Two peers with different mods on one PC

- `-ffModsPath <dir>` (`ModLoader.ModsPathArgument`) gives each player its own mods folder; the shared
  `LocalLow/.../mods` stays empty. `ffnightly.py run --peer-arg host=-ffModsPath --peer-arg host=<dir> --peer-arg a=-ffModsPath --peer-arg a=<dir>`
  (one flag and one value per `--peer-arg`; the lab file is a PATH, `--lab scripts/nightly/lab.win.json`).
- The runner's `lab_is_mod_free` turned a modded host into `env` ("ran an installed mod"). A scenario that tests mods says
  `"modsExpected": true` (`MP-W1252-modded-pair-audit.json`). A heartbeat step waits 120 s unless it carries `timeoutS`:
  5,000 heartbeats at 16 UPS is about 312 s, so `"timeoutS": 900` (the first run failed "did not advance 5000 heartbeats within 120 s ... at 1924").
- A refused client cannot be a scenario (the runner needs every peer to play). Launch a windowed automation host and client
  by hand, and give the client `-ffDeckTour`.

## Reaching the refusal screen

- The agent channel refuses commands at the title menu (`state_not_playable`), and a window message posted to the player is ignored by uGUI
  buttons (it did reach the IMGUI dev console's Close button). The refusal is latched
  (`NetworkedGameManager.PendingJoinFailureReason`) and shown when the Multiplayer panel opens (`MultiplayerSetupController.OnEnable`), so a tour
  `click name:Continue/FFButton`, `wait 40`, `click text:Multiplayer` shows it; the same tour takes the still, the census (`census:` setup) and a
  `record` clip. `-ffAutomationRole Client` and `-ffDeckTour` run together. `Back` then lands on the Lobby Browser, a
  classic MainPanel panel to use as the `ui_layout.py check --ref-census ... --ref LobbyBrowser` style reference.
- If a hand-click is the only way: a Windows player's client area is DPI-virtualised (a 1920x1080 window reads 1097x617 in a
  DPI-unaware Python, scale 0.571) and `scripts/agent/post_key.py click:` is in that space. Real clicks need the window foreground AND
  under the cursor (`WindowFromPoint`): another sandbox's topmost player sat over the same centred spot and refused every click until the
  window was moved (`SetWindowPos` to the bottom-right). Never click without both checks.

## Fixtures a new fingerprint surface needs, beyond the three mirrors

`scripts/audit/test_determinism_audit_verdict.sh` reads `ValidationScenarios/determinism-audit/fixtures/*.log`; each `Fingerprint` record needs
the new field (`"mods":"1B"` before `"combined"`). Without it 25 of 88 checks fail with `field shape differs; missing=['mods']`, and no CI job
runs it (it needs a `python3` on PATH; on Windows a one-line shim). Run it after any wire bump.

## A localization row ending in a colon

`scripts/localization/add_rows.py` wrote "The host has these mods and you don't:" as a plain YAML scalar; Unity read an empty key, and
`ControlHighlightTests` and two `ControllerGlyphCoverageTests` failed with "An item with the same key has already been added. Key: ".
Quote any text ending in ":" (fixed in `scalar()`). PyYAML on the 12 assets (Unity tags stripped) names the row.

Related: [[mod-build-and-built-player-testing]], [[ui-pointer-input-needs-os-focus-and-ui-drag-bypasses-the-module]].
