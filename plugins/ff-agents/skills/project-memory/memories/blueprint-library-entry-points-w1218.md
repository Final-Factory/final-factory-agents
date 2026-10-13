---
name: blueprint-library-entry-points-w1218
description: "Every way a blueprint enters a player's library (SaveNewBp, ImportFolder, Duplicate, InstallWorkshopFile, Load), and why a library-wide rule such as unique link keys must hold on each: w1218 found ImportFolder (#1580) skipped the link-id rule SaveNewBp (#1594) had, so a folder imported twice made a station rewrite the wrong copy."
metadata:
  type: project
---

# The blueprint library's entry points (w1218, 2026-10-13)

A rule over the whole library holds only if every path that adds an entry applies it. The rule here is that no two
blueprints share a link key (`BlueprintLink.KeyOf`, w1146). `FindByLinkKey` returns the first entry in file order, so a
duplicate key sends a linked station's "Update blueprint" rewrite into the wrong file.

The paths, in `Assets/Scripts/Serialization/Blueprints/` of the game repo:

| Path | What it does with the link id |
|---|---|
| `BlueprintManager.SaveNewBp` (Save New Blueprint, edits, a pasted single string) | keeps the id unless the library has its key, else a fresh one; clears `StationLink` (#1594) |
| `BlueprintLibrary.ImportFolder` (a shared folder string, #1580) | the same since w1218 (`GiveOwnLinkId`); before that it wrote every id as it came |
| `BlueprintLibrary.Duplicate` (a new version) | always a fresh id |
| `BlueprintLibrary.InstallWorkshopFile` (a Workshop subscription) | copies the uploaded JSON as it is, link id included: **not de-duplicated** (open as of w1218) |
| `BlueprintLibrary.Load` (files on disk) | takes the files as they are; duplicates already on disk stay |

**Why:** #1594 (link ids) and #1580 (folder import) merged 25 minutes apart on 2026-10-13. The import path never got
the rule, and its tests compared files and folders, not keys. w1218's failing-first test:
`LinkedBlueprintLibraryTest.AFolderImportedTwice_GivesTheSecondCopyItsOwnLinkKey_SoItsStationsRewriteThatCopy`.

**How to apply:** when a change adds a rule over the library (an id, a unique name, a field every blueprint must carry),
grep for every writer of `_entries` and every caller of `Library.Add`. Apply the rule in each, or say why one is exempt,
and test the rule through each path, not only through the one the feature uses. When reviewing a merge night, pair the
merges that touch the same collection.
