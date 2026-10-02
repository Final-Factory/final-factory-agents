---
name: mcp-execute-code-is-retried-keep-editor-mutations-idempotent
description: A Unity MCP execute_code call that times out is sent again, so an editor mutation written as an increment lands several times; write absolute values or guard the edit
metadata:
  type: reference
---

# `execute_code` is retried after a timeout: keep editor mutations idempotent

2026-10-02, w210 (lobby browser column), BEAST sandbox. A prefab edit through `execute_code`
(`PrefabUtility.LoadPrefabContents` → `rt.sizeDelta += 120` on four RectTransforms →
`SaveAsPrefabAsset`) returned `Timeout receiving Unity response`. The save had worked, and the
bridge had sent the same code again several times while the editor was busy: the four widths in
`MainMenuPanel.prefab` came out 720 px wider, not 120.

- A timed-out call may have run zero, one or many times. Check the result on disk (`git diff`)
  before doing anything else, never re-send the same code.
- Write editor mutations so a second run changes nothing: set the absolute value, or return early
  when the edit is already there (`if (root.transform.Find("Visibility") != null) return ...`).
  The row prefab edit in the same session had that guard and came through clean.
- A long `LoadPrefabContents` + save of a big prefab is the kind of call that times out. For a
  handful of overridden numbers, editing the YAML override lines is safer (`propertyPath:
  m_SizeDelta.x` + `value:`), and the diff stays four lines.
- The editor log shows `MCP-FOR-UNITY: Command TCS timed out (N consecutive)` while this happens.
  On a sandbox whose FMOD plists are CRLF the cause is usually the "Repair FMOD Libraries" dialog
  after a domain reload ([[beast-sandbox-editor-driven-from-m5]]); the harness dismisses it within
  about a minute, so wait rather than retry.
