---
name: dontsave-bootstrap-hosts-outlive-editor-play
description: A bootstrap host made as new GameObject { hideFlags = DontSave } plus DontDestroyOnLoad outlives its editor play session; the next session reuses it through its static _instance with its runtime material already destroyed, so it draws nothing. Use plain DontDestroyOnLoad.
---

# DontSave bootstrap hosts outlive the editor play session

The pattern `new GameObject(name) { hideFlags = HideFlags.DontSave }; DontDestroyOnLoad(host);` behind
`if (_instance != null) return;` breaks in the editor, which enters play mode without a domain reload:

- A DontSave object is not destroyed when play mode ends. It stays enabled outside any scene
  (`gameObject.scene.name == ""`), its static `_instance` is still set, and the next session's bootstrap
  returns early and reuses it.
- A runtime `new Material(...)` it made without hide flags is destroyed at the session end. The reused
  object then renders nothing: every `PlayerNameTagController` tag had `fontSharedMaterial == null`
  (087, 2026-09-28).
- After a domain reload the static is reset, so the bootstrap makes a second host while the old one
  keeps running scene-less, and anything it draws is doubled.

Fix: drop `DontSave` from the host and keep `DontDestroyOnLoad`. The host then ends with the session
like any play-mode object. Verified: two sessions in a row gave one controller each, with its material.
Giving the material `DontSave` as well is the wrong fix, because the leaked host starts drawing a
duplicate.

Done for `PlayerNameTagController` and `SlowPeerBurn`. Still `DontSave`, not verified:
`PingOverlay` (it destroys leftovers, but after the same early return), `AgentChannelHost`,
`PresentationStutterProbe`, `RubberbandProbe`.

Diagnose with `Resources.FindObjectsOfTypeAll<T>()`, since `FindAnyObjectByType` misses the leaked
copy. Report each one's scene, enabled flag and material.

Related: [[editor-host-mp-ui-worst-case-screenshots]], [[ecs-runtime-material-unload-gotcha]].
