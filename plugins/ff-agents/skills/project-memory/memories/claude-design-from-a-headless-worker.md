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

**Deleting a project (w1362, 2026-10-15).** DesignSync has no project delete (`delete_files` removes files only). Only
with the person's own words for that one project: on claude.ai/design open the Projects or Design systems list, the
row's "…" menu, "Delete Project", then the dialog names the project ("This cannot be undone"); check the name, click
Delete. `get_project` then answers 404. To learn a row's project id without opening it, use the same menu's "Copy link"
and `pbpaste`. `list_projects` lists design systems only, so confirm kept regular projects with `get_project`.

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

**Revising a doc you already delivered (w1295 reopen, 2026-10-14).** When the request closed on DONE, the harness
swept `$TMPDIR` within minutes; Ben's revision reopened it and every source part, chart script and red-team note was
gone. Recovery worked from the delivered HTML (`DesignSync get_file`, or the copy committed on the branch): split it
by `<section id=` into parts, edit, reassemble. Before DONE, commit or publish the **editable** sources, not only the
rendered HTML (the review-folder zip is the cheap place). In a docs-only scratch clone of the game repo
(`git clone --filter=blob:none --no-checkout --depth 1 -b <branch>` + `sparse-checkout`), do not pass your own
`user.email`: GitHub refused a personal address with GH007 ("would publish a private email address"); use the
author the branch already has (`481770+bryding@users.noreply.github.com`). Overwriting the same project path with
`finalize_plan` + `write_files` replaces the file in place; the project link stays the same.

**Give the link the person can open: check whose account opens it (w1295, 2026-10-17, m5).** A project link
(`https://claude.ai/design/p/<projectId>`) opens only for the claude.ai account that owns it. Ben first said "Drop the
Safari step and only use the project link"; on his own Mac that link answered "Project not found. This project may have
been deleted, or you might not have access to it." Measured on the m5:
- The project's Share menu offers only "Only you" and "Your workspace". It has no link sharing and no invites.
- Signed out, the project link redirects to "Sign in - Claude".
- Any other account gets "Project not found".
- DesignSync can't change sharing and can't publish (`get_project`, `list_files`, `finalize_plan`, `write_files`; no share or publish method).

So:
1. Ask, or read from the brief, which account the person will open it with. The m5's Safari and DesignSync login is
   ryding.ben@gmail.com's workspace.
2. If it is that same account, the project link is fine; update it through DesignSync writes only.
3. For anyone else (another account, a phone that isn't signed in, Lothsahn), the deliverable is the published
   artifact, `https://claude.ai/artifact/<id>`. It opens signed out.
4. To create or refresh it, use your own browser window on the project: Share → "Publish as artifact" → "Publish to
   web". Republishing updates the same `claude.ai/artifact/<id>` link in place. DesignSync writes alone don't update it
   (w1392).
5. Verify the exact link in a brand-new profile before you report:
   `open -na "Google Chrome" --args --user-data-dir="$TMPDIR/vchk-<time>" --no-first-run --new-window "<link>"`, then
   capture that Chrome process's window. You should see the "Sign in" button and the new revision date. Headless Chrome
   (`--headless=new --screenshot`) wrote no file for claude.ai here. A shot in your signed-in window proves nothing.
6. Never give the project link to someone outside the owning account.

**Republishing from a worker, step by step (w1295, 2026-10-17, second update).**
1. `osascript -e 'tell application "Safari" to make new document with properties {URL:"<project link>"}'` (run in the
   background) opens your own window. Safari must already be running.
2. The page draws blank until you reload it with orca and `--restore-window`.
3. The Share popover and its "Publish as artifact" row are not in the accessibility tree. Click them by window
   coordinates (screenshot pixel ÷ `screenshot.scale`), each with `--restore-window`, right after opening it. A click
   without it closed the popover.
4. A "Preview artifact before publishing" dialog follows. Its "Publish to web" button shows once the preview has loaded
   (about 15 s).
5. The toast reads "Published to the web — anyone with the link can view", and the same `claude.ai/artifact/<id>` link
   now shows the new text.

To check the text signed out, open the link in a fresh Chrome profile with `--remote-debugging-port`. Then read
`document.body.innerText` of the **iframe** target (`*.frame.claudeusercontent.com`): the page target holds only the
82-character header with "Sign in". Script: `vchk2.py` in the w1295 review folder.

**A first publish of a new doc, end to end (w1477, 2026-10-20, m5).**
- `orca computer paste-text` into the Blank template's prompt box also attached whatever image sat on the clipboard
  (a `pasted-<n>.png` thumbnail beside the Design system button). Read the tree before Send and click its
  `Remove pasted-…` button, or an unrelated image goes into the person's project.
- After "Publish to web", the toast's **Open** opens the artifact in a new tab of your window.
  `osascript -e 'tell application "Safari" to get URL of every tab of every window'` then prints the
  `https://claude.ai/artifact/<id>` link (the project tree never shows it).
- The m5 has no Python websocket module. Node's built-in `WebSocket` (Node 22+) does the signed-out check over CDP:
  start a fresh profile with `--remote-debugging-port=<p>`, fetch `http://127.0.0.1:<p>/json/list`, run
  `Runtime.evaluate` of `document.body.innerText` on each target, and expect "Sign in" on the page target and the
  doc's text in the `*.frame.claudeusercontent.com` iframe target. Close it with CDP `Browser.close`.

**The authorization lapses between requests too (w1295 reopen, 2026-10-17, m5).** The first DesignSync call of the
resumed request failed with "needs design-system authorization". The pty route above fixed it in one pass, but this time
the authorize page showed an **Authorize** button (disabled for a moment after load, then clickable) before the
`code#state` page. If the page renders blank in a background window, reload it in your own window. The code is single
use; never echo it into a report.

**Updating a doc in place and checking it without clicks (w1608, 2026-10-20, m5).**
- **Diff without reading.** `get_file` on a big doc (130 KB) is saved to a tool-results `.txt` as JSON. Pull out its
  `content` with `python3 -I` (`json.load(f)["content"]`) and `cmp` it with your copy. Do that before the write, so you
  don't overwrite an edit made in the app, and again after the write. Both were byte-identical here.
- **The driver makes the DesignSync calls.** A `general-purpose` subagent doesn't get DesignSync: its ToolSearch
  finds nothing.
- **Seeing the signed-in project without clicking anything:**
  1. `osascript -e 'tell application "Safari" to make new document with properties {URL:"<project link>"}'`, run in
     the background, opens your own window. Its `id of front window` is the CGWindowID.
  2. The window stayed blank in the background, even after a reload.
  3. `set index of window id <id> to 1` plus `activate`, then about 15 s, then `screencapture -x -o -l <id>` captured the
     rendered doc.
  4. `text of front document` shows only the top frame (the project name and the open file's name), because the doc
     sits in a cross-origin iframe. `do JavaScript` is refused unless "Allow JavaScript from Apple Events" is on.
     That is the person's Safari setting: leave it off.
  5. Close the window by its id when done.

**Note:** in October 2026 Claude Design shows "Claude Design is moving to Artifacts in the Claude app. You can keep
using this version until December 14."

Related: evidence-gate lesson `research-the-route-before-you-say-cant`, section "Drive only the windows you opened" (never use the person's Claude desktop app for this).
