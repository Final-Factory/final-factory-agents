---
name: drive-a-persons-signed-in-chrome-on-a-mac
description: How a worker on a Mac (the m5) reads and clicks a website in the person's own signed-in Chrome without bringing Chrome to the front - AppleScript for tabs, the accessibility API (pyobjc AXPress) for the page, screencapture -l for proof - and why AppleScript JavaScript and a CDP profile copy were not needed.
metadata:
  type: reference
---

**Driving the person's signed-in Chrome without stealing focus (w1833, 2026-10-23, m5).** Ben: "i'm logged into
godaddy in chrome, you can use my chrome". He was typing in Firefox at the time, and Chrome never came to the front.

- **AppleScript tabs work with no prompt:** `make new tab at end of tabs of window 1 with properties {URL:...}`,
  `set URL of (tab id N of window 1)`, `title`/`URL`/`loading`, `close (tab id N of window 1)`. Note `active tab index`
  first and set it back. None of these activates Chrome.
- **AppleScript `execute ... javascript` is refused** while View > Developer > Allow JavaScript from Apple Events is off
  (Ben's is). Leave it off: turning it on would let any local process run JS in all of his tabs.
- **The page itself goes through the accessibility API.** The worker process is already trusted
  (`AXIsProcessTrusted()` True). Set `AXManualAccessibility` = True on Chrome's app element, walk `AXWindows` to the
  `AXWebArea`, and `AXUIElementPerformAction(el, "AXPress")` buttons, menu items and checkboxes. Popups show up as
  `AXMenu`/`AXMenuItem` in the same tree. Only the window's **active** tab has a tree, so make your tab active
  (`set active tab index`; this does not raise the window), then hand the old index back at the end. Indexes shift
  after every page change, so read the tree again before each press.
- **Proof:** `screencapture -x -o -l <CGWindowID>` (from Quartz `CGWindowListCopyWindowInfo`, Chrome's pid,
  layer 0) captures Chrome's window even while other windows cover it.
- Setup: `python3 -m venv "$TMPDIR/venv"; pip install pyobjc-framework-ApplicationServices pyobjc-framework-Quartz`.
  macOS has no `timeout`, so cap each osascript call with a background-and-kill loop.
- A CDP copy of the profile (`--remote-debugging-port`) was never needed. It would copy cookies, so avoid it.
- Untested: typing into a form field. Try setting `AXValue`, then read the field back and capture it before you press
  Save. Keystrokes or cliclick need Chrome in front, so ask first if the person is at the Mac.

The full helper (`ax.py dump/press/shot`) and the GoDaddy specifics are in `/srv/fff/review/w1833/chrome-route.md` on
fff-portal. GoDaddy facts from the same run: Renewals & Billing > Manage Subscriptions has a status filter with
"Auto-Renew On/Off". The per-domain auto-renew switch is hidden once auto-renew is on. The domain list's expiration
date opens a checkout with a protection add-on ticked by default, so cancel it.

**GoDaddy can ask for its "Continue & Verify" identity check on every DNS save (w1922, from the w1844 DNS edits).** It
asked three times for one domain (nevergames.com) and never for the other (final-factory.com). Only the person can pass
it. So batch the records into one save per domain where the UI allows it, and warn the person before you start that
they may need to pass the check, so the session is not left waiting on them. If it appears mid-run, declare the wait
(`waiting_on_person`) instead of retrying the save.
