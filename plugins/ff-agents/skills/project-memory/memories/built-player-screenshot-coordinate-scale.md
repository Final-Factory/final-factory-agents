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

## Blueprint cleanup caveat

`ffauto:blueprint.drop` clears `BlueprintMetaItem` without disposing its entries
(`LocalMultiplayerAutomationCommandRunner.cs:7808-7820`). The normal player path calls
`PlayerDataController.ClearBlueprint`, which delegates to `BlueprintTool.DisposeBlueprint`
(`PlayerDataController.cs:757-761`); that method disposes every entry before clearing the buffer
(`BlueprintTool.cs:667-676`). The automation shortcut can therefore leave an orphan preview.

This harness defect is still unfixed. When validating the real player's clear action, use the
normal right-click input and do not treat a ghost left by `blueprint.drop` as gameplay evidence.
