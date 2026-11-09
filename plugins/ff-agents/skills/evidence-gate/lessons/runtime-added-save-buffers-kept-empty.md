# A runtime-added [Save] buffer is kept empty, or says why it need not be

## The rule

When code adds a `[Save]` `IBufferElementData` to an entity at runtime (`AddBuffer<T>`, `AddComponent<T>`, an ECB add, a
`typeof(T)` in a type set) and that entity's prefab does not bake `T`, either list `T` in
`ColumnarWorldCapture.KeepsEmptyBuffer` (`Assets/Scripts/Serialization/Columnar/ColumnarWorldCapture.cs`) or give it a
verdict with a reason in the `SafeToDropEmpty` allow-list of `Assets/Tests/Serialization/EmptySaveBufferGuardTest.cs`.
The fast-suite guard fails the PR otherwise. `EmptySaveBufferJoinCensusTest` then proves the join census for each kept
type with no extra work.

## Why

Both save writers (columnar and legacy `MarshallingSystem`) drop an empty buffer unless `KeepsEmptyBuffer` lists it,
and the loader rebuilds each entity from its prefab. The entity census (`DeterminismStateFingerprint.CensusHash`)
counts component types by presence. So a joiner whose copy lost an empty runtime-added buffer has a different census:
desync at heartbeat 8, RecoveryFailed, client kicked. Players found it four times (HandCraftHeldItem, w3816 / game PR
#3485; PendingRotation; IncomingShieldHit; GuardianSpine). The guard written for w3850 (game PR #3498, 2026-11-09)
found nine more on its first run: PersonalLogisticsRequest, DysonShellRecord, CircuitCalculation, CircuitSetItem,
HaulerStopCircuit, HaulerStopCircuitCondition, HaulerStopHeading, PastedStationStop and
PastedStationStopCircuitCondition.

Keeping every empty buffer by default was rejected: it changes every save and drops the "zero-length buffers are treated
as absent, so prefab defaults survive" contract that load repairs rely on.

## How to apply

- A new runtime `AddBuffer` of a `[Save]` type: ask "can it be empty at a heartbeat, on an entity whose prefab lacks
  it?" Yes or unsure: add the `KeepsEmptyBuffer` line. Provably no (baked on every prefab that gets it, re-added before
  the census, or the component is removed when it empties): an allow-list entry naming the file:line that proves it.
- The guard is a source scan: a buffer added through a generic type parameter is invisible to it, so check that case by
  hand.
- Docs: game repo `Documentation/SaveFormat.md`, the empty-buffer section.
