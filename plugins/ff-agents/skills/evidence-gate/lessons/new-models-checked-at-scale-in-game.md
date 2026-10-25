---
name: new-models-checked-at-scale-in-game
description: "A new or changed in-world 3D model (an item, structure, ship, projectile or pickup) is checked for size in a built game beside the objects it sits among, at gameplay zoom, before its PR: an item on a connector and in an inserter hand next to ordinary items. A still of the model on its own, or an editor preview, does not count. The PR's Evidence carries a 'Scale:' line; pr_evidence.py fails a PR that adds or changes a model without one."
date: 2026-10-25
---

# New models are checked at scale, in the game, beside their neighbours

**Rule.** Whenever you add or replace a 3D model that is drawn in the game world (an item, a structure, a ship, a
projectile, a pickup), take a still of it **in a built player, at gameplay zoom, beside the existing objects it sits
among**, and compare its size with theirs before the PR:

- an **item**: on a connector and in an inserter hand, next to ordinary items (an Iron Plate, a Circuit), and in a
  bot's cargo where the game draws one;
- a **structure**: beside the structures of its footprint and tier (a 3x3 building beside an Assembler);
- a **ship**: beside the ships of its class in the same fleet;
- a **projectile or pickup**: beside the weapon or the ship that fires or drops it, and an existing one of its kind.

The still names what is beside the model and gives a verdict: its size matches theirs, or the ratio you measured and
why it is meant to be so. A still of the model on its own, a prefab preview, the Scene view or a model viewer does not
count: nothing in them says how big the model looks next to what a player already knows.

The PR's `## Evidence` carries the line:

```
Scale: shots/repair-pack-on-connector.png, shots/repair-pack-inserter-hand.png: the Repair Pack beside Iron Plates and
Circuits on the same connector and in the same inserter hand, at gameplay zoom in the built player; its size matches
theirs (0.9x an Iron Plate's width)
```

or `Scale: n/a (<why: a re-tint, a material or texture only, size unchanged, not drawn in the world>)`, which shows in
the verdict for the reviewer.

**Why.** w1157's Repair Packs (#1596, merged 2026-10-13) added the Repair Pack item with a new mesh
(`Assets/Art/Content/RepairPack/RepairPack.asset`) and its connector prefab
(`Assets/Resources/ConnectorEntities/RepairPackConnectorItem.prefab`). Nobody looked at it beside the items it travels
with. Ben, 2026-10-25 (w2204): "the repair pack connector item is comically large. make sure you test these visually
when you add new models to the game in the future". The fix is w2203. The Hero art check (w1497) did not see #1596:
it counts model files (fbx, blend ...), and this mesh was a Unity `.asset`.

**How to apply.**

1. Before the PR, launch the built player from the slot pool (`ff-agents:editor-ops`), put the model where a player
   meets it among its neighbours (for an item: a connector carrying it between ordinary items, an inserter picking it
   up), and take the still at the game's normal camera zoom, not zoomed in on the model.
2. Look at the still yourself and say what it shows: the neighbours by name and the size verdict. If it looks out of
   scale, fix the mesh or the prefab's scale and take the still again.
3. Put the `Scale:` line in the Evidence (checklists/visual.md 5k, merge.md). `pr_evidence.py` fails a PR whose diff
   adds or changes a model file (fbx, obj, blend, glb, gltf, dae) or a mesh `.asset` under `Assets/Art/{Content,Models,
   ItemArt}/`, or adds a world prefab under `Assets/Resources/{ConnectorEntities,ItemEntities}/` or
   `Assets/Prefabs/EffectsEntities/Projectiles/`, without a filled line; for an item it also needs "connector" and
   "inserter" in it. Icons, sprites, UI, effects and VFX folders, textures and third-party packs do not trigger it.
4. A review note about a model gets the critic's question "Is it in scale with its neighbours?"
   (`pr_evidence.py --note N --questions Q`); the ui-critic asks it of any still that shows world art.

**What the tool cannot see.** An edited prefab is not counted (one map-icon PR, #1987, edited 70 of them; a file list
cannot tell a scale edit from those), so a scale change made only in a prefab's transform is yours to check by this
rule without the tool's prompt. Measured on the game repo's 600 pull requests merged 2026-10-01..25: the check fires on
9, eight of them new models and one a re-tint (#2309) that takes `Scale: n/a`.
