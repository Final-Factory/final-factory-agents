---
name: editmode-test-of-a-view-controller
description: EditMode tests of a MonoBehaviour that builds views from a static store (map markers): OnEnable never runs, Destroy logs an error and keeps the object
metadata:
  type: project
---

w1386 (2026-10-18, game repo PR #1935, `PrivateWaypointEditTest.TheMapViews_FollowAnEditToPrivateAndBack_OnTheOwnersMapAndAnotherPlayers`):
testing `MapMarkerDisplayController.RefreshView` with the real `Assets/Prefabs/Map/MapMarker.prefab` in EditMode.

- `AddComponent` in EditMode calls neither `OnEnable` nor `Start`, so the controller subscribes to nothing: invoke
  `OnEnable` (and `OnDisable` in `finally`) by reflection, and set private fields (`_mapMarker`, `_viewer`) the same way.
- `Instantiate` of the prefab works and does not run its `Awake`; `SetUp` paths that read `PlayersManager` guard on `Ready`.
- `Object.Destroy` in EditMode logs "Destroy may not be called from edit mode!" as an error (the test fails on the unhandled
  log) and leaves the object in the hierarchy. Set `LogAssert.ignoreFailingMessages = true` for that test, and read the live
  views from the controller's own dictionary, not `GetComponentInChildren` (it returned a dropped, stale view: a false
  "not cyan" failure).
- Prove the test bites: revert the production hunk (`git diff ... > p; git apply -R p`), run it RED, re-apply.
