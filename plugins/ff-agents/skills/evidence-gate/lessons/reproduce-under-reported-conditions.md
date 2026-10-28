---
name: reproduce-under-reported-conditions
description: "Before a report names a bug's cause, list the reporter's conditions (save, mods, settings, machine and GPU, the exact symptom) beside the repro's. A difference is removed, or the cause is shown with and without it. A finding under different conditions is a contributing factor, not the cause."
date: 2026-10-28
---

# Reproduce under the reporter's conditions before naming a cause

**Rule.** Before a report says "the cause is X", write two columns: what the reporter described and
what your repro had. Rows: the save, the mods, the settings, the machine and GPU, and the exact
symptom (their words, not your summary of them). For every row that differs (an extra mod, a
different symptom):

- remove the difference and reproduce again, or
- reproduce the cause both with and without it.

Only then call it the cause. The report says which conditions were matched and which were not.
A finding under conditions that differ and were not settled is a **contributing factor**, labelled
so, not the cause.

**Why.** Two corrections of the same kind from lothsahn (2026-10-28, w2480):

1. w844 (Frenzy does nothing): the worker reproduced "bats arrive too late" while the report said
   the bats never flew out, and called that the cause. lothsahn: "That's a reasonable fix and we
   should keep it, but the bats weren't even flying out at all.  There was a different problem".
   The symptom row differed (late versus never), and nobody noticed.
2. w2448 (uncapped movement judder on Wittlebase): the worker measured only with lothsahn's Cruiser
   mod loaded and named the mod's 6.3 ms Update spike as the cause. lothsahn: "Please merge this
   fix then re-time with the mod disabled.  The judder was present without the mod". The mods row
   differed; one run without the mod would have shown it.

Both fixes were real improvements; each was reported as the answer while the reported problem
stayed.

**How to apply.**

- Fill the two columns before the first number goes into a report. Take the reporter's side from
  the report, thread or request text itself and quote the symptom.
- A condition you cannot match (their GPU, their save) is named as unmatched. The finding is then
  a contributing factor, and the report says what run would settle it.
- The cheap case is a run with the extra thing off (mod disabled, default settings, their save).
  Do it before the report, not after the person asks.
- Keep a real fix that you found on the way; label it a contributing factor and carry on looking for
  the reported symptom.
- Related: [measure against what the player sees](measure-against-what-the-player-sees.md),
  [settle your own guesses](settle-your-own-guesses.md).
