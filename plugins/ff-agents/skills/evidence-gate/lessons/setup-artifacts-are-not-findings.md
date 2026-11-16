# What the test setup made is not a UI finding, and a standing one is noted, not handed up (w4341, 2026-11-15)

**The rule.** Before a UI finding is graded, counted, fixed, filed or handed up, ask whether a player would see it in
normal play: the window opened fresh where the game opens it, alone unless the person's words are about two, in their
language. If not, it is SETUP (what the tour or the shot made) and is listed, never counted. A STANDING finding (the before
still shows it too and no words ask for it) is noted in the PR's `Critic:` line and the report, not filed and not handed up
by default; only one a player hits in normal play goes to the person's report as "worth a fix?", and their orchestrator
decides. A minor finding is never handed up.

## Why

w4304 fixed the French floating Station Grid (PR #3676 in FinalFactory: French keeps English's width and shows all 8 rows,
measured with the grid alone). Its critic graded one still UGLY: at 1280x800, with a Solar Panel window open beside the
grid, the list scrolled with "+3 de plus" and about 100 px free below. Every language did the same ("+2 more", "+2
weitere", "+3 ещё"), and so did the before build. Rubric item 5 said "content cut off or scrolling while the screen has
room", and `pr_evidence.py` failed a `Critic:` line with a standing count until it named a filed request, so the worker
handed it up as a follow-up. lothsahn dropped it and asked for this audit: "Is this really a difference? Can't the user
move windows around? Are you flagging non-differences as problems?"

What the code says (sourced, the game repo at 424742b2fb): the column fits a window it placed to the place it gets
(`SelectionColumn.cs`, `otherFit.Fit(placedOther.height)` for windows the player did not place), and never moves or
shortens one the player placed (w725, `Header.PlacedByPlayer`). The game remembers where each window was put
(`PanelLayout.cs`, PlayerPrefs `PanelPosition.<role>`). So a grid short beside a Solar Panel window is a player's own
layout choice they can change with a drag or a close, and the tour that ran en, de, fr and ru in one session put each
language's windows where the last one left them.

w4341's audit of 182 UI pull requests' `Critic:` lines found the same pattern again: standing and setup findings counted,
filed or handed up as if the change had made them (the report r<N> of w4341 has the table).

## How to apply

- The checklist line that would have caught w4304's case (`checklists/ui.md`, item 30): **"Before a finding is fixed,
  filed or handed up, name its still's setup: which windows were open, where each was opened (fresh, or where an earlier
  language or step left it) and the screen size. A window short or scrolling beside another window on a small screen,
  when the brief is about one window, is SETUP: shoot that window alone, opened fresh, before you call it a finding."**
- Tours: one language per fresh session (a fresh config folder or `game_data.py` snapshot and restore between legs), or
  close and reopen the window after each language switch; one window per still unless the task is about two
  (unity-ui SKILL.md, the tour notes).
- The critic lists SETUP in its own section and its last line gains `, A setup`
  (`agents/ui-critic.md` step 6b, `design-rubric.md` "Not a finding").
- The PR's line: `Critic: ... (S standing, noted) ...`; `pr_evidence.py` accepts `standing, noted` or a wNNN (a wNNN only
  when a person asked for it filed), and never lets `noted` settle an open NEW finding (tests:
  `test_a_standing_finding_is_noted_not_filed`).
- A small fix on a screen your stills already shoot is still worth making here (w1546); the rule above only stops the
  default of turning every standing finding into a request.
