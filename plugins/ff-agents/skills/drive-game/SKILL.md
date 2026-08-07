---
name: drive-game
description: Drive the running Final Factory game in the Unity editor via the MCP bridge — enter play mode, inject keyboard input (press or hold keys, open the in-game menu), and load saves. Use when asked to run the game, interact with it, press/hold keys, open the menu, or otherwise control the live game from Claude. Also the canonical screenshot recipe (both capture channels, Free Aspect, the GameView-focus trap) that the playtest/massdriver skills and the UI + playtest-harness docs all point at. Proven gameplay recipes (menus, saves, crafting, placement, research) live in recipes.md next to this file.
---

# Driving the Final Factory game from Claude

## ⛔ MANDATORY preflight — run BOTH checks, every time

Run these **before you start driving the game** AND **before you conclude the bridge or editor is
wedged**. No exceptions: every driving failure recorded in this project so far was one of these two
checks being skipped, and each takes about ten seconds.

### Check 1 — is a scene actually open?

Read `mcpforunity://editor/state` and look at `editor.active_scene`.

| `active_scene` | Meaning | What to do |
|---|---|---|
| `name: "main"`, `path: "Assets/Scenes/main.unity"` | Correct. | Proceed. |
| `name: ""`, `path: null` | **NO SCENE IS OPEN.** | Load it before anything else (below). Do not press play, and do not diagnose anything else first. |
| any other scene | Wrong scene. | Load `main` before play. |

Pressing play with no scene (or the wrong one) **deadlocks the boot forever**: it freezes in
`playmode_transition` with `is_changing: true`, stalls right after `ConfigInitializerSystem created`,
never builds the `ItemConfig` singleton, and leaves only `Default World` + `LoadingWorld*` with no
game world. `assets.is_updating` stays `false` throughout, so it is a true deadlock — waiting longer
and pumping `Step()` will NOT fix it, no matter how many frames you pump.

```
manage_scene(action="load", path="Assets/Scenes/main.unity")
```
(Equivalent to double-clicking the scene in the Project view. Requires **Edit mode** — stop play mode
first. Re-read `editor/state` afterwards and confirm `active_scene.name == "main"`.)

⚠️ **The scene can vanish out from under you.** It is not enough to have checked once at session
start: verified 2026-08-01, an editor that reported `active_scene: main` earlier was later found with
`path: null` in Edit mode, and the play session launched from that state produced the deadlock above.
Re-check it at the start of every driving attempt.

### Check 2 — are frames actually advancing?

Two `Time.frameCount` reads. Nothing else diagnoses a "frozen" game.

```csharp
return UnityEngine.Time.frameCount;   // call twice, a few seconds apart
```

| frameCount between two probes | What it means | What to do |
|---|---|---|
| **Unchanged** | Editor is occluded (backgrounded). The player loop is FROZEN, not throttled. | Pump it yourself: `EditorApplication.Step()` — see below. |
| **Advancing on its own** | Editor is visible/free-running. Healthy. | **NEVER `Step()`** — it silently pauses the editor. |
| **Advances only when you `Step()`** | Confirms the occlusion freeze. | Keep pumping; this is normal and fine. |

`play_mode.is_changing: true` for a long time on an unfocused editor is the **expected** signature of
the occlusion freeze — not a wedge. The bridge, `EditorApplication.update`, and `execute_code` all
keep answering normally while the player loop is frozen, so "the bridge responds" proves nothing
about the game. (Occlusion freeze proven 2026-07-12 on macOS; re-confirmed on Windows 2026-08-01,
where a play-mode transition sat at `is_changing: true` for 29 minutes purely because the window was
behind others, and 300 `Step()` calls advanced `frameCount` by exactly 300.)

### Never report "wedged" without both

A missing scene and an occluded editor produce nearly identical symptoms — and neither is a wedge.
State what the two checks returned when you report a problem. "The editor is stuck" with no
`active_scene` value and no frameCount pair is not a diagnosis. If a bridge call errors with
`instance not found`, re-read `mcpforunity://instances` before escalating: a domain reload drops the
session briefly and it returns on its own (proven 2026-08-01).

## The three "editor looks stuck" traps — tell them apart

They share symptoms. The two preflight checks separate them; guessing does not. **None of these is a
wedged editor.**

