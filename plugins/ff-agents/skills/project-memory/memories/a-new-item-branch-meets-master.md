# A new-item branch meets master: op ids, material flags, concept stills

w2962 (the Ancient Portal Mover, PR #3113, 2026-11-03) cost two extra CI rounds on things a minute's check catches.

- **Op ids collide when master adds ops while you work.** `NetworkGameOperationType` is an explicit-numbered enum; on
  w2962 master's fleet attack-move cheat (w2978) took 91/92, which the branch had used. Renumber yours past master's
  last id when you merge. C# accepts two members with one value, so a clean auto-merge can still duplicate an id:
  after every merge of master, list duplicate values
  (`grep -oE "= [0-9]+(,|$)" Assets/Scripts/FFCore/Network/NetworkGameOperationType.cs | sort | uniq -d`).
- **A new material copied from a shipped one carries `m_ObjectHideFlags: 32`.** Many content materials have it, but on a
  changed file CI's "Shared shader and material users" check reads it as a play-mode save and fails. Set new materials
  to 0 and run the check locally before pushing:
  `python scripts/asset_usage.py --changed origin/master --check-body <pr-body.md>`.
- **Quitting the editor dirties shipped assets** (DysonBot and SingularityLance `.mat`s, `BionicStructures4.mat`, the
  LiberationSans fallback font asset). `git checkout --` them before a commit or build.
- **Concept still names for `Hero art: concepts`** may live only in a review folder. When a design rendered them with
  a rig, the rig's `Shot("<name>")` calls name them: w2194's `DragonConceptRig.MoverShots` (branch
  `w2194-ancient-dragon-design`) writes `07-mover-0.png`..`07-mover-3.png`. Read it with `git show <branch>:<path>`
  instead of asking. Say so when the design drew one direction, not 2-3.
