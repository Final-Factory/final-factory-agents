Request: w684

**TL;DR:** On a Steam Deck whose Steam has not loaded our Steam Input manifest, every hint showed keyboard keys (Build 87). Now such a Deck first offers Steam our shipped manifest, and if Steam still gives the game no action set it draws the bundled Deck layout (our own atlas) instead of keys. Keyboard/mouse PC players and PC gamepads are unchanged. Not verified on real Deck hardware.

## Cause (code path; the Deck's Player.log was not available, so this is by trace, not by log)
- `ControllerPrompts.Live` is set only when `SteamInputLive.Connected` (`SteamInputLive.cs`: `_count > 0 && _set != 0`). `_set` is `GetActionSetHandle("ingame")`, which is 0 until Steam has loaded our manifest.
- Steam loads it only when the partner site's Application → Steam Input is set to "Custom Configuration (Bundled with Game)" and published (`docs/SteamInput.md` "Making it the default"; `specs/w644-deck-release/audit.md` row M1 lists this as Ben's open step). With `_set == 0`, `SteamInputBridge.Update` took the not-connected branch, `SetPrompts(false)`, so `ControllerPrompts.Active` stayed false and every label stayed a key. A Deck with no manifest matches Ben's report exactly. Whether the publish was done is not visible from the repo.

## Fix
1. `SteamInputLive.Poll`: on Steam hardware, 3 s with no action set handle → `SetInputActionManifestFilePath` with the shipped `steam_input_manifest.vdf` (Valve's route "running without the game installed in Steam or when you have local changes", Action Manifest page). Under Proton the Linux path is offered first (Wine's `wine_get_unix_file_name`, else `Z:` → `/`), the Windows path last. Once only, never when Steam already has the set, so it is a no-op after the publish. A PC (non-Steam hardware) is untouched.
2. `SteamInputBridge.ChoosePromptSource` (pure, tested): controller in use + Steam connected → Steam's buttons; controller in use + a Deck + 8 s with no action set → the bundled Deck layout via the new `ControllerPrompts.Fallback`; anything else → keys as before.
3. One-time Player.log lines: `Steam Input: Init=… IsRunningOnSteamDeck=… steamHardware=… wine=…`, `N controller(s) connected, input type …`, `action set 'ingame' handle=…`, `SetInputActionManifestFilePath(<path>) returned …`, `N/M action handles, K actions with a button in the set`, `Controller prompts: Keyboard|Steam|BundledDeck (IsSteamDeck=…, steamConnected=…, controllerInUse=…, settled=…)`.
4. Testing flags: `-ffAssumeSteamDeck` (a player acts as a Deck with no manifest), `-ffDeckTourFallback` (Deck tour with the fallback choosing the prompts).

## Evidence

Kind: other   <!-- which prompts are chosen on a Deck; no new art, effect or animation: the glyphs are the existing atlas, so stills of the built player, not clips -->

| Claim | Basis | Where |
|---|---|---|
| A Deck with no action set from Steam drew keys because `ControllerPrompts.Live` needs `_set != 0` | SOURCED: code trace `SteamInputLive.cs` Connected, `SteamInputBridge.cs` Update; `specs/w644-deck-release/audit.md` M1. Not confirmed from a Deck log (none available) | code |
| On such a Deck the bundled Deck glyphs now show instead of keys | MEASURED: built player at 1280x800, log `Controller prompts: BundledDeck (IsSteamDeck=True, steamConnected=False, controllerInUse=True, settled=True)`, hotbar census glyphs 45, keyWords 0 | /srv/fff/review/w684-deck-glyph-fallback/F02-hud-hotbar-hints.png |
| A Deck with origins, a PC keyboard player and a PC gamepad keep their behaviour | MEASURED: `DeckPromptFallbackTests` (12), full fast suite 8718 run, 8702 passed, 0 failed, 16 existing ignores | EditMode run, slot4 |

Built player: yes (development build of this branch, fallback tour)
Looked: yes, F00, F02 and F03 at 1280x800, the glyphs are Deck atlas glyphs, no keyboard keys

Tests: FFEditorTests 8718 run, 8702 passed, 0 failed
Save compatibility: none, no saved state is touched

Not verified: on a real Deck: that Steam accepts `SetInputActionManifestFilePath` under Proton and then loads our configuration; the Proton path conversion (never run under Wine); that Steam's default configuration presents the Deck to Unity as a gamepad, which the fallback uses to switch back to glyphs after a key press; the actual cause on Ben's Deck (no Player.log)

## Checklist for Ben
1. Partner site, only if Steam Input is not already published (never touched by this PR): Final Factory (1383150) → Application → Steam Input → Steam Input Template "Custom Configuration (Bundled with Game)" → path `finalfactory_Data/StreamingAssets/SteamInput/steam_input_manifest.vdf` → tick Xbox, PlayStation, Generic → Save → Publish. Steps and reasons: `docs/SteamInput.md` "Making it the default".
2. On the Deck, next development build: glyphs (R5, L, trackpad, A/B/X/Y…) on the hotbar, objectives and the keybindings screen, no letter keys. In Steam's controller settings for the game, "Final Factory (official)" should list our action titles.
3. Player.log (Deck: `~/.local/share/Steam/steamapps/compatdata/1383150/pfx/drive_c/users/steamuser/AppData/LocalLow/Never Games/finalfactory/Player.log`), grep `Steam Input:` and `Controller prompts:`. Healthy: `action set 'ingame' handle=<nonzero>` then `N/M action handles` and `Controller prompts: Steam`. Fallback: `handle=0 after 3s`, `SetInputActionManifestFilePath(...) returned True|False`, then `Controller prompts: BundledDeck`. If it says `Keyboard` on a Deck: send that log.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
