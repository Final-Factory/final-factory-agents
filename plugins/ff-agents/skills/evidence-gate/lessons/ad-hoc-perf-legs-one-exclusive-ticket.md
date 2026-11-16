# Ad hoc PERF and rerun legs: one exclusive ticket, adaptive vSync off, a void rerun is rerun (w4444, 2026-11-16)

Four traps from fixing the 2026-11-16 nightly regressions (w4444, lothdesktop), each with the check that catches it.

1. **All legs of an ad hoc PERF A/B run inside ONE `bench_queue.py run --mode exclusive` ticket.** A script that took a
   ticket per leg went to the back of the queue each time; the first leg waited about 40 minutes and the next about 42
   behind other workers' shared tickets (measured, w4444). Write the legs into one script and run it under a single
   `bench_queue.py run --mode exclusive -- <script>`; order the legs fix, base, fix, base so drift shows.
2. **A windowed PERF leg can cap at 60 fps through adaptive vSync.** Pass `--peer-arg solo=-ffNoAdaptiveVSync` (the flag
   is read at `Assets/Scripts/Behaviours/Settings/FramePacer.cs:474-476`; `AdaptiveVSync.cs:30` explains it). A frame
   time that sits at 16.7 ms on every build is the cap, not the code.
3. **An EditMode test of a TMP text's layout needs a Canvas on a parent**, or `textInfo` stays empty and every line
   count or size reads 0. Parent the text under a `Canvas` GameObject before `ForceMeshUpdate`.
4. **A rerun that ends `env` while a person plays on that PC is void** (the player-yield, w1894: the bench stops the
   test players when a person starts the game; 7 of 11 reruns in w4444 were void). Do not count it as pass or fail: run
   it again after the game closes, and say in the report which runs were void.
