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
- **Skipping that `OnDisable` breaks other tests, not yours** (w6647, 2026-11-27, game PR #4458,
  `MovementKeysObjectiveTest.ACardShownAgainAfterARebind_ShowsTheNewKey`): the test invoked `ObjectiveItem.OnEnable` by
  reflection, which subscribed the card to the static `ControllerPrompts.Changed`, and then only `DestroyImmediate`d it.
  EditMode's destroy does not call `OnDisable` on a plain MonoBehaviour, so the destroyed card stayed subscribed and
  every later test that refreshed the prompts threw `NullReferenceException`: CI run 46110444706 had 60 red tests in
  `ControllerPromptsTests`, `TrackpadTapTests`, `RadialHotbarFeedTests`, the Deck glyph tests and more, none of them the
  new one. Put the asserts in `try` and the `OnDisable` invoke in `finally`. To catch it locally, run the new test
  first in one `run_tests` call together with two or three classes that fire the same static event.
- A HUD card that a menu disables misses every event fired while it is hidden (a keybind change in Settings): have it
  redraw in `OnEnable` as well as on the event (`ObjectiveItem.OnEnable`, w6647).
