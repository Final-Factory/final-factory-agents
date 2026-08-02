---
name: wsay-voice-notifications
description: Global Claude hooks speak via wsay on notification/stop; how voice alerts are wired
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3ba54556-2326-46e2-9c97-4cb7d0edc7ec
---

User wants Claude to speak aloud when it finishes or needs input. Configured globally in `~/.claude/settings.json` (applies to all Claude instances).

- `wsay` is a macOS-`say`-equivalent TTS at `C:\shared\wsay\wsay.exe` (on PATH). Usage: `wsay "sentence"`.
- **Notification** hook → `~/.claude/hooks/notify.ps1`: reads the hook JSON from stdin, speaks the `message` field (a short summary of what's needed, e.g. "Claude needs your permission to use Bash"); falls back to "Claude needs your input".
- **Stop** hook → `~/.claude/hooks/stop.ps1`: speaks "Claude is done".
- `preferredNotifChannel: terminal_bell` also enabled as a baseline audible cue.

**Why:** User works async and wants an audible spoken cue rather than watching the terminal.
**How to apply:** Don't disable/overwrite these hooks. The Notification message is the best automated summary available — for a richer spoken summary I'd have to write context to a file each turn.
