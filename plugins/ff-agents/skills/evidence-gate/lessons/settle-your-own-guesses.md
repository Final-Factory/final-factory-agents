---
name: settle-your-own-guesses
description: "The evidence gate is self-enforced. An agent settles a guess by research or measurement and then proceeds; the person is asked only for money values, for what the rules reserve for them, and for a fork research could not settle."
date: 2026-10-02
---

# Settle your own guesses

**Rule.** A guess on a choice that affects the outcome is yours to settle: research it or measure
it, record the basis, and carry on. "The person decided" is not a way out of research.

Ask the person only for:

1. **Money:** the value (a budget, a bid, a purchase), once per decision, with the evidence shown.
2. **What the rules already reserve for them:** deletes, app settings and deploys, publishing in
   their name, releases. Merging your own verified work is not on the list: later the same day Ben
   added "stop holding prs, just merge them" ([merge your own pull request](merge-your-own-pr.md)).
3. **A real fork research could not settle:** the options, with a recommendation.

**Why.** Ben, 2026-10-02, on the first design of this gate, which let a guess be resolved by
escalating it: "I want the agent to be mostly autonomous. i dont want you to run every decision
by me. i just want YOU to make sure you are making decisions with appropriate context and
research. If its spending actual money then yea, ask me to confirm the value."

The Reddit campaign went wrong while Ben was approving things: he said yes to caps he had no way
to judge. More questions to him would not have helped. Research by the agent would have.

**How to apply.**

- The record stays a few lines and is never a questionnaire for the person.
- When a row is a guess, the next step is research, in this order: the tool's own docs, the value
  its screen shows, our own data, other people's write-ups, a small reversible test.
- When you do ask about money, show what the value rests on beside the ask.
- An orchestrator that receives a guess from a worker sends it back to be researched. It does
  not pass the question to the person.
- Reports still label each number and recommendation measured, sourced or guess, so the person
  can see what a result rests on without being asked to decide it.

## When a measurement cannot resolve it, measure closer to the change (w824, 2026-10-09)

A measurement whose spread is wider than the difference you must judge settles nothing: neither escalate on its
noise nor merge on a hunch. Measure the changed code itself, as an upper bound, and measure the case that triggers
it. w824 (PR #1332, the vision fingerprint skipping blueprint-preview children, a class 3 FFBox desync PR): the
2-peer JustPlay bench on BEAST, 4+4 interleaved runs, gave host heartbeat means of 123.3 ± 3.6 against
125.3 ± 9.4 ms, a standard error of 5 ms on the delta against a 1% threshold of 1.2 ms (about 280 runs would have
resolved it). Timing `PrepareC3VisionChunks`, the only main-thread code the change adds, on JustPlay in the editor
(1.08 ms median over 50 calls, once per 8 heartbeats) bounded the change at +0.11% tick mean, +0.63% p95 and +0.57%
frame median. Timing the vision hash with a held preview found a cost the bench could never show: 47.6 against
42.6 ms, every one of 45,566 holders paying a hash-set lookup; the review limited it to Parent-bearing chunks (49.9
against 50.0 ms after). The steps for class 3 PRs are in `checklists/ffbox-desync-pr.md`.
