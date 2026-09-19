---
name: accepted-casts-log-nothing-objective-counters-are-presentation-hooks
description: "074 T104: '[PlayerAbilityFire]' lines are REJECTS only -- an accepted ability cast logs nothing, so 'no line' is a non-instrument; prove an apply from the actor's DeterministicAbilityFireState.LastAppliedEventSequence or the ships' Frenzy/AbilityCooldown (a checkpoint save carries them). The tutorial counters FrenzyUsed/PlasmaBoltUsed/AfterburnerUsed hang off the presentation hook AbilityNotifierService.OnAbilityUsed, which the three MOUSE cast sites raised and ffauto:ability.cast never did -- the ability was never dead, the objective just never counted. Since e9bfe40c5 the notifier is raised once in PlayerAbilityFireDispatch.Dispatch and the silent candidates.Length==0 reject records EmptyCandidateReject."
---

# Accepted casts log nothing; objective counters are presentation hooks (074 T104, 2026-09-19)

**The trap.** "Frenzy never accepts on a fresh game": `ability.cast` returned `kind=Frenzy,actor=1`,
the hotbar showed a charge, no `[PlayerAbilityFire]` line followed, `frenzyUsed` stayed 0. A whole
handoff theorised an id-less commander. The editor probe showed every cast APPLIED (all four Bats got
`Frenzy` + a 9.9 s cooldown ten frames later; the player's `DeterministicAbilityFireState` Frenzy
`LastAppliedEventSequence` went 1→2→3) while `ObjectivesTracker.FrenzyUsed` stayed 0 — and the leg's
own checkpoint save already carried `lastSeq=1`.

**Rules.** (1) `[PlayerAbilityFire]` lines are rejects only; silence proves nothing. Read the actor's
fire state or the ships' components, or load the checkpoint save in the editor — prove the instrument
can go positive before believing a negative. (2) Objective counters of the tracker class
(Frenzy/Afterburner/PlasmaBolt/MapUsed/…) are bumped by `AbilityNotifierService.OnAbilityUsed`
(`ObjectivesTrackingSystem.OnAbilityControllerOnCastingFinished`, subscribed at
`StartController.cs:385`) — a presentation hook the mouse sites raised beside their dispatch. Any new
cast path (verb, AI, replay) must raise it or the objective silently never completes. Now raised once
in `PlayerAbilityFireDispatch.Dispatch`; the mouse sites dispatch only. (3) Frenzy charges = ready
Bats ÷ 4 recomputed every heartbeat from the ships' own cooldowns; fresh Bats carry an initial
cooldown, so the charge appears ~2 minutes after the craft.
