---
name: no-external-edits-to-open-unity-scenes
description: "Never Write/Edit a .unity or .prefab file that is open in the editor — Unity's modal \"reload scene?\" dialog blocks the main thread and hangs the MCP bridge; there is no setting to auto-answer it"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 670cfc03-14d1-4130-95c2-ee4e66cdd05f
  modified: 2026-07-27T04:10:59.331Z
---

Editing `Assets/Scenes/main.unity` with the Edit tool while that scene was open in the editor
(2026-07-27, the camera-zoom work) made Unity detect the on-disk change during asset refresh and
raise a modal asking whether to reload the scene. The modal sat there until Ben noticed it. Meanwhile
the compile never finished and every MCP call — `read_console`, the `editor/state` resource — timed
out, which looks exactly like a dead bridge.

**Why:** a modal dialog blocks Unity's main thread, and the MCP bridge services requests on that
same thread. So ANY modal stalls the bridge, not just this one — and per CLAUDE.md a stalled bridge
means stop and notify the user, which costs a full round trip of their attention. There is no way to
configure the dialog away: verified 2026-07-27 by three searches, all negative — static properties on
`EditorSettings`/`EditorSceneManager`/`AssetDatabase`/`EditorApplication` matching
`reload|prompt|dialog|refresh|autoSave`; EditorPrefs value names under
`HKCU\Software\Unity Technologies\Unity Editor 5.x` matching `scene|reload|dialog|prompt|extern|changed`;
and a full member scan of every loaded `UnityEditor*` assembly for
`ReloadScene|AutoReload|SceneChangedOnDisk|ModifiedExternally` (only the `EditorSceneManager.ReloadScene`
*method* exists, no flag).

**How to apply:** when a change needs data serialized into an open scene or prefab, make it THROUGH
the editor — `execute_code` doing a `SerializedObject`/`SerializedProperty` edit plus
`EditorSceneManager.MarkSceneDirty` + `SaveScene` — so the in-memory scene and disk never diverge and
no dialog fires. Reserve direct Write/Edit on `.unity`/`.prefab` for files not currently open. Prefer
designs that need no scene data at all (the zoom fix ended up as a plain `const`, which is why it now
touches zero serialized state). Diagnostic: bridge timing out + NO recent mtime activity in
`Library/Bee` or `Library/ScriptAssemblies` = something is blocking the main thread, very likely a
modal waiting on a human — notify rather than wait it out. See [[verify-compile-dll-string-check]] and
[[playmode-needs-main-scene]].
