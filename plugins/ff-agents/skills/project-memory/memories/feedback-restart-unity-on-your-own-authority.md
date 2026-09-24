---
name: feedback-restart-unity-on-your-own-authority
description: Ben 2026-09-24, emphatic — agents have full authority to restart their own Unity editor whenever it's hung/crashed/frozen/misbehaving, no need to ask first; ffsb sandboxes use the sandbox unity tool, Ben's own machines are also fine to restart; ~5 minutes unresponsive outside a known long operation = restart; startup-dialog quick reference
metadata:
  type: feedback
---

**Rule (Ben, 2026-09-24, emphatic):** Unity crashes and freezes constantly. Agents have full
authority to manage their own Unity editor and must restart it — without asking Ben first —
whenever it is hung, crashed, frozen, or stuck in a bad state: a domain-reload loop, an
unresponsive MCP bridge, a wedged play mode, a stuck compile, or any other misbehavior.

**Why:** Unity's instability is routine, not exceptional, and every pause to ask permission for
a recovery Ben has already delegated just burns a session waiting on a frozen editor. This is
the explicit, standing statement of that delegation — it supersedes any softer or more
hesitant wording elsewhere (this repo's own history included wording that told agents to
"run recovery before involving the user," i.e. quietly work around a stuck bridge instead of
restarting it — see [[feedback-mcp-bridge-down-recover]], which already points the other way:
report the gap, then restart the exact editor yourself).

**How to apply:**
- **In an ffsb sandbox:** restart through the sandbox's own tool, `mcp__sandbox__unity`
  (action `restart`, add `force` if a plain restart doesn't take) — never kill Unity/node/
  PowerShell processes by hand; the sandbox host is shared with other sandboxes and the live
  co-op game and blocks hand-kills for exactly that reason. See
  [[feedback-beast-work-goes-through-a-sandbox]].
- **On Ben's own machines:** restarting his live editor is also fine — he accepts losing
  unsaved in-editor scene state to get unstuck. Never touch git working-tree files as part of
  it (no incidental `checkout`/`reset`/`clean`).
- **After every restart:** re-pin the Unity MCP instance (`mcpforunity://instances` →
  `set_active_instance`), handle whichever startup dialog is actually on screen — several are
  native modals no automation channel can see except a screenshot, see `editor-ops` for the
  full recovery detail per dialog:
  - FMOD "Repair FMOD Libraries" (CRLF line-ending modal) → **Ignore**. On an ffsb sandbox an
    automated click on this one does NOT work (UIPI blocks it under the elevated scheduled
    task) — fix the CRLF files at the source instead; see
    [[beast-sandbox-editor-driven-from-m5]].
  - Native **Safe Mode** (a compile error was already on disk at boot) → fix the error on disk
    first, then Ignore/exit Safe Mode; a relaunch with a known compile error still on disk just
    re-triggers it.
  - Scene-backup recovery dialog ("recover backed-up scene?") with a clean git working tree →
    **No** / discard the backup.
  - "Open scene(s) have been modified externally — Reload/Ignore" (after a branch switch or
    pull changed an open scene) → **Reload**, unless the editor holds deliberate unsaved scene
    work.
  Then wait for the domain reload to finish and `read_console` to be clean of `error CS` before
  continuing — the full compile-verification ritual is in `editor-ops`.
- **Don't burn time waiting on a frozen editor.** If the MCP bridge or the editor hasn't
  responded for roughly 5 minutes, and that stall isn't inside a KNOWN long operation (asset
  import, a big compile, a long test run), restart rather than continuing to poll.

Related: [[feedback-beast-work-goes-through-a-sandbox]], [[beast-sandbox-editor-driven-from-m5]],
[[feedback-mcp-bridge-down-recover]].
