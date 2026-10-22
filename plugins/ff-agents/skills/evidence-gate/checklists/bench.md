# Checklist: before a timed bench run on a shared machine (w1628)

Lesson: [hold the bench lock as briefly as the question allows](../lessons/settle-your-own-guesses.md#hold-the-bench-lock-as-briefly-as-the-question-allows-w1628-2026-10-20).
Mechanics: the game repo's `Documentation/Bench-Lock.md`.

- [ ] **Shortest run that answers the question.** The question and the smallest difference that would change the
      decision are written down. The legs, sample and settle are the shortest that can show it (a few percent: two
      rounds of 30 to 60 s on a quiet machine), and the round count is a cap.
- [ ] **A short plan.** The fewest rounds that can answer the question (lothsahn: "Get them all to shorten their plans a
      lot"); the round count is a cap, never the plan.
- [ ] **Early stop on, and a decision on enough signal.** The probe scripts' `ab_stop.py` stop is left on, or the
      report says why `EARLY_STOP=0`. Once the data shows the answer beyond the noise, stop and decide (lothsahn: "if
      they have sufficient signal, just make a decision"), with the measured numbers and their spread in the report.
- [ ] **At most one hour per exclusive hold.** The run is split so each hold ends within 60 minutes and the lock is
      given back between them (lothsahn: "subdivide their work to not hold the exclusive lock longer than 1 hour at a
      time"); `bench_unlock` warns past the hour and `report` flags it.
- [ ] **The right ticket.** `bench_lock` (exclusive) only for a run whose numbers are times. Untimed heavy work
      (determinism pairs, repros, censuses, launch checks) takes `bench_lock --shared`. A build takes no `bench_lock`,
      because its own `ff_unity_slot` ticket queues it.
- [ ] **The machine is yours while you hold it, and only then** (w1750). Your own players and clips pass the lock (the same `FF_SESSION_ID`, or inside `bench_lock`); other workers' are refused until you give it back, so give it back between legs. Not covered: a player already running when you were granted (your `quiet` gate waits for its CPU).
- [ ] **Nothing under the lock but the leg.** The Unity slot is taken before the ticket. Builds and digests run
      outside it, and the lock is given back between legs.
- [ ] **Lock time reported.** The result says how long the run held the lock (`bench_queue.py report`).
