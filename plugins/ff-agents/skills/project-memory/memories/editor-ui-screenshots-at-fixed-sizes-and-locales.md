---
name: editor-ui-screenshots-at-fixed-sizes-and-locales
description: Recipe for menu/UI screenshots in the editor at 1080p, 1440p and Steam Deck size in several languages, captured by a coroutine; the transient-frame, lost-custom-size and paused-editor traps; staging lobby browser rows without Steam
metadata:
  type: reference
---

# Editor UI screenshots at fixed sizes and in several languages

2026-10-02, w210 (lobby browser Public/Private column), BEAST sandbox. Thirteen browser shots and
seven dialog shots came out of two `execute_code` calls. Companion to
[[ui-screenshot-worst-case-before-done]] and [[editor-host-mp-ui-worst-case-screenshots]].

**Sizes.** The Game view renders at a fixed resolution whatever its docked size, and both
`manage_camera` (no `camera`) and `ScreenCapture.CaptureScreenshot` then write that resolution
(checked: 1920x1080, 2560x1440, 1280x800 PNGs from a 1447x744 window). Pick the size by
reflection: `UnityEditor.GameViewSizes` → `currentGroup` → `GetGameViewSize(i)` to find the
index of a `FixedResolution` w×h, `AddCustomSize(new GameViewSize(FixedResolution, w, h, name))`
when it is missing, then `GameView.selectedSizeIndex = i`. A custom size is lost when the editor
restarts, and its old index then points at another entry (a "Steam Deck" run came out
1920x1200): look the index up by width and height every time, and check the PNG's dimensions.

**The first frame after a size switch is wrong.** The capture taken right after
`selectedSizeIndex` changes has no UI at all, or the panel without its list rows. Let about 20
frames pass before capturing.

**Locale.** `LocalizationSettings.SelectedLocale = locale` (find it by `Identifier.Code`: `de`,
`zh`, `ja`, `ko-KR`, `ru`). Text set from code is not re-localized: rebuild it after the switch.

**Drive it from a coroutine**, started on any live MonoBehaviour, so one call does the whole
matrix: for each size, set it and wait 20 frames; for each locale, set it, wait 10, stage the UI,
wait 20, `ScreenCapture.CaptureScreenshot(absolutePath)`, wait 20; write a `done.txt` at the end
and poll for it from the shell. `execute_code` accepts a local iterator function
(`System.Collections.IEnumerator Run() { ... yield return null; }`).

- Nothing runs if the editor is paused: `EditorApplication.isPaused` was true after an earlier
  screenshot call, and the coroutine sat at frame 516 until it was cleared. Set it false first.
- `execute_code` blocks `System.IO.File.Delete`; remove old shots from the shell. A capture to
  an existing name through `manage_camera` gets a `-1` suffix instead of replacing it.
- Captures under `Assets/Screenshots/` are gitignored. Convert the ones a PR needs to JPEG
  (quality 80) under `specs/<item>/proofs/` and link them as
  `https://github.com/Final-Factory/FinalFactory/blob/<sha>/<path>?raw=true`.

**Lobby browser without Steam.** The sandbox has no Steam, so no real lobby exists.
`LobbyBrowser.ShowRows(IReadOnlyList<LobbyBrowserRow>)` builds the list from plain row data
(name, private, password, players, max); both are internal, so build the list by reflection
(`typeof(List<>).MakeGenericType(rowType)`, the row's one constructor). Open the panel with
`MainMenuPanel.HandleMultiplayerPressed()` then `MultiplayerSetupController.UpdateState(
BrowseLobbies)`. The refusal and password dialogs come from
`HandleClientJoinRejected("<category>")` and `ShowPasswordPrompt(default(Lobby), message)`.

**What the stills found**, both invisible in English: a `TextMeshProUGUI` cloned from a
neighbouring cell kept that cell's 8 px left margin, which cut the Russian label off
("Публичн…"), and passing the TMP to `LocalizationHelper.LocalizeString` swaps in the locale's
font, which sits a few pixels lower than the Khyay text beside it. Shoot Russian for width and a
CJK language for baseline.