| | **No scene open** | **Occlusion freeze** | **Compile blocked on a play-mode exit** |
|---|---|---|---|
| Symptom | `is_changing: true`, boot never progresses | `is_changing: true`, boot never progresses | `activity.phase: compiling` that never ends, state `sequence` frozen |
| Tell | `active_scene.path: null` / `name: ""`; only `Default World` + `LoadingWorld*` | `is_playing: true`, editor **unfocused**, frameCount frozen | `is_playing: true` **and** `is_changing: true` while compiling |
| Cause | Play pressed with no/wrong scene loaded | OS backgrounded the editor | A `refresh_unity(compile)` was issued mid play-mode transition |
| Fix | `stop` → `manage_scene` load `main` → `play` | `Step()` pump, or the user focuses the window | `manage_editor(action=stop)` — clears it instantly |
| Do NOT | pump `Step()` — frames advance and it still never boots | stop play mode; it's not broken | conclude "hung" from a frozen `sequence` alone |

The first two are the easiest pair to confuse, because **`Step()` "works" in both** — frames advance
either way. Only `active_scene` distinguishes them, which is why Check 1 is mandatory before Check 2.
(Proven 2026-08-01: 900 pumped frames read as "boot still in progress" when the real cause was
`active_scene: null`; the world list — `Default World` + `LoadingWorld0..3` — was the confirming tell.)

**Compile-blocked recovery order — do this BEFORE reporting a wedge or notifying the user:**
1. `manage_editor(action=stop)` — re-issue it even if an earlier `stop` already returned
   `"Exited play mode."`, because that success is reported optimistically and the transition can
   still be pending.
2. Re-read `editor/state`: `is_playing`/`is_changing` should both be `false`, and
   `last_domain_reload_after_unix_ms` should be NEWER than your edit.
3. Only if that does not clear it, `stop` → `play` → `stop` to force the transition through, then
   re-issue `refresh_unity`.

High process CPU does not rule out any of them — Unity keeps burning cores (Burst) while blocked.
(Compile-wedge proven 2026-07-31: a 6+ minute "compile" cleared instantly on `stop`, domain reload
finished within seconds.)

## Control channels

1. **`execute_code` — the primary surface.** Compiles via Roslyn on macOS AND Windows
   (`"compiler":"roslyn"`). Use it to inspect/mutate live ECS state, drive uGUI menus by reflection,
   call `SaveGameManager`, and pump frames. It is also the RIGHT way to check Log-level progress
   markers, because `read_console` generally does not surface plain `Debug.Log` (only warnings and
   errors) — poll game state instead of grepping for log lines.
   **Caveat:** code is wrapped as a *method body* — no `using` directives, use fully-qualified names.
2. **Trigger-file channel — keyboard input only** (`execute_code` cannot synthesize input).
   Write one command into `dev_command.trigger` at the project root with the Write tool.
   `DevCommandWatcher` (`Assets/Editor/DevCommandWatcher.cs`, `[InitializeOnLoad]`) polls it on
   `EditorApplication.update`, is readiness-gated on `InputHelper.Instance` (so you can write it any
   time without racing boot), then deletes it and injects via `InputHelper.InjectKey`.

   | Command | Effect |
   |---|---|
   | `escape` or `menu` | Inject Escape — opens/closes the in-game menu |
   | `key:<KeyCode>` | Single-frame press, e.g. `key:Tab` |
   | `key:<KeyCode>:<frames>` | Hold N frames, e.g. `key:LeftShift:30` (`GetKeyDown` once, `GetKey` for N, `GetKeyUp` at end) |

   **Reach is limited.** Injection only reaches legacy-input consumers
   (`GetKeyDown`/`GetKey`/`GetKeyUp`): Escape, discrete hotkeys, held modifiers. WASD movement and
   E/T/V/C/Space use the new Input System (`FFInput` `PlayerController` InputActions) and are
   **unreachable** — `key:W:60` will not move the player. Every panel those keys open has a
   HUD-button or `execute_code` path instead (see recipes.md).
3. **Mouse is not injectable.** Read directly via `Input.GetMouseButton*`/`Input.mousePosition` in
   ~38 sites across ~23 files (no chokepoint); uGUI clicks go through the EventSystem. UI clicks can
   be simulated via EventSystem (recipes.md); world-mouse would need a refactor.

## `Step()` rules

```csharp
for (int i = 0; i < 300; i++) UnityEditor.EditorApplication.Step();  // one frame each, rendering included
return "frame=" + UnityEngine.Time.frameCount;                       // ALWAYS verify it advanced
```

