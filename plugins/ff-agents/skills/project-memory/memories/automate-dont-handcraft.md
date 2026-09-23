---
name: automate-dont-handcraft
description: Ben's standing rule — when an agent PLAYS Final Factory, hand-crafting and hand-carrying are for bootstrapping only; research bots, their inputs and fleet ships must come from automated production lines, the way a human plays.
---

# Automate, don't hand-craft (Ben, 2026-09-23)

Ben, watching the honest co-op game: "this is unsustainable … you should be automating research bot
production, it's pretty much the whole point of the game … learn to automate and play the game like a
human, not just handcraft."

In sittings h2–h3 of the 074 honest game, the three play agents hand-crafted several hundred research
bots with `craft.queue` and hand-carried inputs, and the briefs told the fleet agent to do it "when
idle". That moved objectives but is not how the game is played, and it cannot reach Stellar Science
(~800 planetary + ~3,000 asteroid bots' worth of points).

**How to apply**
- `craft.queue` and carrying items are bootstrap tools: the first miners, a construction bot, one-off
  structures. Anything consumed continuously comes from a line: mining → printers/assemblers → belts →
  a Ship Assembler with a research-bot (or ship) recipe.
- Routing is automatic and deterministic: a station-origin craft is routed by
  `ExecuteShipSpawnCommandSystem.FindNetworkedCommander` to the closest commander with a free slot on the
  assembler's logistics network (research station, or Ship Yard as buffer). Put the assembler on the
  same network as the stations. Full recipe: `docs/HowToPlay.md` §2b.
- Trap: players are commanders on the Default network, so a player within ~60 tiles of an assembler
  swallows its output into their own fleet (HowToPlay §6, "The PLAYER competes for station-crafted
  ships"). That is where "missing" crafted ships go. Keep clear of running lines.
- Driver: when briefing play agents, never suggest hand-crafting as a fill-in task; when an agent drifts
  into mass hand-crafting, redirect it to building or feeding a line. The honest-coop-play skill and its
  briefs carry this rule.
- Related: [[ui-screenshot-worst-case-before-done]] (agents also look at the game, via windowed peers).
