---
name: decide-a-before-after-on-one-or-two-samples
description: "A before/after timing (a fix against master: fps, frame times, bench runs) is decided on 1 or 2 samples per side, each run 5 to 10 minutes at most; more only with a stated reason to suspect a result. After a move to another computer, re-time the baseline there."
date: 2026-10-25
---

# Decide a before/after on one or two samples per side

**Rule.**

- Decide a before/after (a fix against master: fps, frame times, bench runs) with 1 or 2 timing samples on each side.
  Take more only with a strong reason to suspect a result is wrong, and say that reason in the report.
- Each test run lasts 5 to 10 minutes at most.
- After the work moves to another computer, time the baseline again there. Timings never compare across machines.
- Plan the A/B as 1 build per side, run alternating (A, B, A, B) in one exclusive session, with the same leg sequence
  on both sides, so a change in the machine's state hits both sides equally.

**Why.** w2099 (the Mass Driver FPS fix, 2026-10-25) took about 12 timing passes over an hour (about 7 on BEAST, 5 on
LothLaptop) plus several player builds. Passes were repeated because the fix's run did not use master's sequence of
legs, and because a reboot changed the machine between the two sides. lothsahn (w2229): "It makes sense that it needs
to rebaseline when moved to a different computer. But we should generally decide with 1 or 2 samples before and
after. Cna you updat eyour notes that workers should avoid more than 2 tests on each before/after unless there's a
strong reason to suspect it's wrong. And each test should be short: 5-10 minutes at most. It's been working on this
for an hour."

**How to apply.** Before the first timed leg, write the plan: the builds (one per side), the leg sequence (one script,
used for both), the order (A, B, A, B), and the run length (10 minutes at most). Run it in one exclusive ticket on one
machine, without a reboot or a sandbox move between sides. A third sample needs its reason in the report ("side B's
second run read 40% off its first"). If the run must move to another computer, both sides run again there. This
works with the bench checklist's "Shortest run that answers the question" and the lesson
[a speed-up is one build, switched off and on, back to back](settle-your-own-guesses.md#a-speed-up-is-one-build-switched-off-and-on-back-to-back-w1069-2026-10-13):
it caps how many samples, while those choose how short each is and what is compared.
