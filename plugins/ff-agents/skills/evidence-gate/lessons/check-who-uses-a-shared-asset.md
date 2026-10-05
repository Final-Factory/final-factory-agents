---
name: check-who-uses-a-shared-asset
description: "Before you change a shader, shader graph, subgraph, shader include or material, list what uses it with the game repo's scripts/asset_usage.py. Anything besides the target: give the target its own shader or material, or verify every user in a built player. The PR's '## Used by' section carries the list, and pr_evidence.py and CI fail without it."
date: 2026-10-05
---

# Check who uses a shared shader or material before you change it

**Rule.** Before you edit a `.shader`, `.shadergraph`, `.shadersubgraph`, `.hlsl`/`.cginc` or `.mat`,
run the game repo's tool on it:

```sh
python3 scripts/asset_usage.py Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph
```

It lists every material, VFX graph and asset that draws with it (by GUID, through any graph or
include that pulls it in), the code that loads it by Resources path or shader name, and the prefabs
and scenes those users are on. If anything besides your intended target is on the list, do one of
two things:

1. **Give the target its own** shader, material or variant, and change that. This is almost always
   the right call, and the users list then shrinks to the target.
2. **Treat every user as in scope**: a built-player before/after of each kind of user (the range
   rings, the warning icons, the map marker...), not only the one you meant to change.

**Why.** w410 (#1068, the Alt-view icon backing, merged 2026-10-05) put a dark rounded square
behind the Alt-view item icons by adding a Custom Function to `AsteroWorldSprite.ShaderGraph`, the
sprite shader. `asset_usage.py` on that tree: 25 materials, on 51 prefabs, among them the range ring
of every ranged building, the warning icons, inserter arrows, logistics markers and the player map
marker. Every range circle in Build 77 (0.50.0.77) shipped with a 75% black square inside it. Only
players noticed. w435 (#1076) fixed it by moving the backing into its own shader. #1068 had passed
`pr_evidence.py`: built players, clips, Ben's words, a frame-by-frame look. All of it was of the
icons. Nothing asked what else used the shader. Ben: "Can you update the harness somehow to prevent
making changes to materials in unity without first checking what uses them".

**How to apply.**

- Run the tool before the first edit, not at PR time: the answer decides the design.
- The pull request carries a `## Used by` section: `python3 scripts/asset_usage.py --changed
  origin/develop --markdown` prints it for every shader and material the branch changed. Give each
  user a basis: `TARGET:` (the change is meant for it; shown under Evidence), `MEASURED:` (a
  built-player before/after of that user; name the stills or clip) or `SOURCED:` (why it cannot look
  different, e.g. the graph is restored byte for byte). A guess is not a basis.
- `pr_evidence.py` fails a PR that changes one of those files without the section, with a row
  missing, or with a weak basis. The game repo's "Shared shader and material users" CI job
  (`.github/workflows/asset-usage.yml`) runs the tool on the PR's own diff, posts the list as a
  comment, and fails while the description misses a user the tool found.
- A reviewer asks the same question of any shared asset the tool does not watch (a texture, a
  prefab): `asset_usage.py` takes those paths too.

The checklist line: [visual changes](../checklists/visual.md), item 0; the format: [merges](../checklists/merge.md).
