# VFX on an entity the simulation removes

w2962 (the Ancient Portal Mover, PR #3113, 2026-11-03): the pack effect folds an Ancient Portal down a beam into the
player's ship, but the pickup op destroys the portal's entity on the heartbeat it applies. Three tries went wrong before
the clip looked right.

- **Snapshot a stand-in before the apply.** A presentation system cannot read an entity the op already destroyed. Copy
  what the effect needs (the model's meshes, materials and pose) into a presentation-only stand-in when the hold
  starts, and animate the stand-in after the apply. Draw only what the camera does (the stand-in followed the
  entity's LOD and culling); otherwise it pops in at full detail.
- **Every part of the effect needs its own fade.** The seal field was a child of the portal and vanished on the apply
  frame with the entity; it needed its own 0.3 s fade that starts with the fold.
- **An additive term added after a dim factor escapes it.** In a shader, `col = base * dim + glow` keeps `glow` at full
  strength while the rest dims. Multiply the whole sum, or the "faint" rings stay bright.
- **Check the watch_video model's "snap" and "vanish" notes against strips.** `watch_video --mode vfx` notes said the
  early release snapped and vanished, but every frame of `transition_strip` over the same span showed a smooth fade.
  Settle each such note with a strip (`--out` is a directory, not a file name) before you change the effect.
- **A built player is capped at 60 fps**, so a VFX cost reads as frame time, not fps: compare `ftGpu`/`ftMain` medians
  idle against the effect (w2962: GPU median 1.48-1.68 ms idle, 1.82 ms during a pack on BEAST's RTX 4080 SUPER,
  measured), under a bench ticket; on BEAST ask `timed_place` first.
