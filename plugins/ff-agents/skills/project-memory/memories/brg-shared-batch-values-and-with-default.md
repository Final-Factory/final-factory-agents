---
name: brg-shared-batch-values-and-with-default
description: A BatchRendererGroup batch value without the per-instance bit is ignored by any shader property read WITH_DEFAULT (Shader Graph's hybrid per-instance properties, URP-style DOTS_INSTANCED_PROP_WITH_DEFAULT): it reads the material's value instead
metadata:
  type: reference
---

# BRG: a shared batch value is invisible to a WITH_DEFAULT property

w1627, 2026-10-20 (LothDesktop). The Dyson shell's record renderer (`DysonShellRecordRenderSystem`, game repo) drew
nothing for a day. Its culling emitted draws, and the GPU buffer read back right. The shell shaders read
`_DysonShellLocal0..2` with `UNITY_ACCESS_DOTS_INSTANCED_PROP_WITH_DEFAULT` (Shader Graph's hybrid per-instance
properties do the same). `LoadDOTSInstancedData_float4(default, metadata)` in `UnityDOTSInstancing.hlsl` takes the
batch value only when the metadata has the per-instance bit (`0x80000000`). A shared batch value (no bit) falls back to
the material's value. Here those were zeros, so every vertex sat at one point and the draw was invisible, with no error.

- A value that is the same for a whole batch and read `WITH_DEFAULT` goes on a per-batch **copy of the material**
  (`new Material(src)` + `SetVector`, registered with the BRG), not in the batch's metadata. Only properties read with
  the plain `UNITY_ACCESS_DOTS_INSTANCED_PROP` (e.g. `unity_ObjectToWorld`) honour a shared batch value.
- Check before debugging culling: grep the shader's input include for `WITH_DEFAULT` on each property you feed shared.

Two traps from the same request:

- **Bench code compiles only in a player build.** `FF_SHADER_BENCH` code (`ContentShaderBench*`) is behind
  `extraScriptingDefines` of `Editor.ShaderBenchBuild`, so the editor never compiles it: an `error CS0136` in it
  surfaced 15 minutes into a player build. Build the bench player right after a bench edit, or keep the edit trivial.
- **Bench clips on a fixed capture clock vs a simulation-driven look.** A look driven by the simulation clock (heartbeats
  advance on the wall clock, `HeartbeatSystem`'s Stopwatch) turns at each arm's own frame rate under
  `Time.captureFramerate`, so two arms drift apart frame by frame. Pin the look's clock per captured frame
  (`DysonShellStep.ClockPin`) for a before/after, and film any event the simulation places (orphans spawned where the
  shell is) on the game's own clock, with no offset.
