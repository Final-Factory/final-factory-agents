# Checklist: before a timed bench run on a shared machine (w1628)

Lesson: [hold the bench lock as briefly as the question allows](../lessons/settle-your-own-guesses.md#hold-the-bench-lock-as-briefly-as-the-question-allows-w1628-2026-10-20).
Mechanics: the game repo's `Documentation/Bench-Lock.md`.

- [ ] **Shortest run that answers the question.** The question and the smallest difference that would change the
      decision are written down. The legs, sample and settle are the shortest that can show it (a few percent: two
      rounds of 30 to 60 s on a quiet machine), and the round count is a cap.
- [ ] **Early stop on.** The probe scripts' `ab_stop.py` stop is left on, or the report says why `EARLY_STOP=0`.
- [ ] **The right ticket.** `bench_lock` (exclusive) only for a run whose numbers are times. Untimed heavy work
      (determinism pairs, repros, censuses, launch checks) takes `bench_lock --shared`. A build takes no `bench_lock`,
      because its own `ff_unity_slot` ticket queues it.
- [ ] **Nothing under the lock but the leg.** The Unity slot is taken before the ticket. Builds and digests run
      outside it, and the lock is given back between legs.
- [ ] **Lock time reported.** The result says how long the run held the lock (`bench_queue.py report`).
