---
name: marshalled-entity-type-precedence-player-item-comet
description: "When adding a new AsteroEntityType (074 T110: Comet), the classification in BOTH capture paths (MarshallingSystem legacy loop + ColumnarWorldCapture) must keep precedence Player > Item > Comet regardless of component-type iteration order: an entity that also carries AsteroItem stays an Item. The first cut typed the 055 legacy fixtures' comets (built ON enemy item ids) as Comet, the loader had no comet prefab, and CombatMoverRailSaveRoundTripTest lost both comets ('expected 2, was 0'). Pinned by CometSaveRoundTripTest.Comet_ThatAlsoCarriesAnAsteroItem_StaysAnItem."
---

# Marshalled-entity-type precedence: Player > Item > Comet (074 T110, 2026-09-19)

**The surface.** Every saved/served entity gets ONE `AsteroEntityType`
(`Assets/Scripts/FFCore/Serialization/AsteroEntityType.cs`), assigned while the capture walks the
entity's component types — in the legacy loop `MarshallingSystem.cs:116-198` and in
`Serialization/Columnar/ColumnarWorldCapture.cs:124-297`. The loader instantiates a prefab PER
TYPE; a wrong type means the wrong prefab, or none.

**The bug.** Appending `Comet` and tagging any entity that carries `FFComponents.Map.Comet` looked
right and passed the new guard, but `CombatMoverRailSaveRoundTripTest` (055 fixtures) builds its
comets ON an enemy `AsteroItem` id and loads them through the ITEM prefab. Typed `Comet`, they hit
the loader with no comet prefab → dropped → "both comets are excluded: expected 2, was 0". The
type assignment depended on which component the walk saw first.

**Rule.** A new type only claims an entity whose `EntityType` is still `Invalid` (or the new type
itself), and both paths write the same precedence Player > Item > Comet in ANY iteration order
(`MarshallingSystem.cs:180-198`, `ColumnarWorldCapture.cs:287-297`). Both capture paths must
change together, and the round-trip suites of EVERY existing fixture family that could carry the
new component are part of the RED→GREEN, not just the new guard
(`Assets/Tests/Serialization/CometSaveRoundTripTest.cs:226`
`Comet_ThatAlsoCarriesAnAsteroItem_StaysAnItem`; `CombatMoverRailSaveRoundTripTest` 55/55).
A missing prefab for the new type must be LOUD (`Dropping restored comet` error), never a silent
skip — the silent skip is exactly how T110 hid for months.
