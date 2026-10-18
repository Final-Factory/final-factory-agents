# NUnit collection asserts compare Transforms by their children

**Fact (w1450, 2026-10-18, FinalFactory #1905).** `CollectionAssert.Contains`, `CollectionAssert.AreEqual` and
`Assert.That(x, Is.EqualTo(y))` on lists of `Transform`/`RectTransform` use NUnit's structural equality, and
`Transform` is `IEnumerable` (it enumerates its children). So two different windows, each with one empty child,
compare as equal, and a test that should fail passes. `SaveBlueprintCoverTest` passed on the code it was written to
catch until its asserts compared references.

**How to apply:** assert Unity objects by reference: `Assert.IsTrue(list.Contains(window))` (`List.Contains` uses
`Object.Equals`), `Assert.IsTrue(a == b)`, or compare `GetInstanceID()`. Run a new test red against the old code before
trusting its green.
