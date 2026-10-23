# A static ComponentType[] field initializer can throw in a built player only

**Seen:** w1773, 2026-10-22, biscuit, Linux development player (FinalFactory #2232,
`StationGridEntityPanel`). A UI panel (a MonoBehaviour in FFSpaghetti) had a static field built at type
initialisation:

```csharp
private static readonly ComponentType[] OpensBySelfTypes = { ComponentType.ReadOnly<...>(), ... };
```

The editor and the EditMode tests were fine. In the built player the first touch of the type threw
`TypeInitializationException`, so the panel never worked. Nothing failed before a built-player tour
opened it.

**Do instead:** build such arrays lazily, on first use
(`static ComponentType[] _types; static ComponentType[] Types => _types ??= new[] { ... };`), or in
`OnCreate`/`Awake`, never in a static field initializer of a UI type. Any change that adds one gets a
built-player run that opens the panel, not only tests.
