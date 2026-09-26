# Toggling an enableable component back on needs IgnoreComponentEnabledState

**Learned:** 2026-09-26, in a perf A/B probe that hid and showed the old comet tail quads by toggling
`MaterialMeshInfo` (an enableable component).

An ordinary `EntityQuery` over `MaterialMeshInfo` (or any enableable component) matches only entities where that
component is ENABLED. Once the probe disabled the quads, the next "show" pass found none of them. All 720
renderers stayed off, and the "tails drawn" half of the A/B measured nothing, with no error anywhere.

**Rule:** any code that re-enables an enableable component must build its query with
`EntityQueryOptions.IgnoreComponentEnabledState`, or keep the entity list from the disabling pass. Before trusting
a toggle, count the enabled entities after the "on" step (the probe that exposed it:
`em.IsComponentEnabled<MaterialMeshInfo>(e)` summed over an `IgnoreComponentEnabledState` query).
