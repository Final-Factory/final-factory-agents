# CI's edit-mode runner has no ECS world; your editor does

**Learned:** 2026-10-17, w1418 (PR #1849, CI run 39047000208), beast.

A UI helper called from a MonoBehaviour test read `Ecs.EntityManager` before any guard
(`AlertStructureLabels.TryRead`, a new first branch for haulers ahead of the old `SpaghettiConfig.Instance == null`
check). In the sandbox editor every touched test passed: an edit-mode editor keeps
`World.DefaultGameObjectInjectionWorld` alive. In CI's `Test in editmode` there is no default world, so
`Ecs.get_EntityManager` (`Ecs.cs:27`, `World.EntityManager` on a null `World`) threw a NullReferenceException in eight
`WarningIconButtonTest` cases.

**How to apply:**
- Code that UI tests reach without building a world guards with `Ecs.Ready` (`World is { IsCreated: true }`; a plain
  null check misses a disposed world) before the first `Ecs.EntityManager`, and keeps that guard ahead of any branch
  you add in front of an older guard.
- Prove it locally with the case CI has: in the test's SetUp keep `World.DefaultGameObjectInjectionWorld`, set it to
  null, restore it in TearDown (`Assets/Tests/UI/AlertStructureLabelsNoWorldTest.cs`). A local pass with the editor's
  world proves nothing about CI.
