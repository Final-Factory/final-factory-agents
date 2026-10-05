---
name: check-the-other-systems-live-config
description: "A tool's summary sentence about what another system does (or does not do) is not a fact until that system's own live config or state says so; read it before relaying the claim."
date: 2026-10-05
---

# Check the other system's live config before relaying what it does

**Rule.** When a tool, a page or a status line of one system says what *another* system does or
does not do ("automatic investigations are not built yet", "nothing will pick this up", "that
switch is off"), treat the sentence as a guess about the other system. Before you pass it on as
fact, read the other system's own live config or state, and quote that.

**Why.** 2026-10-05 (w412, fixing FF Factory's FFBox signatures view): FF Factory's
`ffbox_activity show signatures` printed "Automatic investigations are not built yet (phase 4)
... 0 would start", a sentence hard-coded from FF Factory's own unbuilt plan. An orchestrator
relayed it to Ben as what FFBox does. FFBox's live config had `intake.auto.enabled = true`
(settle 5 min, `max_per_day` 24, `ffdiagnose`), and FFBox had been diagnosing every crash and
desync report by itself since 2026-10-04 (Build 76's Windows crash report
20261005T035612Z-crash-6102d405dc had FFBox conversation 684). Ben: "that seems wrong ffbox does
auto do that, look at ffbox code/harness".

**How to apply.**

- A claim about FFBox comes from FFBox: `ffbox_activity show config` (its effective config),
  `show signatures` (now reads `intake.auto` and each report's diagnosis conversation live),
  `show conversations`, `show status`; a worker's `fetch_ffbox_report` names the diagnosing
  conversation. The same holds for any other system: its config file, its API, its logs.
- If the other system cannot answer now, say "unknown" and why, not the tool's sentence.
- Label the claim: measured (you read the live config: which key, which value) or a guess.
- A tool that prints a fixed sentence about another system's behaviour is a bug: fix it to read
  that system, or to say it cannot know.
