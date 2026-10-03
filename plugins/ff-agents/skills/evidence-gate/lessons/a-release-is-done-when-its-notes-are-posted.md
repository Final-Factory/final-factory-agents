---
name: a-release-is-done-when-its-notes-are-posted
description: "A requested release is done only when release-status.py says LANDED on its branch (develop: development, master: pre-release) AND its patch notes are posted once, as Max, in #dev-patch-notes. A machine without the ffdiscord config reports the post as an open step instead of finishing."
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
- Posting needs the ffdiscord config (LothDesktop today). Check before the bump with
  `ffdiscord read 1072387196927094845 --limit 1`. Without it, report "live on <branch> (BuildID …),
  patch notes NOT posted: no ffdiscord config on <machine>" with the notes file's path, and leave
  the step open for a machine that has it.
- An orchestrator that dispatches a release puts "post the patch notes once live" in the brief, and
  does not close the release until the link is in.
