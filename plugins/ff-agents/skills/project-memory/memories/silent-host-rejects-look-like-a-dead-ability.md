---
name: silent-host-rejects-look-like-a-dead-ability
description: A hotbar ability that "almost never works, nothing happens" can be a SILENT host-side reject, not a broken effect — the UI charge count is a client prediction that can promise more than the host's gate allows
metadata:
  type: project
---

Ben's 2026-09-02 report "the Bat frenzy ability almost never works, nothing happens" was a
SILENT host-side reject, not a broken effect. The hotbar's charge count is a client
PREDICTION (`FleetAbilityCooldownTracker.Charges` = ready ships / `RequiredUnitCount`, from
the per-ship `AbilityCooldown` map in `FleetSummarySystem`), while the 055 T017
request-only conversion (`ecb0d74d4`) had carried Plasma's per-player
`NextAllowedSimulationTimeRaw` gate over to all four ability kinds in
`PlayerAbilityFireClientRequest` — so with 38 Bats the UI promised 9 charges and the host
accepted one cast per 10 s, rejecting the rest with no log. Fixed `f4e3af6a2` (fleet kinds
gated by their ships' cooldowns via the candidate query; Plasma keeps the per-player gate;
ships named by an unconsumed pending intent are excluded from the next cast).

**How to apply:** (1) when converting a local action into a request/apply op pair, find who
OWNED the gate before (per-ship vs per-player) and keep that owner — the UI affordance must
model the exact gate the host validates; (2) the diagnostic tell for this class is in the
live session, not the code: read the actor's saved `DeterministicAbilityFireState` —
accepted event sequences spaced exactly one config cooldown apart while the UI showed
charges means the host was dropping clicks between them. A read-only `execute_code` probe of
the saved state + candidate query answered it in minutes; the host-validation code path was
correct line by line and would never have shown it.
