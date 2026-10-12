---
name: feedback-carry-over-merges-into-the-new
description: "When a person asks for an old thing's duties to carry over into its replacement, merge what was lost into the new thing's own structure and words. Never paste the old text back, re-point at the old, or keep a history of the old inside the new; list each item merged and where it now sits, and what you left out and why."
date: 2026-10-12
metadata:
  type: feedback
---

# Carrying over means merging into the new, not restoring the old

**Rule.** When an old tool, agent or document is replaced and its duties "carry over" (a standing agent folded into a
job timer, an old script into a new one, an old doc into its successor), the replacement absorbs them in its own
structure and voice. Compare the two item by item, write each missing duty where it belongs in the new, and leave the
old out: no wholesale copy of its text, no "the old X did" headings, no pointers to its folder or archive as
instructions, no history section about it. Report a table of each item merged and where it now sits, and a list of
what you left out on purpose, with why.

**Why.** w905, 2026-10-12: the Nightly Regression Sentry became the nightly merge review. Asked to compare the old
charter with the new, the worker found what was missing in the Sentry's archived notes and added it, but as "How the
Sentry worked, kept", "The Sentry's recurring risk patterns … verbatim", pointers to the archive and a "What changed from
the Sentry" section. Lothsahn: "w905 is merging those differences into the new sentry, right? Not just restoring the
old?" and "We still want the old gone". The same content, re-homed as the review's own rules, was what he wanted
(FinalFactory #1560).

**How to apply.**

- Before the PR, grep the new file for the old name, its folder and its archive path. What is left must be one line of
  history, a person's quoted words, or a fact the code still needs (an id the billing keys on).
- Headings and templates use the new name. A list carried over becomes the new thing's own list ("grown by its
  reports"), not "its own list, verbatim".
- One-time migration steps (copy the old folder, start where the old stopped) come out once they are done.
- The PR description carries the item → location table and the left-out list; the archive stays readable for history,
  not as instructions.
