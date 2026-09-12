---
name: m3-scratch-sweep-refused-delete-named-roots
description: "A blanket `rm -rf /private/tmp/ff-*` over ssh on the M3 is refused by the permission classifier (a wildcard delete of many roots); deleting the CLOSED roots by explicit name (sixteen `ff-*-011*` roots, 768 MB → 8.8 GB free) is accepted — list, pick by feature/sha, delete named, never the live-lane or DeterminismAudit roots."
---

# M3 scratch cleanup: delete named roots, never a wildcard sweep (2026-09-12, 069 relay #8)

- The M3 had 768 MB free (100 % used). `rm -rf /private/tmp/ff-*` inside an `ssh benryding@10.0.0.110` command was
  refused by the permission classifier — a wildcard delete over an unknown set of roots reads as destructive.
- What was accepted: `ls -d /private/tmp/ff-*` first, then one `rm -rf` naming each CLOSED root explicitly
  (sixteen `ff-*-011*` roots of the closed feature 011) → 8.8 GB free. The live-lane roots
  (`ff-steamdesync-<sha>`, `ff-tut-host-<sha>`) and `DeterminismAudit/` (16 GB of reports) were left alone.
- Rule: enumerate, choose by feature number / build sha against the plan's "live now" list, delete by name,
  print what you deleted. Same for the M5 and BEAST roots.
- Related: [[three-peer-lane-recipe-and-traps]], [[built-client-relaunch-and-evidence-traps]].
