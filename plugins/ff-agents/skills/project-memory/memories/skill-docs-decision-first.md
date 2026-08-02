---
name: skill-docs-decision-first
description: "Ben wants skill docs restructured decision-first when one misleads me, not just patched — lead with the check that prevents the wrong action."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b9526c85-2723-48d8-91e3-4a1b662e4645
  modified: 2026-08-01T22:32:05.418Z
---

When a skill doc is in my context and I still take the wrong action, Ben's fix is to
**restructure the doc, not just correct the one line** (2026-08-01, after I declared the Unity
editor "stuck" when `drive-game/SKILL.md` already documented the occlusion freeze).

He asked for it "clearer and shorter." What that meant concretely:

- **Lead with the decisive check**, before any prose. The `Time.frameCount` probe distinguishes
  "occluded and frozen" from "wedged" in ten seconds; it was at line 70 of a 437-line file and I
  skipped it.
- **Merge look-alike traps into one comparison table.** The doc had two different "editor looks
  stuck" sections 120 lines apart with opposite fixes (`Step()` vs `stop play mode`), and I grabbed
  the nearer-looking one.
- **Split operational rules from recipes.** Long dated playthrough logs bury the rules you need at
  decision time. Moved them to a sibling `recipes.md`; SKILL.md went 437 → 175 lines.

**Why:** a rule I have to go looking for mid-file is a rule I will half-apply under load. Length
itself isn't the problem — burying the load-bearing check is.

**How to apply:** after any mistake that a doc should have prevented, ask whether the doc's
*structure* caused it, and fix that. Put the falsifying test first, make look-alike failure modes
adjacent and contrastive, and push reference material to a companion file. Related:
[[repo-path-trace-claims]].
