---
name: claude-design-from-a-headless-worker
description: How a headless FF Factory worker puts files (an HTML doc) into a person's Claude Design (claude.ai/design) with Claude Code's DesignSync tool, including the one-time /design-login done through an interactive claude in a pty, and what to undo after create_project.
metadata:
  type: reference
---

**Route (w1287, 2026-10-14, measured on the m5).** Claude Code's `DesignSync` tool (deferred; `ToolSearch select:DesignSync`)
lists, creates and writes claude.ai/design projects through the person's claude.ai account. In a headless worker
session its first call fails: "DesignSync needs design-system authorization, and /design-login cannot run in this
non-interactive session." The authorization is per machine, and headless sessions there reuse it once it exists.

**One-time authorization from a worker:**

1. Start an interactive `claude` in a pty with `/usr/bin/expect` (there is no tmux on the m5): `spawn env -u CLAUDECODE -u
   CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_CHILD_SESSION -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_MESSAGING_SOCKET -u
   CLAUDE_CODE_MESSAGING_TOKEN BROWSER=none claude`, in a scratch folder under `$TMPDIR`, `log_file` to a file. Feed it
   keys from a file the expect loop polls. It picked up the machine's own Claude Max login.
2. Answer the folder-trust prompt (Down, Enter), then send `/design-login` and Enter.
3. It prints `https://claude.com/cai/oauth/authorize?...scope=user:design:read+user:design:write...&state=...`. Take
   it from the log with a parser that checks every query param appears once: terminal wrapping repeats fragments, and
   a garbled copy carried a duplicated `state`.
4. Open it in a browser **window you opened** that is signed in to claude.ai (on the m5: Safari yes, Chrome no). The
   page says "Claude Design would like to connect to your Claude chat account ... Logged in as <email>". Click
   Authorize. The person must have asked for this; a login, password or 2FA page means stop.
5. The callback page (platform.claude.com/oauth/code/callback) shows a `code#state` string. Send it to the pty with
   Enter. The pty prints "Design-system access authorized." Then `/exit`.

**Then, from the headless session:** `create_project` (name), `finalize_plan` (writes; `deletes: []` is required;
`localDir` is a folder of your own in `$TMPDIR`), `write_files` with `localPath` (a 5.3 MB self-contained HTML went in
one call). The project is `https://claude.ai/design/p/<projectId>`.

**Undo what create_project turns on.** It makes a `PROJECT_TYPE_DESIGN_SYSTEM` (the type can't be changed later)
that starts **Published** and **Org default**, so every new design the person starts would use it. Unless they asked
for a design system: open the project, click "Remove as org default" (and confirm), then untick "Published". Sharing
stays private (the Share button is at the top right of the project view).

**Viewing:** the file opens from the "No file open" picker at the top of the project. The viewer is an iframe. `orca
computer scroll` reports ok but doesn't move it. Click the margin, then `press-key PageDown`. Screenshots taken
within about 2 s of a scroll show tearing (overlapping text), so wait 3 s. The zoom menu (100% next to the pointer
tool) at 75% fits a wide doc into a 1324 px window. Hiding the chat sidebar is the button left of the reload icon.

**Note:** in October 2026 Claude Design shows "Claude Design is moving to Artifacts in the Claude app. You can keep
using this version until December 14."

Related: evidence-gate lesson `research-the-route-before-you-say-cant`, section "Drive only the windows you opened" (never use the person's Claude desktop app for this).
