---
name: live-view-asset-iteration
description: "The live view (w1398): an asset agent streams its sandbox editor's running game into FF Factory beside its chat, and the person drags the shader's own properties as knobs; how to start it, what a knob can and cannot move, the editor's dev-tier agent channel, measured numbers"
metadata:
  node_type: memory
  type: project
  modified: 2026-10-16T03:00:00Z
---

**What it is (w1398, 2026-10-16; the plan is w1393's).** A worker iterating on a look (a glow, a VFX, a shader) can let the
person watch the asset live beside the chat and drag knobs, instead of a 30–60 min build-and-clip round. Ben, w1393:
"the game should just show a preview of that asset rendering in the engine ... change how much this glows".
- **Game half:** FinalFactory #1822, `Assets/Scripts/Behaviours/Multiplayer/AgentControl/LiveLook.cs`. It adds the
  DevOnly ffauto commands `live.frames`, `look.material.list|set|reset`.
- **Portal half:** ff-factory #408, `docs/live-view.md`. It adds the worker tool `live_view` and the `#/live/<sessionId>`
  page.
- **Off by default:** the portal needs config `live.enabled`, which only Ben or an owner turns on.

## Using it as the asset agent

1. Stage the asset in editor play mode as for a capture:
   - a flat new game;
   - `blueprint.place` the structure;
   - `camera.zoom`, `ui.hide|true`.
2. Call `live_view` `{action: "start", materials: [...], fps, width}`.
   - **Name the materials that own the look.** A loaded material by its name works: `CometCatcherMaterial`.
   - A material that only loads when the game first draws it (the comet's `VfxComet`) fails as "no loaded material"
     until then. Its Resources path loads it at once: `Vfx/VfxComet`.
   - Find candidates with `Resources.FindObjectsOfTypeAll<Material>()` filtered by name, then
     `look.material.list|<name>`.
3. **The person's knob moves** reach you as `[live view] <who> set <material>.<prop> to <value>` lines in your
   conversation. The next message from a person starts with them.
   - Knobs are never saved. Keep a value by editing the `.mat` text yourself and checking `git diff` for
     `m_ObjectHideFlags: 32`, per [[play-mode-material-edits-land-on-disk-with-hide-flag-32]].
4. **Stop the view** when done: `live_view {action: "stop"}`.

## What a knob cannot move (measured on beast, w1398)

- **Values set per entity.** A knob edits the loaded material. Neither `_Emission` on `CometHavesterEntranceGate` nor
  on `CometHarvesterConnectorItemGateMaterial` changed the Comet Catcher's pink energy sphere, even set to black. Its
  colour comes from elsewhere (likely a per-entity override). The catcher's tip lights (`CometCatcherMaterial._EmissionAG`)
  did change, on the next frame.
- **A look the shader takes from other properties.** A caught comet (w1332's catch look) ignored `VfxComet._ComaColor`,
  which colours a flyby comet's coma.
- **C# constants, meshes and shader code.** These are still an edit, then a reload or reimport. The view holds the last
  frame (`holding`) and comes back by itself.

## The editor's agent channel in the dev tier

- **The knob and frame commands are DevOnly.** A play session whose channel was started by the saved settings
  toggle runs the `player-safe` tier.
- **The daemon switches it** once, through the editor's MCP bridge (ff-factory `machine/live.ts` `DEV_TIER_SNIPPET`):
  `SessionState.SetBool(AgentChannelHost.DevSessionStateKey, true)`, then `StopChannel` + `StartChannel`.
- **By hand:** run the same snippet with `execute_code`, then read port and token from
  `%USERPROFILE%/AppData/LocalLow/Never Games/finalfactory/AgentControl/session-<editor pid>.json`.
- **No session needed.** `/v1/command` works without opening an agent session (`POST /v1/session`), so the daemon
  never collides with an agent's own.
- **Frame dump:** `scripts/live/live_frames_dump.py --session <file> --out DIR [--knob "<mat>|<prop>|<value>@<s>"]`
  streams to disk and moves a knob mid-run.

## Numbers (measured, beast/slot1 editor, 2026-10-16)

- **Stream rate:** `live.frames|on|30|960` gave 23.2 fps received, with a 64 KB median JPEG (about 11.6 Mbit/s).
  Through the portal page it ran 19–23 fps.
- **Command latency:** `/v1/command` median 12.3 ms, p90 20 ms.
- **Knob to screen:** the next streamed frame.
- **Editor fps by window state:** 52 unfocused, 42 covered by a topmost window, 12.6 minimized. Never minimize the
  live editor.
- **Quality level:** 2 (High) in play mode.
- **Link to the portal:** beast to the portal over the tailnet carries 18–48 Mbit/s sustained. Ben's MacBook reaches the
  tailnet through DERP at 128 ms.
