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

**Which project type (w1287 reopen, 2026-10-14).** A design-system project's link opens on its landing page
(Published box, "Check whether this design system can migrate", a card grid), not on a file. Ben opened it on his
phone: "it doesn't look like it worked." A `<!-- @dsCard group="…" -->` first line makes the HTML a card on that page,
but the card sits below those panels and is clipped. For a doc to read, use a **regular project**
(`PROJECT_TYPE_PROJECT`). DesignSync can't create one, but it writes into one: create it in a browser window you
opened with a short prompt to the Blank template ("holds an existing HTML file I will add. Create no files; reply:
ready"; Claude names the project, here "Factions plan w1268"), read its id from the URL, `get_project` to confirm the
type, then `finalize_plan` and `write_files`. With one HTML file in it, the link opens straight on that file, and the
phone layout opens on its Preview tab. `list_projects` lists design systems only.

**Check before you report: open the exact link fresh, as the person will**, and also at phone width (Safari page zoom
300% in a 1324 px window is about 441 CSS px). The first report of w1287 checked the doc after opening the file by hand
and missed that the link itself opened on an empty landing page.

**Then, from the headless session:** `create_project` (name), `finalize_plan` (writes; `deletes: []` is required;
`localDir` is a folder of your own in `$TMPDIR`), `write_files` with `localPath` (a 5.3 MB self-contained HTML went in
one call). The project is `https://claude.ai/design/p/<projectId>`.

**Undo what create_project turns on** (if you made a design system). It makes a `PROJECT_TYPE_DESIGN_SYSTEM` (the type can't be changed later)
that starts **Published** and **Org default**, so every new design the person starts would use it. Unless they asked
for a design system: open the project, click "Remove as org default" (and confirm), then untick "Published". Sharing
stays private (the Share button is at the top right of the project view).

**Viewing:** the file opens from the "No file open" picker at the top of the project. The viewer is an iframe. `orca
computer scroll` reports ok but doesn't move it. Click the margin, then `press-key PageDown`. Screenshots taken
within about 2 s of a scroll show tearing (overlapping text), so wait 3 s. The zoom menu (100% next to the pointer
tool) at 75% fits a wide doc into a 1324 px window. Hiding the chat sidebar is the button left of the reload icon. Typing into the prompt box with orca: `paste-text`
lands late or not at all, and `type-text` can enter the text twice; check the box before you send.

**The authorization can lapse mid-session (w1295, 2026-10-14, m5).** `get_project` and `list_projects` worked, then
about 40 minutes later every call, reads included, returned "DesignSync needs design-system authorization". Run the
pty route above again; it took one pass. This time the authorize URL went straight to the code page with no Authorize
click, because the account had approved it before. The clean URL is the OSC 8 hyperlink target in the pty log:
`re.findall(r'8;id=[^;]*;(https://claude\.com/cai/oauth/authorize[^\x07\x1b]*)', log)` gave exactly one copy with
every query param once. Read the `code#state` from the page's tree text and write it to the pty's key file; never
echo it into a report.

**When Safari will not take keyboard focus** (orca `window_not_focused` on `press-key`, even with `--restore-window`,
because another app is in front): `open -a Safari "<url>"` loads the URL into Safari's only window, the one you
opened, with no focus needed; read the result with `get-app-state`. Check first with `list-windows` that Safari has
only your window. The same command opened the exact project link for the final check.

**Creating the regular project:** the Blank template's prompt box changes its element index every second (its
placeholder animates), so `set-value` and index clicks fail as stale. Click the box by window coordinates, `paste-text`,
look at the screenshot (the text in once), then click Send by coordinates.

**Close what you started.** If Safari or the Orca app was not running before you opened it, quit it at the end:
`osascript -e 'tell application "Safari" to quit'` (and `"Orca"`), run in the background so a hung AppleEvent cannot
stall the shell. An `osascript` `make new document` to a Safari that is still launching timed out after 120 s
(AppleEvent -1712); `open -a Safari "<url>"` is the reliable way to start it.

**Note:** in October 2026 Claude Design shows "Claude Design is moving to Artifacts in the Claude app. You can keep
using this version until December 14."

Related: evidence-gate lesson `research-the-route-before-you-say-cant`, section "Drive only the windows you opened" (never use the person's Claude desktop app for this).
