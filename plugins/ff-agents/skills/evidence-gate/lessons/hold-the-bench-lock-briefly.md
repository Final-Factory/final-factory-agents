# Hold the bench lock as briefly as the question allows (w1628, 2026-10-20)

**The rule.** lothsahn, 2026-10-20: "Workers should also consider how they can hold a bench lock as short as possible.
A benchmark with 90% fidelity that runs twice as fast as better one is likely the right choice." Before you take a
machine's bench lock, pick the shortest run that still answers your question. That means the fewest and shortest legs
that can show the difference you are after, an early stop once the result is clear past the noise, and no re-run you
do not need. Only a run whose numbers are times takes the exclusive lock. Untimed heavy work takes a shared ticket
(`bench_lock --shared`), and a build takes nothing extra.

**Why.** On 2026-10-20 (00:00 to 15:58 UTC, measured from each machine's transcripts and run logs; the game repo's
`Documentation/Bench-Lock.md`):

- BEAST's lock was held 15.5 of 16 hours, and requests spent 40 hours waiting in its queue (not counting waits behind
  their own legs).
- lothdesktop's lock was held 13.1 hours, with 14.3 hours of waiting.
- lothsahn: "Timed runs are killing our throughput... Our workers have become almost serial instead of parallel."

Where the time went:

- **Builds under the exclusive lock.** They held it for 1.7 h on BEAST and 3.8 h on lothdesktop (one release build
  held it 58 minutes). Determinism pairs and repros held it for another 1.3 h and 1.1 h.
- **An idle tail in every probe leg.** The player's dwell counts from the end of its command chain, but the probe
  scripts asked for `SETTLE + 2 x SAMPLE + 15` s more: 120 s of nothing per leg at the defaults. With a 240 s settle
  and 90 s sample, legs ran 810 to 824 s until the backstop killed them.
- **Rounds past the answer.** w1243's radius A/B queued 20 legs of 746 s each. Its two arms were apart by 0.5 ms
  against a 0.17 ms spread after two rounds; stopping there would have freed about 3.3 hours of BEAST.

**How to apply.**

1. Write the question and the smallest difference that would change your decision before the first leg. A
   difference of several percent shows in two rounds of 60 s on a quiet machine (BEAST repeats to about 1 to 2%).
   A 1% question on a busy machine needs a closer measurement (the per-system time, a timed call), not 20 rounds.
2. Leave the probe scripts' early stop on (`scripts/bench/ab_stop.py`; `EARLY_STOP=0` only when you can say why).
   Use an even round count as the cap, not the plan.
3. Keep legs short: a settle long enough for the event you measure, a sample of 30 to 60 s, and no longer.
4. Untimed work (a determinism pair, a functional repro, a census, a Steam launch check) takes
   `bench_lock --shared`. A build takes no `bench_lock` at all, because `build_player.sh` and `ff_unity_slot` queue
   their own shared ticket.
5. Give the lock back between legs, and do builds and digests outside it.
6. After the run, `python scripts/bench/bench_queue.py report` shows your holds and whom they kept waiting. Put the
   lock time beside the result in your report.
