---
name: a-release-is-done-when-its-notes-are-posted
description: "A requested release is done only when release-status.py says LANDED on its branch (develop: development, master: pre-release) AND its patch notes are posted once, as Max, in #dev-patch-notes, with post_as_max (any machine; FFBox posts). A failed post is reported as an open step with FFBox's reason instead of finishing."
date: 2026-10-03
---

# A release is done when its notes are posted

**Rule.** Every requested release (a version bump on develop or master) ends with two checks, and is
not reported done until both hold:

1. it is live on its Steam branch: `python scripts/release-status.py <version>` says LANDED, on
   `development` for develop or `pre-release` for master;
2. its patch notes (`cicd/release-notes/<version>.md`, player-facing, no internal ids) are posted
   once, as Max, in #dev-patch-notes, and the report carries the message link.

**Why.** Lothsahn, 2026-10-03: "any time a release is requested, you should always post the
#dev-patch-notes after the build is complete and uploaded." On 2026-10-02 the notes for 0.50.0.65
and .66 were never posted: the worker waited for a Steam branch ffbox does not set and finished
without them, and nothing in its report said the post was missing.

**How to apply.**

- Treat the post as the release's last step, in the `ci-release` checklist (section 3), not as a
  courtesy after the report.
- Post with `mcp__machine__post_as_max` from any machine (w901, 2026-10-10: Lothsahn, "at some point,
  a worker on LothDesktop didn't have access to publish the notes. Please make sure that workers can
  request FFBox send a discord message"). FFBox holds the bot; `ci-release` `patch-notes.md` section 4
  has the call (`channel: dev_patch_notes`, `file`, `skip_lines: 2`, `key: <version>`). If it fails,
  report "live on <branch> (BuildID …), patch notes NOT posted: <FFBox's reason>" with the notes
  file's path, and leave the step open. There is no "no config on this machine" excuse any more.
- An orchestrator that dispatches a release puts "post the patch notes once live" in the brief, and
  does not close the release until the link is in.
