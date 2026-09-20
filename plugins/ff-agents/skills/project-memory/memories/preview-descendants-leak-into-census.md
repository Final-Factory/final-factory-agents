---
name: preview-descendants-leak-into-census
description: "A held preview root may be excluded while its nested children still enter the census; inspect ownership before globally stripping their component."
---

# Inspect the parent chain before stripping a component

074 T112 reproduced an Atomic Printer placement fork with symmetric CensusDetail at the actual
fingerprint pass: epoch 4 hb 879, host 58/client 56 rows carrying only RotationParameters.
The fork persisted through recovery. Both peers had the real printer and its two spinning
children; the extra host children belonged to the retained in-hand preview, whose root carried
BlueprintItemMarker, BlueprintGhostOwner and OutOfPlay. Dropping that preview healed every
fingerprint field at epoch 6 hb 2339.

`BlueprintPlacementSystem.BlueprintPlacerJob.Execute` clones the confirmed root to retain another
preview. `CensusTypePolicy.BuildDrop` excluded the root; its nested children did not carry the
marker. `CollectCensusRecords` now inherits the existing exclusion through Parent ancestry
(game commit d4da217fb; RED/GREEN and fast suite, live acceptance pending when recorded).

Do not strip RotationParameters globally: `KrilloChargeUpAnimation.KrilloChargeUpAnimatorJob.Execute`
reads the claw transform into the ability projectile. A presentation-looking component can have
simulation consumers elsewhere. Trace consumers, inspect live ownership, and preserve coverage of
real entities. A save/reload may look healed simply because a held preview is not saved.

Evidence: feature 074 tasks.md T112 and M5 lab `xplat/t112-pair2`. Fingerprints, per-pass detail,
parent-chain probes and blueprint.drop together distinguish this from an unsaved built component.
