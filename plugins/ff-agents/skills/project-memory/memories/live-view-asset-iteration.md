---
name: live-view-asset-iteration
description: "The live view (w1398; w1498: the session is a conversation, the person says what to change and the agent edits shader, material, VFX Graph or model live, knobs optional; measured round trips): an asset agent streams its sandbox editor's running game into FF Factory beside its chat, and the person drags the shader's own properties as knobs; how to start it, what a knob can and cannot move, the editor's dev-tier agent channel, measured numbers"
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

## A Live view session is a conversation, not a knob panel (w1498, 2026-10-18)

Ben, w1498: "why dont we test out the live editor for some of this new art and vfx?" and "keep in mind the knobs arent as
important as me just being able to iterate conversatoinally with the agent to improve the art model or vfx". So for new
art or VFX the session works like this:

1. **Offer it after the concept stills** (the hero-art rule, evidence-gate `checklists/visual.md` 5e): "I can open a Live
   view of the picked concept in the real scene, with the game's lighting, so you can tell me what to change and watch it
   change." The offer waits for the person's yes (`waiting_on_person`); the sidebar's "Live view: go" button is theirs.
2. **Stage the asset in its real scene** (a late-game save or a flat new game, the structure or ship placed, the camera
   at the angle a player sees it, `ui.hide|true`), `live_view start`, and tell the person the page's address.
3. **Make whatever change the person describes**: shader code, a material, a VFX Graph, a mesh or model, a new layer of
   the effect. Do not steer them to the preset knobs; the knobs are optional extras for numbers they want to drag.
   Say roughly how long each kind of change takes before you start it (numbers below) and say when it is on screen.
4. **Which changes keep the view up and which do not** (what updates without a reload:
   `Documentation/Live-View-Knobs.md` in the game repo, from PR #1862, lists the knobs that show nothing):
   - a shader or shader graph edit, a `.mat` edit, a texture: save the file, then `refresh_unity` (or
     `AssetDatabase.Refresh()`); the stream stays up and the new look is on screen within seconds;
   - a C# change (a presentation system, a constant): Unity holds the compile while the game is in play mode, so it needs
     leaving play, a compile and reload, re-entering play and reloading the save; the page shows the last frame ("holding")
     and the daemon brings the stream back by itself when the new play session is up (it re-asks for the dev tier and
     the new port every 3 s);
   - a mesh or model reimport: changes the asset the render uses; not measured (a guess: seconds, no reload).
5. **When the person is happy**, the final values go through the normal PR flow: write the values into the `.mat`, shader,
   graph or code defaults yourself (a knob is never saved, and `git diff` for `m_ObjectHideFlags: 32`), fill the `Hero art:`
   line, and record the smooth built-game clip (`watch-video`). **Stop the Live view (`live_view stop`) and the editor
   (`mcp__machine__unity` stop) when done**; a view left up holds the editor from idling out.

**Round-trip numbers (MEASURED, beast/slot1 editor, 2026-10-18, JustPlay save copy, a busy machine so the stream gave
only about 1.5 fps at 320 px; the game side only, the daemon and portal hops come after it):**

| Change | Edit to the editor having it | Edit to the new look on screen |
|---|---|---|
| A colour in a small URP unlit shader (file write, `AssetDatabase.Refresh()`) | refresh returned in 0.8 to 1.7 s (median 0.9, 6 trials) | first live frame 1.6 to 3.0 s after the edit (median 2.0), about one frame interval of it the stream |
| A real VFX shader (`VfxComet.shader`, a comment appended) | refresh 0.9 to 1.7 s | nothing compiling after 2.6 to 4.7 s |
| `BlackHoleRaymarch.shader` | refresh 1.1 to 1.3 s | nothing compiling after 3.2 to 3.3 s |
| `Standard-LowPoly_SG.shadergraph` (every building's shader) | refresh 0.8 to 1.0 s | nothing compiling after 10.2 to 11.6 s |
| A C# presentation system (comment appended) while in play mode | compile held for the whole 300 s watched (`isCompiling` true, play kept) | after leaving play the bridge answered again at 94 s; then re-enter play and load the save (a minute or more) |

The stream stayed up through every shader refresh (no drop in 6 trials). Polling granularity was about 0.6 s. Frame
change was read as a mean-colour jump in the dumped frames; one trial's frame read a compile-time transient first.

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
- **C# constants and meshes.** A knob cannot reach them: they are an edit, then a reload or reimport. A shader edit is
  an edit plus a refresh, a few seconds, with the stream up (the table above). A C# edit drops the view to `holding`
  until play is re-entered, and then the view comes back by itself.

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
