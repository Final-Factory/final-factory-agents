---
name: determinism-pass-must-be-proven-non-vacuous
description: "A clean determinism verdict proves nothing until you show the run actually exercised the defect: compare the fingerprint hash POPULATION before vs after the action on both peers, and never write an acceptance criterion that requires seeing an ephemeral entity in observe.state."
---

# A determinism PASS is not evidence until it is proven non-vacuous

A paired/three-peer run that places nothing, or whose command was silently rejected, reports
exactly the same "all fields match, zero mismatches" as a real fix. The verdict is identical;
only the cause differs. So a clean verdict is the SECOND half of the evidence — the first half
is proving the run changed the world at all.

**The technique that works** (074 T116, leg t19, 2026-09-20). Take the distinct set of a
fingerprint field's hashes in a window BEFORE the action and a window AFTER it, per peer:

- before hb1100-1400 `census` = {0F02C568C6, 4977C173F4, 7842AE58D8, 9D4E721C3E}
- after  hb1430-1700 `census` = {07C583EE16, 395A0673EE}
- same disjoint shift on `directions`; and the client's before-set and after-set each equalled
  the host's.

That single comparison answers both questions at once: the sets differ, so the action really
mutated the exact surfaces that used to fork; and the peers agree on both sides, so the fix
holds. Use the SET of distinct hashes over a window, not a single heartbeat — many fields
oscillate between two values every heartbeat, so "the hash changed at hb N" is meaningless on
its own.

Sample the fields out of the report directly; they are nested under `fields`, not at the top
level, of the `# audit-record-v1 {"action":"Fingerprint"…}` lines:
`json.loads(line[18:])["fields"]["census"]`.

## Never require an ephemeral entity to appear in a structure snapshot

The same feature's written acceptance bar was "require actual zones in host snapshots". It was
unsatisfiable, and chasing it nearly produced a wrong verdict. A Landing Zone is EPHEMERAL
(`Assets/Resources/ItemEntities/LandingZoneEntity.prefab` carries `EphemeralStructureMarker`) and
never becomes a built structure, so `ffauto:observe.state|nearby` reports zero of them — in the
fixed run AND in the earlier broken run's own saved nearby snapshot — while the placing peer
keeps the items in inventory in both. `placementRejections: 0` and `commandErrors: 0` in
`snapshot/session` on both runs confirmed the command was accepted either way.

What actually existed was visible only in the diagnostic census: n=2 entities per peer whose
component lists were identical except `OutOfPlay`. **The census is the evidence for an ephemeral
entity; a structure snapshot is blind to it.** Before adopting an acceptance criterion written by
an earlier session, confirm the instrument can express it — and if the broken run's own artifacts
fail the criterion too, the criterion is wrong, not the fix.

Related: [built-pair-lab-traps-2026-09-18](built-pair-lab-traps-2026-09-18.md) (`construction.place`
reports "placed" even when the ghost never commits),
[gate probes must be broader than their system](revert-pair-proves-a-widened-instrument.md).
