---
name: learnToPlay
description: Harvest gameplay knowledge learned this session into the two HowToPlay guides — the PUBLIC player-framed kit/HowToPlay.md in Final-Factory/finalfactory-agent-kit (what players' agents read) and the internal code-traced docs/HowToPlay.md in the game repo. Reviews the current conversation for game mechanics you were confused about and then figured out (by reading code, testing, or the user explaining), routes each one to the guide whose reader needs it, and folds it in so the next session (and every player's agent) doesn't re-learn it. Invoke when the user says "/learnToPlay", asks to update the how-to-play doc, or after you've worked out a gameplay aspect that was non-obvious.
---

# learnToPlay: capture gameplay knowledge into HowToPlay.md

## Two guides — route every learning by audience (068, 2026-09-24)

| Guide | Reader | Goes there |
|---|---|---|
| `kit/HowToPlay.md` in the **public** repo `Final-Factory/finalfactory-agent-kit` | a player's agent, playing through the `finalfactory` MCP tools | how the game plays: mechanics, numbers, gotchas, strategy — in **tiles** and **MCP tool names** (`move_to`, `build`, `look_around`, …) |
| `docs/HowToPlay.md` in the game repo | engineers and dev agents | code-traced internals (systems, components, `file:line`), §6 automation/determinism validation, `ffauto:` harness detail, §7 open questions |

Most gameplay learnings belong in BOTH, phrased for each reader: the player-framed fact in the kit
guide, the code trace behind it in the internal one. Pure engine or harness facts go only in the
internal guide.

**Rules for the public guide** (it is public and ships inside the game):
- No code internals: no file paths, `file:line`, system or component names, `ffauto:` harness
  flags, spec/task numbers, machine names, or people's names and dates. State the fact the way a
  player would check it in the game; mark an unsure fact as unsure.
- Work in a fresh clone outside the game repo (`gh repo clone Final-Factory/finalfactory-agent-kit
  <tmp>`), and set the clone's identity to the noreply one BEFORE committing:
  `git config user.name "Final Factory"` and
  `git config user.email "481770+bryding@users.noreply.github.com"`. Never commit there with the
  machine's global identity. Before pushing, `git log --format='%an <%ae>' origin/main..HEAD` must
  show only that noreply address.
- Push to `main` (its normal flow; CI runs gofmt/vet/tests/skill lint). If a push guard cannot tell
  the repo apart from the game repo, push with the explicit URL:
  `git push https://github.com/Final-Factory/finalfactory-agent-kit.git HEAD:main`.
- It reaches players only with the next kit release (bump `kit/VERSION`, tag `v<ver>`, then the
  game repo's `scripts/fetch-agent-kit.sh <ver>`). Do not tag a release as a side effect; say in
  your report that the change is on `main`, unreleased.

`docs/HowToPlay.md` is the living reference for how Final Factory actually plays — it exists so an
engineer (or Claude) can set up and *validate* gameplay scenarios without re-deriving the mechanics.
It is only valuable if it stays current. Your job here: mine THIS session for gameplay things you
got wrong, were confused by, or had to work out (from code, from testing, or from the user
explaining), and write the corrected understanding into the doc.

This is also a STANDING PRACTICE, not just an on-demand command: whenever during a session you
struggle with a gameplay aspect and then figure it out (or the user corrects/teaches you), update
`docs/HowToPlay.md` then and there. Don't wait to be asked. This skill is the explicit sweep for
anything missed.

## What counts as "learned" (include these)

- A mechanic you initially misunderstood and then corrected (e.g. "I assumed X auto-happens; it
  actually requires Y").
- Something the USER told you about how the game works (their word is authoritative — mark it
  `user-confirmed <date>`).
- A code-verified mechanic you traced (name the systems/components/files so it's checkable).
- A gotcha that cost you time (a non-obvious precondition, a special case, a counterintuitive
  routing/ordering rule).
- A correction to an existing doc claim that turned out wrong — fix it in place AND note it changed.

## What NOT to add

- Pure code-structure facts already obvious from the repo (belongs in code/architecture docs, not a
  play guide).
- Session-only minutiae (specific entity ids, one-off scratch values) — keep it about how the game
  *plays*, not this run's transient state.
- Speculation. If you're not sure, mark it `[NEEDS CONFIRMATION]` and, if it matters, ask the user.

## Procedure

1. **Scan the session.** Re-read the conversation for: questions you asked about gameplay, moments
   you were wrong then corrected, things the user explained, mechanics you traced in code to set up
   a scenario, and any "huh, that's not how I thought it worked" beats.

2. **Diff against the docs.** Route each item (see "Two guides" above), then read the guide(s) it
   belongs in. For each learned item: is it already there and
   correct? If missing → add it. If present but wrong/stale → fix it in place (don't leave the wrong
   claim; you may strike it through with the correction, like the existing §7 entries).

3. **Write it into the right section.** The public guide has its own numbered sections — match
   them. The internal doc's structure (extend, don't fight it): §1 Fleet vs
   Factory, §2 core loop, §3 mining detail, §4 other systems, §5 controls/UI, §6
   automation/determinism validation, §7 open questions. Put each fact where a reader would look for
   it. Move resolved §7 open questions into the body and mark them answered (with date + how known).
   Keep the doc's voice: concrete, code-referenced where possible, `user-confirmed <date>` where the
   user is the source, `[NEEDS CONFIRMATION]` where still unsure.

4. **Keep it honest and dated.** Use today's date (check the environment's current date). Attribute
   user-sourced facts to the user. Don't overstate confidence.

5. **Surface remaining unknowns.** If the session exposed gameplay questions you still can't answer
   from code or testing, add them to §7 and — if they block current work — ask the user now.

6. **Commit** the `docs/HowToPlay.md` change in the game repo with a clear message (e.g.
   `docs: HowToPlay — <what you learned>`), and the `kit/HowToPlay.md` change in the kit clone under
   the noreply identity. Doc-only changes; no heavy code review needed.

7. **Confirm** to the user in 1–3 lines: what you added/corrected in which guide (with the commit
   SHAs), that the kit change awaits the next kit release, and any §7 question you still need them
   to answer.

## Notes

- Bias toward capturing MORE — a play guide that's slightly verbose beats one that silently omits the
  gotcha that cost the next session an hour.
- If nothing gameplay-relevant was learned this session, say so plainly and don't pad the doc.
- This pairs with `/handoff` (which captures *work state*); learnToPlay captures *game knowledge*.
  Run it before a handoff so the doc the next session reads is current.
