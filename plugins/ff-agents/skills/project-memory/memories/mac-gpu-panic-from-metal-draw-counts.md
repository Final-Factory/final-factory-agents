# A Mac panics when one Metal pass carries thousands of draws (w2078, 2026-10-24)

The M3 Pro MacBook (m3, 18 GB) crashed three times (Oct 23 12:52, Oct 24 00:54, Oct 24 ~13:36 MDT) with a
WindowServer watchdog panic after GPU MMU faults and `GPURestart`. The cause was the game, not the machine:
while a big save loaded, every structure's hidden overheating glow was drawn, one draw per part (transparent,
depth-sorted entities get one draw each in Entities Graphics): 10,394 single-instance draws of 11,000 in one pass
on c34, 17 frames running. Fix: game PR #2495 (`OverheatingGlowPrefab.Hide`, hide on the prefab, so instances are
born undrawn).

What to know next time:
- **Killing the game does not save the Mac.** Once the GPU faults the panic follows; stop a run *before*, on a
  gauge: `footprint -p <pid>` row `IOAccelerator (graphics)`, its **region count** (healthy ~6k; the panicking
  JustPlay load hit 35.7k in 2 s). Dirty MB moves little; regions are the early warning.
- **Unity's Metal draw path is O(n^2) in the draws of one encoder** (`sample`: render thread 100% in
  `GfxDeviceMetalBase::DrawBuffersBatchMode` / `OverrideConstantBufferBindIndex`; regions grow in
  `AGX::DataBufferAllocator::grow`). Count draws per pass with an `MTLRenderCommandEncoder` interpose dylib
  (`DYLD_INSERT_LIBRARIES`; w2078's `drawcount.m` logs draws, instances and single-instance draws per encoder).
  The render graph merges passes, so an encoder label like `[R] Fold: Planets` holds more than its name says.
- **Load frames render before the first heartbeat.** A presentation hide done in a fixed-group system (first
  heartbeat) is too late for what a save spawns; hide it on the prefab (enableable `MaterialMeshInfo` off;
  `Instantiate` copies enable bits).
- A Windows-built Mac player copied by tar over ssh needs `chmod +x Contents/MacOS/*`, `xattr -cr <app>` and
  `codesign --force --deep -s - <app>` before it starts.
- `player_slots.py launch` on the m3 over ssh refuses with "runs in no sandbox" unless `FF_SANDBOX_ID=<slot>` is set.
- A bench save on the Mac goes in `~/Library/Application Support/Never Games/finalfactory/UserData/saves/`.
- JustPlay's own CPU memory reaches ~9.4 GB footprint (6 GB untagged VM_ALLOCATE) by 50 s of load on the m3, with the
  glow fixed; a footprint cap of 9 GB stops it before the game is ready, so cap on graphics regions/MB instead.
