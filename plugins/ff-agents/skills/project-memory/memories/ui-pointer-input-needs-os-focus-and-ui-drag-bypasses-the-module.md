---
name: ui-pointer-input-needs-os-focus-and-ui-drag-bypasses-the-module
description: A UI drag that "does nothing" in an unfocused editor or player is not a product bug (InputSystemUIInputModule idles without OS focus); ffauto ui.drag without `real` never goes through the module; recipe for an edit-mode gesture test
metadata:
  type: reference
---

# Pointer input needs OS focus; `ui.drag` without `real` bypasses the input module

2026-10-10, w875 (Blueprint library drag and drop, Discord feedback thread 1558448051662749797). Hours went on
"real mouse drags do nothing" that was never the game.

- **`InputSystemUIInputModule.Process` skips every pointer while `!eventSystem.isFocused`** (package
  `InputSystemUIInputModule.cs`, `Process`). An editor or built player that is not the foreground window ignores a
  physical mouse, a virtual `Mouse` device and queued state events alike: hover is stale, no drag begins, and a
  release elsewhere clicks nothing. It looks exactly like a broken gesture. Check `Application.isFocused` first.
  An editor stepped with `EditorApplication.Step()` while paused never runs the module at all (unpause).
- **On a shared desktop focus is stolen within seconds** by other sandboxes' players. `SetForegroundWindow` (with an
  ALT key tap first) then verify `GetForegroundWindow` is your pid *immediately* before the command; abort if not.
  Never drive the OS mouse (`SetCursorPos`, `mouse_event`) there: the clicks land in whichever window is on top, and
  a helper that picks "the newest `AgentControl/session-*.json`" starts talking to another sandbox's game. Pin the
  session by pid.
- **`ffauto:ui.drag` (and `pointer.*`) go through `AutomationPointerInput`**, which raycasts and dispatches the drag
  events itself; the real module is never involved, so it can pass while a real mouse fails. Add `|real` (w875): a
  virtual Input System mouse drives the module. It still needs focus. `research.drag` does the same for the research
  queue.
- **An edit-mode test can drive the real module**: `InputTestFixture` by composition, `OnEnable` by reflection for
  `EventSystem`, the module and the raycaster then `EventSystem.UpdateModules()`, `EventSystem.m_HasFocus = true`, a
  `BaseRaycaster` stand-in (an edit-mode canvas never draws, so `GraphicRaycaster` finds nothing: every `Graphic.depth`
  is -1), `Helpers.EditSafeDestroy.Now` instead of `Destroy`. Recipe and reasons in the game repo's
  `Documentation/UI-Pointer-Gesture-Tests.md`; example `Assets/Tests/Blueprints/BlueprintPanelPointerDragTest.cs`.
