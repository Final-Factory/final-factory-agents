---
name: mod-abi-package-pinning
description: Why Entities/URP versions matter for mod ABI — the 1.3.10 pin is HISTORY, re-read Packages/manifest.json before quoting versions
metadata: 
  node_type: memory
  type: project
  originSessionId: 586fd72b-f4f8-4376-999f-b817f3cac528
  modified: 2026-07-27T02:40:55.067Z
---

⚠️ **The pinned versions below are HISTORICAL — re-read `Packages/manifest.json` before quoting any version.** Verified 2026-07-26 on `master`: `com.unity.entities` **1.4.7**, `entities.graphics` **1.4.20**, URP **17.3.0** (`Packages/manifest.json:22,23,36`), Unity **6000.3.19f1** (`ProjectSettings/ProjectVersion.txt`). The 1.3.10 pin was lifted at some point; what stays durable is the reasoning, not the numbers.

Mod compatibility once pinned the Entities package versions. Commit c7f1fc48e (2026-05-28, "Roll back packages that ... broke ABI compatibility for mods") rolled `com.unity.entities` 1.4.5 → **1.3.10** and `com.unity.entities.graphics` 1.4.18 → **1.4.8** (1.4.8 pins entities exactly 1.3.10), on Unity 6000.0.71f1 with URP/core 17.0.4.

**Mod ABI surface (still current):** mods ship a managed C# DLL (loaded via `Assembly.Load`, `ModLoader.cs`), an optional Burst native DLL (already exact-version-locked — `ModLoader.cs:310` disables it on version mismatch), and AssetBundles. The managed DLL compiles against `Unity.Entities` (core), Burst, Collections, `Unity.Mathematics.FixedPoint`, and FFCore/FFComponents — **not** `Unity.Entities.Graphics` (the mod API `IUserModLoader` is gameplay/entities/config only; no `.asmdef` references the graphics package).

**How to apply:** an Entities *core* bump is the mod-breaking move; `entities.graphics` alone is harmless in principle, but its version constraints drag core along (1.4.12 requires entities 1.3.14, 1.4.15+ require 1.4.x). URP can't be downgraded (major version is bound to the editor version; Unity 6 requires URP 17.x). Since the pin has been lifted, treat any claim that "mods force entities 1.3.10" as stale — check the manifest and ask before acting on it. Related: [[unity-keyword-remap-shader-crash]].
