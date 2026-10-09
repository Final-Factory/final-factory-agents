---
name: lessons-belong-in-the-harness-repo
description: "A lesson goes into the version-controlled harness or the game repo's docs, written by the worker who learned it before it says DONE (its report carries a Learned: line), in the strongest home that fits: a tool check first, then a checklist line, the task's skill, or the doc beside the code. A person's correction or reopen always gets a check; the orchestrator counts corrections by kind and files harness work on the second. A memory folder holds a pointer at most."
date: 2026-10-02
---

# Lessons belong in the harness repo, written before DONE

**Rule.** A rule worth keeping is written into a harness repo or the game repo's docs by pull
request, by the worker who learned it, in the same request, before it says DONE. Its DONE report
carries `Learned: <file or PR> (<one line>)`, or `Learned: nothing new`; FF Factory's ledger refuses
a DONE without the line. A private memory folder is a pointer to it, and a place for one person's
preferences.

**When something was learned.** Any of these, and `nothing new` is the usual answer:

- **A person corrected you or reopened the request.** Always: write the check that would have
  caught it (`Learned: nothing new` is refused on a reopened request; say `no check possible:
  <why>` when there really is none).
- **A check failed on you before it passed**, or you redid the same step three or more times.
- **A cluster**: `git log --since=14.days -- <the files you changed>` shows another fix of the same
  kind.
- **A fact a future agent would have needed** (where something lives, a hidden coupling, a tool
  quirk) that cost you real time to find.

**Where each kind goes** (strongest first: in the 22 worker sessions on the m5 from 10-07 to 10-09,
`pr_evidence.py` ran in 15 and a checklist was read in 13; lesson files were read in 3, all by
sessions writing one):

| What you learned | Home |
|---|---|
| A miss a script could catch | the tool (`pr_evidence.py`, `ui_layout.py`, a game test or census), with the failing case as a fixture |
| How to decide, verify or report | a checklist line here; a lesson only for the dated why |
| How to do a task better | that task's skill (`unity-ui`, `drive-game`, `playtest`, `editor-ops`, `ci-release`) |
| A fact about the game or the code | the game repo, beside the code: `Documentation/<system>.md` or `docs/`, with `file:line`; `docs/HowToPlay.md` for how it plays; `CLAUDE.md` only when every agent needs it |
| A trap in Unity, ECS, a tool or a machine | `project-memory`: a memory plus one index line |
| Marketing | the ff-marketing repo, `lessons/` |
| Rules the prompts state themselves | ff-factory, `server/agents.ts`, `server/work.ts` |
| One person's preferences | their orchestrator's memory folder; never in a public repo |

**A second correction of the same kind is a harness bug.** The Deck UI took five rounds of Ben's
corrections before a check changed: the w560 hub, w644's audit passing a hub broken on his Deck
(#1251), w712's navy Blueprints window (#1272), w732's minimap buttons drifting after #1264, w723's
overlapping classic panels. The checks came only when he asked for them (w718, w733, 2026-10-08),
and the prose rule they needed had been in project-memory since 2026-09-22
(`ui-screenshot-worst-case-before-done`). Each correction landed on a different worker, so no
worker saw the second one: his orchestrator did. So the person's orchestrator keeps one memory line
per correction (the date, the request, the kind, the person's words verbatim) and, on the second of
a kind, files the harness work itself in that turn (FF Factory `personalBrief`). A worker that gets
the second correction itself adds the check in the same request as the fix.

**The person's latest words win.** When a lesson or a check disagrees with what a person just told
you, follow the person, say so in the report, and fix the lesson or the check in the same request,
quoting their words, never a paraphrase (w732: `hud-clusters.json` `byDesign`, a one-pair exemption; w742 made it the general `openedPanels` rule).

**Why.** Ben, 2026-10-02: "Your memory should be stored in this repos harness so it is enshrined
forever for anyone who forks it." Ben, 2026-10-09 (w741): "If you learn something after struggling
or figure out new ways to do things better, update the harness especially after putting in a bunch
for related bugs or you learn something new about the game or code that would help you in the
future." The design behind this, with its sources: `design-w741.md` beside this skill.

**How to apply.**

- Search first (`grep -ril <word>` over this skill, `project-memory`, the game repo's `docs/`);
  extend an entry rather than add one. Lessons here are capped at 26 (CI fails above it): a new one
  merges or retires another.
- Harness changes go through `/ff-agents:publish-skills` as a pull request, merged when CI is green;
  game-repo docs ride the request's own PR.
- A lesson names its incident (date, request, PR) and links the check. "Be careful" is not a lesson.
- An orchestrator cannot write to a repo. It keeps the one-line pointer and the correction tally in
  its memory, files a request, and tells its person.
- Keep names of players, secrets and private details out: these repos are public.
- Don't write lessons to `~/.claude/projects/*/memory/`. They stay on that machine.
