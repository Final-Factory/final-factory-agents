# Which skill to use in an ffu checkout

Every ff-agents skill, and what an agent uses in its place when the work is in Final Factory Universe (FFU,
Final-Factory/ffu) rather than the Unity game (ffu PLAN.md row M0.8, w2895). `check_ffu_skills.py` reads this table and
fails when a skill is missing from it, when it names an ffu-* skill that does not exist, or when a skill replaced here
does not name its replacement in its own `description` (so an agent picking skills by description finds the right one).

- **an `ffu-*` skill**: use that one; the FF1 skill's commands (the Unity editor, the MCP bridge, player slots, ffauto,
  game-repo scripts) do not exist in ffu.
- **shared**: the skill works unchanged in either repo.
- **FF1 only**: FFU has nothing it applies to yet; the reason names what would change that.

| Skill | In an ffu checkout | Why |
|---|---|---|
| add-network-operation | ffu-add-op | A mutation is an `Op` through `Sector::submit`, not a Unity network op pair |
| ci-release | FF1 only | FFU ships nothing to players and has no Steam depot; its CI release job is `ffu-build-test`'s |
| concept-art | shared | Engine-independent: paints concepts with Stability AI |
| deep-think | shared | Engine-independent |
| determinism-audit | ffu-determinism | No paired editors: hashcheck, crosscheck, replay and bisect; live sessions are ffu-multiplayer's |
| drive-game | ffu-drive | Headless runs, the agent state API, `ffu-mcp`, the window, stills and clips |
| editor-ops | ffu-build-test | No editor to pin or compile: cargo, the CI checks and gh |
| evidence-gate | shared | Engine-independent rules and checklists |
| github-pr-review | FF1 only | Reviews Final-Factory/FinalFactory PRs in Ben's voice; not asked for ffu |
| handoff | shared | Engine-independent |
| honest-coop-play | FF1 only | FFU has no game to beat yet; its multiplayer sessions are ffu-multiplayer's |
| learnToPlay | FF1 only | The HowToPlay guides describe FF1 |
| massdriver-visual-e2e | FF1 only | FFU has no mass drivers yet |
| mp-beta-deploy | FF1 only | FFU has no Steam builds |
| plain-writing | shared | Engine-independent |
| playtest | ffu-playtest | A goal, ops through the agent API, watches, stills and a recording as the bug report |
| project-memory | FF1 only | Unity, Burst and FF1 lessons; FFU's binding rules are ffu's own `CLAUDE.md` |
| publish-skills | shared | Engine-independent |
| resumeFromHandoff | shared | Engine-independent |
| steam-upload | FF1 only | FFU has no Steam builds |
| unity-ui | ffu-ui | `ffu-ui`'s tree as data, `ui_tree`, headless captures and its bounds tests |
| update-docs | shared | Engine-independent |
| watch-video | shared | Its viewer judges any clip; FFU records with `ffu --clip`, not its Unity recorder |
