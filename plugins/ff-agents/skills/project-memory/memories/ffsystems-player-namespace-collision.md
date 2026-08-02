---
name: ffsystems-player-namespace-collision
description: "New systems under FFSystems/Player/ must use namespace FFSystems.Players (plural), not FFSystems.Player"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 5ed349f2-a5df-4fd7-bddf-afc0f517fac7
---

The folder `Assets/Scripts/FFSystems/Player/` uses namespace **`FFSystems.Players`** (plural),
NOT `FFSystems.Player`. A namespace named `FFSystems.Player` collides with the component type
`FFComponents.Player.Player` everywhere in the FFSystems assembly that references `Player`
unqualified, producing a cascade of `CS0118: 'Player' is a namespace but is used like a type`
errors across dozens of unrelated systems (DeathSystem, EnemyCampGeneratorSystem, FleetIdleSystem,
etc.) plus their source-generated `.g.cs` files.

**How to apply:** when adding a system in `FFSystems/Player/`, declare `namespace FFSystems.Players`.
Match `PlayerSimulationPositionReplicationOps.cs` (the existing file there). Same trap applies to any
new namespace segment that shadows a widely-used component type. Related: [[remote-player-presentation-position-bug]].
