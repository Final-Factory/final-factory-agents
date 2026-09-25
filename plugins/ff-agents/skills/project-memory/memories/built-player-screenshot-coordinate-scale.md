# Built-player screenshot and pointer coordinates

Do not use screenshot PNG coordinates directly with `ffauto:pointer.moveto|x|y|screen`.
The screenshot endpoint defaults to a 1280-pixel maximum edge
(`AgentRequestRouter.ScreenshotAsync`, `AgentRequestRouter.cs:747-786`) and captures the native
`Screen.width`/`Screen.height` before scaling to that cap
(`AgentScreenshotPipeline.cs:247-279,369-389`). Its `X-FF-Width` and `X-FF-Height` headers are
the returned PNG dimensions, not the native view dimensions.

The pointer command takes raw `Input.mousePosition` pixels with a bottom-left origin and compares
them with the live `Screen.width`/`Screen.height`
(`LocalMultiplayerAutomationCommandRunner.cs:6011-6056`). A witnessed 2560×1289 viewport returned
a 1280×644 screenshot; screenshot slot `(752,50)` measured from the bottom-left therefore mapped to about native `(1504,100)`.
Scale each axis from returned PNG dimensions to the native view before moving the pointer.

Do not assume launch `-screen-width`/`-screen-height` is the live size. Startup loads saved display
settings through `Screen.SetResolution` (`DisplaySettingsController.cs:54-70`), so they can
override launch dimensions. Do not assume PlayerPrefs is current either: witnessed stored
3456×2168 values did not match the current view. Prefer read-only native screen metadata when the
harness provides it. Until then,
`ffauto:pointer.moveto|999999|999999|screen` reports the actual view in its bounds warning, but
the command also calls `AutomationPointer.MoveTo`; reset the pointer to the intended coordinate
before clicking.

## Blueprint cleanup requires entities and buffer disposal

`ExecuteBlueprintDrop` now calls both `PlayerDataController.CleanupBlueprintItems` and
`ClearBlueprint` (`LocalMultiplayerAutomationCommandRunner.cs:7808-7820`). The former destroys
owner-scoped live previews; the latter delegates native entry disposal to
`BlueprintTool.DisposeBlueprint`. Calling only `ClearBlueprint` leaves preview entities alive.

Fixed in `0059658fd`; the real two-Mac run `live-upgrade-drop-retry011/upgrade` on 2026-09-10
showed the held two-structure preview and its disappearance after `blueprint.drop`, with both
screenshots inspected. The regression also verifies foreign-owner and unstamped markers survive.
The earlier open-defect warning applies to older builds. Use actual right-click when the test
concerns player input, and use the fixed command for harness cleanup.

## Mac Retina dialog-dismiss recipe (2x scale + Y-origin flip, 074 h6/h7, T171)

On the Mac player the general rule above has an exact, reusable form: a native view 2560×1289
returns a `GET screenshot` of 1280×644 — exactly HALF each axis — with a TOP-LEFT origin (image
convention), while the pointer command's `screen` space is native-resolution with a BOTTOM-LEFT
origin (`Input.mousePosition`). Convert a screenshot pixel `(x, y)` to a pointer coordinate with

```
screenX = 2 * x
screenY = nativeHeight - 2 * y   # 1289 - 2*y at this resolution
```

then `ffauto:pointer.moveto|<screenX>|<screenY>|screen` followed by `ffauto:pointer.click|0|6` (a
non-zero hold-frame count — `0|0` did not register). This is the recipe that dismisses the
"Technology Unlocked" dialog (`TechnologyUnlockedNotificationPanel.cs:56` has no key shortcut,
and dialogs queue one per completed tech) — do it after EVERY research completion, like a real
player would, never through a debug/skip channel. Re-derive the native size per machine/window
before converting; it is not a fixed constant across builds or windows.
