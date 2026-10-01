---
description: Drive real uGUI clicks and drags in the editor with a virtual Input System mouse; keep the editor topmost while record_clip runs; adjudicate the blind model review on frames.
---

# Verifying a UI gesture (double-click, drag) in the editor, on video

From w161 (research window double-click + drag reorder, PR #881, 2026-10-01, BEAST sandbox).

**Real pointer input without an OS mouse.** The `ffauto` synthetic pointer (`AutomationPointerInput`)
dispatches down/up/click only: no drag events, no click timing. To exercise the game's real
`InputSystemUIInputModule` in the editor:

- `InputSystem.AddDevice<Mouse>("name")`, focus the Game view (`EditorWindow.Focus()`), then from a
  coroutine `InputSystem.QueueStateEvent(mouse, new MouseState { position = p }.WithButton(MouseButton.Left, down))`
  every frame. The module then produces real clicks, cancels the click when a press becomes a drag, and
  sends `IBeginDrag`/`IDrag`/`IEndDrag`. It works while the editor runs freely; it does not need the OS cursor.
- Legacy `Input.GetKeyDown` / `Input.GetMouseButtonDown` do NOT see the virtual device. Esc and right-click
  go through `InputHelper.InjectKeyDown` and `AutomationPointer.Click`, so UI code that should be drivable
  reads those seams, not raw `Input`.
- A virtual mouse draws no cursor. Add an overlay canvas marker at the pointer, or the clip is unreadable.
- Put the driver in a temporary `Assets/Editor/*.cs` (never committed) rather than pasting it into every
  `execute_code` call; `execute_code` rejects `while (true)`.
- A first click that selects something can cost a long frame, so two clicks 0.13 s apart can arrive more
  than 0.3 s apart by frame time. A double-click detector must restart its window after the first click's frame.

**Clips on a shared desktop.** `record_clip --unity` on Windows records the screen region (ddagrab), so it
records whatever window is on top. Another agent's player came to the front and a 40 s clip was a starfield.

- Keep this sandbox's own editor topmost only while the clip records: `SetWindowPos(hwnd, HWND_TOPMOST, …,
  SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE)` on that editor's pid, then `HWND_NOTOPMOST`. Crop to the Game view
  afterwards with ffmpeg.
- Always open a contact sheet of the clip before trusting it.
- Set the Game view's `lowResolutionForAspectRatios` to false (reflection) on a HiDPI monitor, or the render is
  a small low-res image in a big panel.
- An in-game per-frame capture (`CaptureScreenshotIntoRenderTexture` + `AsyncGPUReadback` piped raw into
  ffmpeg) only reached about 25 fps at 2532x1303. It is not a 60 fps substitute.
- `manage_camera` screenshots can leave the editor paused; check `EditorApplication.isPaused` after one.

**The blind model review is weak on UI.** `watch_video --mode vfx` samples Gemini at 10 fps: it cannot see a
double-click and reported "a single click queued it", and it invented a cleared queue, a missing drag copy and
a tile left on screen. Check every claim against frames and say so in the PR. It did point at one real fault
(the dragged copy had no tile background), so read it, but never act on it unchecked. POP/SNAP/STUTTER flags
on UI clips are instant UI changes and a 50 to 60 fps editor, not faults.

**Cloning a tile for a drag ghost.** `Instantiate` of a `TechnologyButton` loses its state colour:
`ExclusiveToggleVisualUpdater` restarts from a clear background. Call the tile's own setup on the clone.
