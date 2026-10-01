# A shader's fragment stage must not re-derive a choice the vertex stage made

**Learned:** 2026-09-30, w139 (launch blocker): "a white box flashing by my ship and other players" on
0.50.0.58. Fixed by FinalFactory #850 (`b9a0d30b2`); follow-up #854.

## What happened

`VfxExhaust.shader` draws the afterburner as a volume: when `burner > 0` the vertex stage lays a screen-aligned
quad over the whole plume and sets `local = (0, 0, uv)`; otherwise it draws the flame's billboard. The fragment
stage made the same `burner > 0` choice from the INTERPOLATED level. The level came from an exponential fade
(`lerp(level, 0, 1 - exp(-dt * rate))`), which never reaches 0.

- About 3.4 s after every dash the level passed through about 1e-36 to 1.2e-38. The vertex stage read it as lit.
  The interpolator underflowed it to 0 (perspective-correct interpolation multiplies by 1/w), so the fragment
  stage took the billboard path with `local = (0, 0)`: the white-hot nozzle colour on every pixel of the box, for
  about ten frames. Bloom spread it. It looked like a lighting bug.
- The level then stuck at 1.4e-45 for good: `a * (1 - k)` rounds back to the smallest denormal.
- It was on every ship that dashed, remote players included, and only "sometimes": once per dash, seconds later.
  The afterburner's own clips all ended before 3.4 s.

## Rules

1. **Decide in one stage.** If the vertex stage picks a geometry or mode, pass the decision on in a form the
   fragment stage cannot read differently: snap the value to 0 below a floor in the vertex stage and branch in
   the fragment stage at half the floor, and declare per-instance values `nointerpolation` (VfxBeam, VfxComet,
   VfxDeathExplosion, VfxHoverField, VfxRocketPlume and now VfxExhaust do).
2. **An exponential fade needs a floor.** Snap to exactly 0 below something invisible (1/256 here). Test it: the
   value written to the shader is exactly 0 within a bounded time and never between 0 and the floor.
3. **`x > 0.0` on a faded value is a trap** anywhere a tiny value changes what is drawn, not how bright it is.
4. **Record a clip well past the effect's end.** Four seconds after the dash would have caught this.

## Finding one like it

- Pin the per-instance value from a dev override and sweep it down through 1e-30, 1e-36, 1.2e-38 (the smallest
  normal float), 1e-40 and 1.4e-45, capturing each. On D3D11 / RTX 4080 the box showed at 1.2e-38 to 1e-36 only;
  denormals read as 0 in both stages there. Other GPUs were not tested.
- `Stop NaNs` is off on the game camera (`m_StopNaN: 0` in `main.unity`), so a NaN pixel from any shader near a
  ship would also show as a flashing box through bloom. It was not the cause here, but check it for the next one.
- **The editor compiles an edited shader's variants asynchronously.** For the first seconds after a shader edit
  the object is not drawn at all. A capture taken then shows "no effect", which reads as a pass or as a broken
  shader. Check `ShaderUtil.anythingCompiling`, or capture twice.
