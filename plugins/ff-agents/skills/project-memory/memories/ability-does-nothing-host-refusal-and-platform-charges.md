# An ability that "does nothing" for one player: the host refused it, and the charge may come from a Defense Platform

**Learned:** 2026-10-01, w159, a live 4-player game on 0.50.0.61. Ben, a client: "frenzy isnt casting for me
... the animation for the indicator plays but the bats dont deploy", and later "i cant press enter to open
the chat". Fixed by game PRs #876 and #878.

1. **The caster hears nothing back when the host refuses a cast.** The reason is one line in the HOST's
   Player.log: `[PlayerAbilityFire] Refused <Kind> from client N (<name>): <reason>`
   (`PlayerAbilityFireClientRequest.RefusalLine`). The client log shows nothing at all. Ask for the host's
   line before theorising. On the caster's screen a refusal looks like the cast marker shrinking away after
   about a second (`LocalCastPrediction.ConfirmTimeoutSeconds`).
2. **Fleet-ability hotbar charges are not only the player's own ships.** `FleetSummarySystem` counts every
   ship tagged `ValidForPlayerAbility`, and that tag means "THIS peer's own player stands within 150 u (3D)
   of that Defense Platform" (`PlayerEntityProximitySystem`). The host judges a cast by the caster's own
   `NearbyEntity` record (`PlayerAbilityFireCandidates.IsCommandableBy`). A hotbar predicate that differs from
   the host's candidate predicate is a silent dead ability. Code that adds the tag outside the proximity
   system must follow the per-peer rule: `ExecuteShipSpawnCommandSystem.SetupShip` tags a ship only when its
   commander carries the tag. `ShipTransferHelper` tagged on every peer until #876, so everyone saw charges
   for a platform they were nowhere near.
3. **Fastest probe: three built players and the player snapshot.** `python scripts/nightly/poke.py up
   --player <exe> --scenario <id> --dir <scratch> --lab <lab.json>`, then `poke.py snap --dir <scratch> <peer>
   player` and compare `data.abilities[].charges` and `data.fleet` across peers, and `poke.py grep ... host
   'PlayerAbilityFire'`. That showed the phantom charge and the refusal in minutes, after hours of reading
   code had not. A scratch lab file with `"workRoot"` on F: and its own `"port"` keeps it off the nightly lab.
   A scenario needs its fixture key too (`preConnectBlueprint`), and `"windowed": true` for `/v1/screenshot`
   (headless players answer 409).
4. **The reporting player's own save says where their charges come from.** A client writes its own copy of
   every host save (`saves/<name>.zip` on their machine). Loaded single-player in a sandbox editor, Ben's
   showed no Bats in his fleet, one platform holding 14, and his ship parked 142 u from it.
5. **The `ability` invariant monitor judges by the ships the caster commands** (own fleet plus nearby
   platforms' ships, since #876). Before that it failed every platform cast with "no effect".
6. **"Enter does not open chat" is the EventSystem selection, not input state.** `ChatInputRules.CanOpen`
   refuses while an active control is selected. A click selects only controls whose navigation is not None
   (in the HUD: the four quick-control toggles, the tech progress bar, panel close buttons), and `main.unity`
   has `m_DeselectOnBackgroundClick: 0`. Since #878 `UiController` releases the selection a click leaves in
   the game HUD (`ClickSelectionRelease`). To list what a click can select in a running game: every active
   `Selectable` with `navigation.mode != None`.
7. **A player's own explanation of the trigger can be a coincidence.** Ben thought it was app switching. His
   log's `[Focus]` lines showed five focus-gains that did not clear it and no held keys, and entity clicks
   worked in between. Check the claim against the log before building on it.
8. **The M3 refuses synthetic keystrokes over ssh**: `osascript is not allowed to send keystrokes (1002)`.
   A real Cmd+Tab repro there needs Accessibility permission granted by Ben first. `open -a` can switch apps,
   but nothing can press a key or click.
