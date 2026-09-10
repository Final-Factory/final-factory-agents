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
