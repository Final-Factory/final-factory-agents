# FFBox desync PRs: classify, verify, merge or escalate

Lothsahn's standing policy (2026-10-04, w358): "Please update your harness, FFFactory, and/or rules
necessary to make sure you remember how to do this." It holds for every FFBox desync diagnosis and
its `ffbox/*` PR, however it reaches you: an FF Factory intake request tagged "desync PR policy"
(triage `ffbox-desync`), a review-branch request, an escalation, or a person handing you one.
FF Factory approves these at once and adds the policy to the worker's brief (FF Factory
docs/intake.md, "FFBox desync PRs"); this page is the checklist and the commands.

## 1. Classify before anything else

Read the whole diff against `origin/develop`. Write the class and the reason (the files, and when the
changed code runs) in your first report and in the PR description.

| Class | What it changes | What it needs |
|---|---|---|
| 1. Report generation only | code that runs only while a desync report is written or uploaded: what the report holds, its files, its upload. No effect on the game while it plays | tests, then merge |
| 2. A desync fix in the game code | the simulation, so the peers no longer fork | a failing-first test and a 2-peer built-player check, then merge |
| 3. Capture during play | what is captured while the game plays: the simulation hash or fingerprint, the census, per-heartbeat or per-frame capture or recording, anything that costs time during play | a before/after performance measurement; merge only if negligible |

- A change that spans classes takes the highest.
- Class 1 or 3 in doubt is 3. "Only runs when a desync is detected" is class 1 only if the code it
  adds is reached from the report writer and nowhere on the heartbeat or frame path; show the call
  sites (`file.cs:line`).
- That covers every existing function the diff changes, not only the ones it adds: list each
  changed function's callers. A helper the report shares with a per-heartbeat capture is on the
  heartbeat path (w817, PR #1327: FFBox changed `DescribeBotOwner` to print `bot=dead`, and
  `DescribeConstruction` feeds both the report's `DetailDumps` and
  `DeterminismFingerprintSystem.RecordDetail` every heartbeat in audit sessions). It is class 3
  unless you split the change so that path prints exactly what develop prints (there: a report-only
  `DescribeConstructionForReport` overload, plus a test that the audit dump is unchanged).
- A class 2 fix that also adds capture is class 3 for the capture part.

## 2. Class 1: safe to merge

- [ ] The fast suite (`FFEditorTests`) passes on the branch, compile verified (the `editor-ops` ritual).
- [ ] A test covers the report it writes (add one when none does).
- [ ] Every new call site is on the report path only: cite them.
- [ ] The PR's `## Evidence` says class 1, the call sites, the tests ([merges](merge.md)), then merge.
- [ ] CI red from `Tests.Performance.InterpolationRestoreCostTest.RestoringALateGameFrame_IsFasterThanTheSingleJob`
      alone is that wall-clock test's known flake on the shared runner (it also failed on unrelated
      PR heads aab19faf4 and d61b6c7fa, and on #1327's first attempt, which passed on rerun, w817).
      Read the failed test's name from the `editmode Test Results` annotations, then
      `gh run rerun <run id> --failed`; don't change code for it.

## 3. Class 2: proven red, then green

- [ ] A test that fails on develop and passes with the fix: run both and quote the results.
- [ ] A 2-peer built-player check that reproduces the fork: red on develop, green with the fix,
      with the heartbeat count (the `determinism-audit` skill; players start from the slot pool,
      never a new exe path).
- [ ] The repo's rules: `fp` only, no wall-clock or frame dependence, the crown-jewel surfaces,
      save compatibility (an UpgradeStep and a golden fixture if saved state changes).
- [ ] `## Evidence` Kind `simulation` with Tests, Determinism audit, Save compatibility
      (`pr_evidence.py` PASS), then merge.

## 4. Class 3: measure before you merge

**What to measure.** Tick time: the heartbeat's main-thread cost, mean and p95 (a capture that runs
every Nth heartbeat, like the fingerprint sampler every 8, hides in the median). Frame time: the
heartbeat-frame wall median. Develop against the branch.

**Method** (game repo; `Documentation/Performance-Simulation-Big-Saves-2026-10-03.md` for the setup):

1. Two bench players, one from `origin/develop` and one from the branch, the same way on the same
   machine: `Unity -batchmode -quit -projectPath . -buildTarget Win64 -executeMethod
   Editor.ShaderBenchBuild.BuildWindows -ffBenchBuildOutput "$PWD/builds/<name>/finalfactory.exe"`.
2. The biggest save you can load (JustPlay where present; else the biggest in the saves folder or the
   golden fixtures), the same save for both.
3. A session that runs the changed code. Solo: `-ffBench save:<name> -ffBenchSystems 1
   -ffBenchSeconds 180 -ffBenchOut <absolute dir>`. A capture that runs only in multiplayer (the
   runtime desync detector, the fingerprint sampler) needs two peers:
   `scripts/bench/run_mp_frame_bench.sh <player.exe> <outDir> 180 <save>` then
   `scripts/bench/analyze_frames.py`. Start every player through the slot pool
   (`scripts/nightly/player_slots.py launch`; in a worker-root sandbox that is its own pair, slotK-0 and slotK-1,
   and `--peer 1` gives a same-build client its own folder).
4. Interleave: develop, branch, develop, branch, at least 3 runs each. On a shared machine hold the
   GPU bench lock for each run and note what else ran.
5. `python scripts/bench/ab_summary.py <runs dir> <prefix> develop branch` (solo runs): mean ± standard
   deviation per build of the heartbeat median, mean and p95 and the heartbeat-frame wall median.

**Negligible** means each of tick mean, tick p95 and frame median rises by less than 1% of develop's
value, and the runs resolve it: the difference of the means is clear of the run-to-run spread, or
add runs until it is. A difference you cannot resolve is not negligible.

- [ ] Negligible: put the table and the method in the PR, validate it as class 1 or 2 above, merge.
- [ ] Not negligible: do not merge. Leave the PR open and end your turn with one line, FF Factory
      reads it and puts the request back in the intake for a developer (needs a human), linked to
      the PR:

      PERF-ESCALATION: PR #<n>: <the change in a phrase>; tick <before> -> <after> ms (+<x>%), frame <before> -> <after> ms (+<y>%) on <save>

      Outside FF Factory's intake, file the same as a needs-human intake request (the numbers, a
      change summary, the PR link). Never merge a class 3 PR with a measured cost yourself; a
      reviewer's approval of the escalation is what merges it.

## 5. Merge

Through the PR, once CI is green (open one from the `ffbox/*` branch when FFBox opened none: a
branch gets CI only through a PR). No "fixed" or "merged" post to the reporter anywhere: FFBox sees
the merge and tells its thread. The PR keeps any `Discord: <thread url>` line.
