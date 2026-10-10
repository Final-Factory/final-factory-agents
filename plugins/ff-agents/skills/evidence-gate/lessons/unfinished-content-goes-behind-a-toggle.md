---
name: unfinished-content-goes-behind-a-toggle
description: "New game content or a feature that is not ready for players merges to develop behind a feature toggle (FFCore.Features.FeatureToggles), off for players, instead of waiting on a branch or being hidden by deleting it. Simulation toggles are fixed per game and the host's set wins; Presentation toggles are local. The game repo's FeatureToggleLifecycleTest enforces dates, use and self-contained gating."
date: 2026-10-10
---

# Unfinished content goes behind a feature toggle

**Rule.** New items, recipes, buildings, research nodes, belt models or features that are not ready
for players merge into `develop` behind a toggle and ship turned off for them. Do not keep them on a
long-lived branch waiting for a review, and do not hide them by removing them from the config list.

**Why.** Ben, 2026-10-10 (w937): "can we add a feature toggle implementation so you can just merge new
content and stuff like connector items i'm checking to develop and i can test stuff off develop
without worrying about branches and stuff and also not exposing unfinished stuff to players". The
w27 connector models sat on a draft branch for 11 days, re-merged with develop and moved to Ben's m5
to be looked at (w934). Item ids are the configs' load order, so deleting content to hide it shifts
every later id: gated content must stay loaded.

**How to apply** (the game repo's `Documentation/Feature-Toggles.md` is the full guide; spec 091).

- Declare the toggle in `Assets/Scripts/FFCore/Features/FeatureToggles.cs`: id, kind, owner (a person
  and the request id), created, remove-by, removal plan, description, `DefaultOnInDev`.
- Pick the kind. **Simulation** if the fixed tick reads it or it changes the entities a fixed-tick
  system creates (items, recipes, research, belt prefabs): fixed for a game, saved, the host's set wins
  on join, folded into the desync fingerprint. **Presentation** only for what one player sees. Unsure:
  Simulation.
- Gate it: the **Feature Toggle** field on the item or research asset, **Connector Item Prefab
  Feature Toggle** for a belt model, `FeatureToggles.IsOn(FeatureToggles.X)` in code. Asset gates name
  a Simulation toggle. Gated content stays self-contained: nothing ungated needs or hands out a gated
  item, and a node that unlocks one carries the same toggle.
- Test it both ways (`using (FeatureToggles.OverrideScope(FeatureToggles.X, true))`); a Simulation
  toggle gets a two-peer run with it on (`/ff-agents:determinism-audit`, or a nightly scenario with
  `"features"`).
- Tell the person how to see it: editor menu **Final Factory > Feature Toggles**, `-ffFeatures=<id>`
  (a Steam launch option on a develop build), or the console `feature <id> on`.
- Shipping it: clear the gates, delete the toggle, add its id to `FeatureToggles.Retired`. The fast
  suite (`FeatureToggleLifecycleTest`) fails when a toggle passes its remove-by date, so every toggle
  ends in a decision.
