---
name: a-new-ffauto-command-touches-six-places
description: Adding an ffauto command in a harness file (RegressionHarnessCommands) needs six edits; the runner's explicit Catalog[N] list is the one that is missed
metadata:
  type: project
---

w1386 (2026-10-18, `marker.edit`, game repo PR #1935). A command added to `RegressionHarnessCommands` needs:

1. its `Catalog` entry (name, args, summary);
2. its `case` in that file's `TryExecute`;
3. its `case` in `LocalMultiplayerAutomationCommandRunner`'s dispatch switch (the fall-through list that forwards to the file);
4. **one more `RegressionHarnessCommands.Catalog[N]` line in the runner's combined catalog** (`LocalMultiplayerAutomationCommandRunner.cs`,
   an explicit index list, ~line 1468). Miss it and `CommandTiersTest` reports the LAST entry of the file's array missing
   (`marker.list`), not the new one, because the new entry shifted it past the list's end;
5. a `CommandTiers` row (tier and a one-line reason);
6. the golden in `CommandTiersTest` from `python scripts/ffauto_catalog_hash.py` (both the constant and the `ComputeHex()` string),
   and a line in `docs/ffauto-command-reference.md`.
