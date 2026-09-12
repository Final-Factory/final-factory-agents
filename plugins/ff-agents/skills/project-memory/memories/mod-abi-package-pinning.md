---
name: mod-abi-package-pinning
description: Why Entities/URP versions matter for mod ABI, and why you must re-read Packages/manifest.json before quoting any version number
metadata: 
  node_type: memory
  type: project
  originSessionId: 586fd72b-f4f8-4376-999f-b817f3cac528
  modified: 2026-07-27T02:40:55.067Z
---

⚠️ **Never quote a package version from this file — read `Packages/manifest.json` and
`ProjectSettings/ProjectVersion.txt`.** Mod ABI questions are always answered from the manifest,
never from memory or from a doc. There is no Entities pin in force: any claim that "mods force
entities 1.3.10" is stale, and the durable content here is the reasoning, not a number.

**Mod ABI surface:** mods ship a managed C# DLL (loaded via `Assembly.Load`, `ModLoader.cs`), an optional Burst native DLL (already exact-version-locked — `ModLoader.cs:310` disables it on version mismatch), and AssetBundles. The managed DLL compiles against `Unity.Entities` (core), Burst, Collections, `Unity.Mathematics.FixedPoint`, and FFCore/FFComponents — **not** `Unity.Entities.Graphics` (the mod API `IUserModLoader` is gameplay/entities/config only; no `.asmdef` references the graphics package).

**How to apply:** an Entities *core* bump is the mod-breaking move; `entities.graphics` alone is harmless in principle, but its version constraints drag core along (1.4.12 requires entities 1.3.14, 1.4.15+ require 1.4.x). URP can't be downgraded (major version is bound to the editor version; Unity 6 requires URP 17.x). Read the manifest, then ask before acting on a version change that moves Entities core. Related: [[unity-keyword-remap-shader-crash]].