- **Only on an occluded/frozen editor.** On a free-running editor a 300–500 Step batch advances
  frameCount by ZERO and leaves the editor **paused** — silently freezing it. (Proven 2026-07-14:
  this wedged the host of a paired MP session and the client's join timed out `ClosedByRemote`.)
  If a peer stops responding mid-session, check `EditorApplication.isPaused` FIRST.
- **Cap ~600 Steps per `execute_code` call, counting the SUM across loops in that call.** A 2800-step
  batch — and separately a loop totalling 3000 — blocked the editor main thread past the bridge
  timeout; every later call times out for minutes. A timed-out call may still have fully executed:
  re-sync with a light `frameCount` probe once the bridge answers.
- **When you finish driving, clear the pause**: `UnityEditor.EditorApplication.isPaused = false`.
  `Step()` leaves the editor paused, so skipping this makes the game look dead the moment the user
  focuses the window.
- **When you finish driving, ALSO clear the pointer**: any leg that issued `ffauto:pointer.*` MUST
  end with `ffauto:pointer.clear` (or `PlayerController.AutomationPointer.Clear()`) — on normal end
  as much as abnormal. The position override is a static (`AutomationPointer._positionOverride`)
  that survives play-mode cycles while domain reload is off, so a skipped clear leaves the user's
  NEXT session reading a frozen mouse position — selection, hover, and ability indicators all
  ignore the real mouse, which presents as a gameplay regression (cost a live diagnosis 2026-08-04,
  057 US3 probe leg).

## Standard workflow

1. **Pin this project's editor instance** (`mcpforunity://instances` → `set_active_instance`), then
   read `mcpforunity://editor/state` for `ready_for_tools` and `play_mode.is_playing`.
2. **Run the MANDATORY preflight at the top of this file — Check 1 (`active_scene`) and Check 2
   (`frameCount`) — now, before `play`.** Do not skip Check 1 because you checked earlier in the
   session; the scene can be unloaded out from under you. A missing scene also looks identical to a
   wiped-Library subscene hang, so establish it first and you rule out both.
3. **A compile error also silently blocks play mode** — entering play "succeeds" but
   `Application.isPlaying` stays false. Confirm a clean compile before diagnosing a bad boot.
4. **Enter play mode:** `manage_editor` action `play`.
5. **Wait for boot: ~30–40 s of RUNNING frames, i.e. roughly 1800–2400 frames at 60fps.** Budget that
   before calling a boot slow or hung — a few hundred pumped Steps is not a boot. ❗The game boots to
   the **MAIN MENU (TitleScreen), NOT into a game**; to get in-game you must drive New Game / Load
   Game (recipes.md). Progress probes: `ItemConfig` singleton exists ≈ config loaded; a clean boot
   ends with `System Start Controller finished loading...` and no error flood.
6. **Send input:** write to `dev_command.trigger`; confirm via `read_console` filtered for
   `DevCommand` (e.g. `[DevCommand] Injected key: Escape`).
7. **Stop when done:** `manage_editor` action `stop`.

## 📸 Screenshots — THE canonical recipe (all channels)

> **Single source of truth.** The `playtest` skill, `massdriver-visual-e2e`, the `game-driver`
> agent, `recipes.md`, `Documentation/Agent-Playtest-Harness.md` and `docs/UI-Architecture.md` all
> point HERE. Fix this section; don't re-copy it.

**Prerequisite, once per editor session — Free Aspect.** A blank / all-white capture is the #1
screenshot failure and it is almost always this: `ScreenCapture` reads at `Screen.width/height`,
so if the Game view is pinned to a fixed resolution larger than its docked render target the
readback fails (console: `CaptureScreenshot ... requested a region that exceeds the active Render
Target sized [W×H]`). Fix: `execute_menu_item` → `Final Factory/Dev/GameView Free Aspect`
(`Assets/Editor/DevGameView.cs` sets `selectedSizeIndex = 0` by reflection). **EDIT mode only, and
flaky for the first 1-2 calls after a compile — retry 2-3×.** Manual fallback: the Game view
toolbar's aspect dropdown → "Free Aspect". The setting persists.

**Channel A — composited `manage_camera` (DEFAULT: no focus needed, works occluded, includes the
UI overlay).**

- `manage_camera` action `screenshot`, `capture_source: game_view`, `include_image: true`,
  `max_resolution: ~640`, and **do NOT pass `camera`**.
- Why no `camera`: that renders the camera directly, which in this pipeline comes back **BLANK**
  (the game's custom `ManualCameraRenderer`) *and* excludes `ScreenSpaceOverlay` canvases. The
  default **composited** path on THIS setup includes the menu/HUD overlay.
- Occluded editor: the capture lands on the next pumped frame.

**Channel B — `ScreenCapture` + focused GameView (when Channel A returns blank/stale, or you need
a full-resolution PNG).** Writes to disk; then Read the PNG.

```csharp
var gvType = System.Type.GetType("UnityEditor.GameView, UnityEditor");
var gv = UnityEngine.Resources.FindObjectsOfTypeAll(gvType)[0] as UnityEditor.EditorWindow;
gv.Focus(); gv.Repaint();
UnityEngine.ScreenCapture.CaptureScreenshot("<scratchpad>/shot.png"); // absolute path
UnityEditor.EditorApplication.Step(); UnityEditor.EditorApplication.Step(); // capture lands in a stepped frame
```

- PNG stale/missing → no frame ran; pump more steps.
- Degenerate `Screen` dims (e.g. 2560x20) → the GameView wasn't the active target; `gv.Focus()`
  is what fixes that.
- ⚠️ **NEVER `gv.Focus()` while a blueprint is live in hand** — the OS focus click can commit the
  blueprint at whatever world position happens to be hovered. Use Channel A instead.
- This is an in-editor `EditorWindow.Focus()`, which Claude issues itself. **Nothing here requires
  the user to bring the Unity app to the foreground**, and it does not un-occlude the editor —
  the player loop still only advances on `Step()` (see Check 2 above).

**World-only (no UI) — not available today.** The only way to exclude overlay UI would be the
camera-specified render, which is blank here (feature 020, T020). Nearest fallback:
`manage_camera` `capture_source: scene_view`, which always works but shows world geometry + editor
gizmos rather than the game's HUD.

## Compiling and testing around play mode

- **Recompiling stops play mode, and the editor will NOT recompile while playing.** Any change to
  `InputHelper`/watcher code requires `stop` → `refresh_unity (compile)` → wait ready → `play` →
  re-boot. Changing `InputHelper` rebuilds **FFSpaghetti** (slow).
- **`execute_menu_item` only fires in EDIT mode**, and is flaky for the first 1–2 calls after a
  compile (menu not yet registered) — retry 2–3×.
- **A cancelled/aborted `run_tests` PlayMode job wedges the bridge's test tracking permanently.**
  Every later `run_tests`/`refresh_unity` returns `"tests_running"`/`"busy"`. The state is
  server/plugin-side in memory: neither an editor restart NOR an `/mcp` reconnect clears it. Only
  recovery found (both classes are `internal`, package `com.coplaydev.unity-mcp`):
  ```csharp
  var asm = System.Reflection.Assembly.Load("MCPForUnity.Editor");
  asm.GetType("MCPForUnity.Editor.Services.TestJobManager")
    .GetMethod("ClearStuckJob", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static)
    .Invoke(null, null);
  asm.GetType("MCPForUnity.Editor.Services.TestRunStatus")
    .GetMethod("MarkFinished", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static)
    .Invoke(null, null);
  ```
  then `refresh_unity(compile:request, mode:force)` before the next run. (Proven 2026-07-20.)
- **Long PlayMode NUnit runs driven by `Step()` on an occluded editor are unreliable** — distinct
  from the plain freeze: the run can WEDGE mid-test with `frameCount` still advancing while the
  test's own async chain (`UniTask.NextFrame()` continuations, `SaveGameManager`'s
  `WaitUntilOrTimeout` polling) stops resuming, so no new log lines ever appear. Passive waiting does
  not help. Recovery: `stop` + the bridge-wedge reset above + a forced `refresh_unity` + restart the
  run. Budget 2–3 attempts, and prefer short single-testcase runs over long corpus sweeps.
- **Don't hammer the bridge in a degraded state.** A long session with a broken boot once hung the
  editor's main thread and required force-quitting Unity.

## Files

- `Assets/Scripts/UI/InputHelper.cs` — `InjectKey(key, holdFrames)` / `InjectKeyDown(key)` plus the
  `GetKeyDown`/`GetKey`/`GetKeyUp` injection plumbing.
- `Assets/Editor/DevCommandWatcher.cs` — the trigger-file command channel.
- `Assets/Editor/DevLoadSave.cs` — load-a-save dev hook (menu `Final Factory/Dev/Load NewGame`).
- `Assets/Editor/DevGameView.cs` — forces the Game view to Free Aspect so screenshots aren't blank.
- `Assets/Editor/UnityMcpStdioAutoStart.cs` — auto-starts the stdio MCP bridge on editor open.

## Recipes

Proven, dated gameplay recipes — driving menus, starting a new game, loading saves, crafting,
abilities, blueprint placement, research, inventory, objectives, and the full tutorial playthrough
notes — live in **`recipes.md`** next to this file. Read it when you need to *play*; this file is
what you need to *drive the editor safely*.

For the **complete `ffauto:` command vocabulary** (every family, args, descriptions), read the
game repo's generated **`docs/ffauto-command-reference.md`** — do not grep
`LocalMultiplayerAutomationCommandRunner.cs`; the doc is generated from its dispatch table and
`python scripts/generate-ffauto-reference.py --check` keeps it honest.
