# Write status reports in simpler, plainer language

**What Ben said (2026-08-17):** "when you give me these reports, can you use somewhat simpler,
less verbose language?" — given mid-session after a run of dense, jargon-heavy multiplayer
status reports.

**Why:** Ben still wants ALL the technical detail (that rule stands, CLAUDE.md), and he still
wants a TL;DR first. What he does not want is prose that is hard to parse: long sentences
packed with run ids, surface names, and shorthand, one clause after another. Reading effort is
the constraint, not information.

**How to apply:**

- Plain words, short sentences. Say "two machines picked a different winner" before naming
  the job and the surface id.
- One idea per sentence. Cut clauses that only restate what evidence already shows.
- Keep the structure: TL;DR first, detail below. Detail keeps file:line citations and run ids —
  just carried by simpler prose, or bullets, not woven into dense paragraphs.
- Codenames and run ids are reference material, not narrative: put them in parentheses or a
  bullet, and never make the reader decode one to follow the point of a sentence.
- This applies to chat reports and decision asks. Committed docs already have their own rule
  (match length to need, CLAUDE.md).
