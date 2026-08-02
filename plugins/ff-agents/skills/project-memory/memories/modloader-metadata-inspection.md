---
name: modloader-metadata-inspection
description: "Mod DLLs are inspected reflection-only (MetadataLoadContext) before Assembly.Load; which plugin DLLs that needs, and a namespace-shadowing gotcha"
metadata: 
  node_type: memory
  type: reference
  originSessionId: bb679653-6d0b-4419-a51f-9c1a60617cae
  modified: 2026-07-24T06:13:05.250Z
---

`ModLoader.LoadIUserModForDll` (Assets/Scripts/FFCore/Modding/ModLoader.cs) inspects a mod
assembly's metadata in an isolated `MetadataLoadContext` BEFORE `Assembly.Load`-ing it into the
default AppDomain. Reason: Unity's Mono runtime can't unload an assembly, and
`Unity.Entities.TypeManager.Initialize()` scans EVERY loaded assembly — so one incompatible mod
DLL aborts type-system init and bricks the game (the infinite `TypeManager.ManagedException` NRE
spam). The old `AppDomain.CreateDomain("TempDomain")` isolation never worked — `Assembly.Load(byte[])`
always loads into the calling domain, and secondary-AppDomain unload is unsupported under Unity's runtime.

MetadataLoadContext needs three runtime plugin DLLs in `Assets/Plugins/Modding/` (fetched via
`dotnet publish` of a netstandard2.0 classlib referencing `System.Reflection.MetadataLoadContext`,
all matched at 8.0.0): `System.Reflection.MetadataLoadContext.dll`, `System.Reflection.Metadata.dll`,
`System.Collections.Immutable.dll`. Do NOT add the 4 netstandard2.0 BCL polyfills from that publish
(System.Memory, System.Buffers, System.Numerics.Vectors, System.Runtime.CompilerServices.Unsafe) —
Unity's Mono already provides them under the .NET Standard 2.1 profile; adding them = duplicate-assembly
conflict. Only works because the game ships the **Mono** scripting backend (IL2CPP can't runtime-load managed DLLs).

GOTCHA: inside `namespace FFCore.Modding` with `using FFCore.Unity;`, writing `Unity.Entities.World`
fails (`CS0234`) because `Unity` binds to `FFCore.Unity`, not global `Unity`. Use
`typeof(global::Unity.Entities.World)`. This shadowing applies anywhere the `FFCore.Unity` namespace is in scope.

The mod-compat version check there is best-effort only: Unity often stamps assembly versions as
0.0.0.0, so it only rejects when both the mod's referenced Unity.Entities and the game's carry real,
differing versions. See [[verify-compile-dll-string-check]] (string literals are UTF-16 in the DLL).
