---
name: a-child-popup-over-its-own-window-is-by-design
description: "A popup a window opens for a choice (an entity or item picker, a filter, a colour picker, a confirmation dialog) and that returns to that window covers its own window by design: never a flaw, never STANDING, never handed up, with no 'standing, noted' line. The same popup over an unrelated window or a HUD block is still graded by the layer rules. ui_layout.py check counts it as a `child popup` apart from new, kept and standing (w4504, the second correction of this kind after w4341)."
date: 2026-11-16
---

# A child popup over its own window is by design

**Rule.** Before you call an overlap a flaw, ask who opened the thing on top. If a window opened it for the player to
make a choice, and the player then goes back to that window (an entity or item picker, a request filter, a colour
picker, a confirmation dialog), it covers its own window by design. It is not a flaw, not STANDING and not a note, and
it is never handed up. Leave it out of Flaws and out of every count. The same popup over **another** window, or over a
HUD block, is graded by the usual layer rules (checklists/ui.md, item 34). So are two pieces that one hover shows over
each other (a hover card and its tooltip).

**Why.** In w4381 a fresh ui-critic flagged the Circuit Module's entity picker for covering the Circuit Module window
it was opened from, and the finding got handed up. lothsahn, 2026-11-16, w4504: "These are popup dialogs from the prior
window where the user has to make a selection and then returns to the prior window. Never worry about overlap in cases
like this. Please make sure you don't highlight overlap for popup windows that overlay their parent window." That was
the second correction of this kind. The first was w4304/w4341 (r257: "Can't the user move windows around? Are you
flagging non-differences as problems?"), which taught the critic to drop test setup but did not cover popups over their
parent. The tools gave no help either: `ui_layout.py check` counted the picker as a new window overlap, and
`pr_evidence.py` failed it.

**How to apply.**
- The critic (agents/ui-critic.md, item 6) writes the pair as "<popup> (child popup of <window>) over <window>" and
  leaves it out of Flaws. The rubric's "Not a finding" section says the same.
- `ui_layout.py check` and `overlaps` print the pair as `CHILD POPUP` and count it on the `Window overlaps:` line as
  "N child popup(s) over the window that opened them, by design (w4504)", apart from new, kept and standing.
  `covered_text` skips the opener's text that sits under its popup. Popups are found by path (`DEFAULT_POPUPS`: the
  `Modal/*` children, `*Picker`, `*Dialog`, `LogisticsRequestFilterPanel`, and more) plus hud-clusters.json
  `childPopups.paths`. The game opens them under `Modal`, so the opener is the open window the popup covers most,
  unless hud-clusters.json names it (`childPopups.parents`: `{"popup": "<pattern>", "parents": ["<pattern>"]}`). Every
  pair is printed, so a wrong guess can be seen. Tests: `ChildPopupTest` in unity-ui/tests/test_ui_layout.py.
- `pr_evidence.py` never counts a child popup. When a `Window overlaps:` line has no child-popup count, it came from a
  tool older than 1.34.330, so a new or kept overlap there also points to the re-run (`WindowOverlapTest` in
  evidence-gate/tests).
- `make_tour.py` in the game repo has no overlap census of its own, so nothing changed there.
