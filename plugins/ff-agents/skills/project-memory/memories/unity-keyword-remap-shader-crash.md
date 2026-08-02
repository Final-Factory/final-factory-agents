---
name: unity-keyword-remap-shader-crash
description: Known Unity engine bug crashing the asset import worker on shader fallback keyword remap (ParticlesUnlit); diagnosed 2026-07-01
metadata: 
  node_type: memory
  type: project
  originSessionId: 586fd72b-f4f8-4376-999f-b817f3cac528
---

Recurring AssetImportWorker crash (`code=10054` transport error in the main editor) is a **known Unity engine bug**, NOT project code/packages/cache.

- Stack: `ReloadUpdatedAssets → ReloadAssetIfLoaded → Shader::AwakeFromLoad → ResolveFallback → KeywordRemap::Init → LocalSpace::Find`.
- Crashing asset: URP stock `ParticlesUnlit.shader` (confirmed from the crash minidump, which contained `shader/ParticlesUnlit` + GUID `0406db5a14f94604a8c57ccfbc9f3b46`). Fires during mass asset reload ("231 updated asset objects reloaded").
- Matches Unity issue "Crash on keywords::LocalSpace::Find when reimporting specific assets." Root cause: engine accesses **stale resources** during keyword remap while resolving a shader Fallback on reimport/reload. Reproduces on Windows; affected 6000.0.67f1 (project is on 6000.0.71f1).
- **Fixed in 6000.3.13f1 / 6000.4.2f1 / 6000.5.0b2 / 6000.6.0a2 — no 6000.0.x LTS backport listed.**
- Survives a full `Library` rebuild (reproducible from source).

**Why not the packages:** the entities/entities.graphics rollback (commit c7f1fc48e) was **2026-05-28**, five weeks before the crashes; `packages-lock.json`/`manifest.json` unchanged since. Correlation was coincidental. See [[mod-abi-package-pinning]].

**How to apply:** Trigger is mass reimport/reload while editor is live (build-target/platform switching during multi-depot Steam builds is a known trigger). Mitigate: reimport/switch platforms with editor closed or `-batchmode`. Try latest 6000.0.x patch (same LTS stream = no package/mod-ABI risk) in case of a quiet backport. Moving to 6000.3 LTS fixes it but forces URP/entities bumps that reopen the mod-ABI issue.
