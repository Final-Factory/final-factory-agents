---
name: bench-fight-ab-needs-bench-mode-and-a-raw-digest
description: "probe_ab_win_switches.sh ignores -ffBenchFight and every other -ffBench* flag unless BENCH=1 (the run measures the idle save and exits 0 with plausible numbers); a Burst job's worker-thread time in a Windows player comes from PROFILE=1 .raw logs digested with rawreader/PhysicsJobDigest.cs -pdMatch, not from -ffBenchJobs or PerfSystems."
---

# A timed fight A/B: bench mode on, job time from the profiler log (2026-10-24, w1985 for w1440)

w1985 timed PR #2156 (lazy line-of-sight targeter) with the brief's command, `probe_ab_win_switches.sh ... "lazy=-ffBenchFight 1000 ..." "allrays=... -ffAllTargeterRays"`
and no `BENCH=1`. All four legs ran, exited 0 and gave a 4.9 ms difference, on an idle save: no fight ran.

- **`-ffBenchFight <ships>` is read only in the bench's save mode** (`-ffBench save:<save>`; FinalFactory
  `Assets/Scripts/Behaviours/Bench/ContentShaderBench.cs` reads `-ffBench` and calls `Fight` inside that flow).
  `probe_ab_win_switches.sh` adds `-ffBench save:` only with `BENCH=1`; without it the arm's extra flags go to the
  automation perf probe, which ignores them. Before reporting, check every leg's `player.log` for
  `[ShaderBench] fight: <N> ships` and the `fight-<N> 30s: ... frame p50` line; `probe_table.py` reads only
  the perf probe ("no PerfSummary" on bench legs), so read the bench line or `analyze_systems.py <run>/bench/fight-<N>`.
- **A job's time is on worker threads**: main-thread PerfSystems and `fight-<N>-systems.csv` show the system
  (TargetingSystem ~70 us) but not its job (TargeterJob 11 to 36 ms per frame summed over workers). `-ffBenchJobs 1`
  recorded no job rows in the Windows player (again, as w1199 found). What worked: `PROFILE=1 BENCH=1` (each leg
  writes `bench/fight-<N>.raw`, about 600 MB), then `scripts/bench/rawreader/PhysicsJobDigest.cs` copied into
  `Assets/Editor/<scratch>/` with a few-line wrapper that loops `PhysicsJobDigest.Analyse(log, new Regex("Targeter|..."))`
  over all legs in one `unity-slot run -- Unity.exe -batchmode -nographics -quit -executeMethod ...` (about 3 min
  for four logs), then delete the scratch folder. The profiler adds cost: frame times from the unprofiled run,
  job times from the profiled one.
- Result there: TargeterJob lazy 11.0/12.7 ms vs all-rays 22.3/36.1 ms per frame, frame p50 ~62 ms both (main-thread bound).
