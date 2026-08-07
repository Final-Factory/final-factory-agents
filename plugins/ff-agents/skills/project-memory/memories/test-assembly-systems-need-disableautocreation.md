# Test-assembly ECS systems MUST carry [DisableAutoCreation]

Every ECS system type defined in a test assembly (`Assets/Tests/**`, FFEditorTests etc.) MUST
be marked `[DisableAutoCreation]`. Unity's default-world bootstrap scans ALL loaded
assemblies — including editor-only test assemblies — and auto-creates any unmarked system in
live play mode.

**Why (caught live 2026-07-21, during Ben's 030 manual pass):** a pipelining test's
`KnnPipelineJitterSystem` (writes `LocalToWorld.x += z*0.01` per tick to every KNN source)
auto-created into the play-mode world. Dynamic entities hid it (transform sync rewrites LtW
from LocalTransform every frame) but STATIC entities (spawner buildings) accumulate the nudge
forever → enemy spawn buildings visibly streaking across the screen at ~2000 u/s (render-only;
simulation state stayed correct — the desync detectors were blind to it). It would also have
corrupted future in-editor paired audits/playtests. Fixed in `4a0c1ed8a` (+ hardened the
pre-existing `PlaceableHelperTest.HelperRunner`).

**How to apply:**

- Adding a system class to a test file → `[DisableAutoCreation]` on it, always. Manual
  creation in tests (`CreateFFSystemForTesting`, `CreateSystemManaged`) is unaffected by the
  attribute.
- Symptom signature if it happens again: presentation-only weirdness in play mode
  (`LocalToWorld` ≠ `LocalTransform` on STATIC entities) that no simulation-side probe or
  fingerprint surface can see. Diff LtW vs LT to detect; the per-tick delta names the culprit.
- Debugging trick that found it: `execute_code` step-diff probes read `LocalTransform`
  (simulation) — for RENDER anomalies also compare `LocalToWorld`; they diverge exactly on
  static entities.
