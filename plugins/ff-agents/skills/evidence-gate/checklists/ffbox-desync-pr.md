# FFBox desync PRs: classify, verify, merge or escalate

Lothsahn's standing policy (2026-10-04, w358): "Please update your harness, FFFactory, and/or rules
necessary to make sure you remember how to do this." It holds for every FFBox desync diagnosis and
its `ffbox/*` PR, however it reaches you: an FF Factory intake request tagged "desync PR policy"
(triage `ffbox-desync`), a review-branch request, an escalation, or a person handing you one.
FF Factory approves these at once and adds the policy to the worker's brief (FF Factory
docs/intake.md, "FFBox desync PRs"); this page is the checklist and the commands.

## 0. What an FFBox fix branch carries (w1819, 2026-10-23)

Lothsahn: "Why does ffbox make a fix and propose it and it gets independently developed by a
worker? Seems like we're wasting time." Since ffbox commits 1754f18 and 786f5ec:

- **One branch per root cause.** Every diagnosis brief lists the open `ffbox/*` fix branches with
  their root causes, and a diagnosis of a cause one of them already fixes joins that branch
  (`joins_branch`) instead of pushing a second one: its conversation adopts the branch, its reports
  come to FF Factory under that branch's key (the brief says "joined that branch"), and a change the
  branch still needs arrives as new commits on it. So one request may carry several conversations'
  reports. Two `ffbox/*` branches for one cause now means one predates this or two diagnoses ran at
  once: validate the more complete one, close the other with the reason, and say which in the PR.
- **A regression test, measured by the harness.** For a diagnosis, the container reruns the branch's
  EditMode test classes with every file the fix changed outside its tests put back to `master`, and
  the PR body (and the FF Factory request) carries the line `Regression test, measured by the
  harness in its container: ... Red on master ... green with the fix ...`. Rerun that test both
  ways yourself (`run_tests` by name on `origin/master` and on the branch) and quote it: that is the
  failing-first test of class 2, so do not write a second one. When the line says **not measured**
  or **does not fail without the fix**, writing a test that is red on master is your first step,
  and the PR says the FFBox one was missing or did not reproduce. The agent's own `## Regression
  test` section names any test the container could not run (a play-mode test, a three-peer
  scenario): run it.

## 1. Classify before anything else

Read the whole diff against `origin/master`. Write the class and the reason (the files, and when the
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
  unless you split the change so that path prints exactly what master prints (there: a report-only
  `DescribeConstructionForReport` overload, plus a test that the audit dump is unchanged).
  Second case, w1013 (PR #1472): FFBox reordered `FleetMoverInputDiagnostics.Describe` (shooters
  first, a character budget, new header fields, an extra projectile query) for the report's
  `FleetInputsDetail`. The Diagnostic audit profile appends the same `Describe` to `DescribeMovers`,
  which `DeterminismFingerprintSystem` records on audit heartbeats. The split: `Describe(em)` kept
  master's code path and `DescribeForReport(em, budget)` took the new behaviour. FFBox's PRs keep
  doing this, so grep every changed `Describe*` and every function it calls for callers outside
  `DesyncReportCollector`.
- A class 2 fix that also adds capture is class 3 for the capture part.

## 2. Class 1: safe to merge

- [ ] The fast suite (`FFEditorTests`) passes on the branch, compile verified (the `editor-ops` ritual).
- [ ] A test covers the report it writes (add one when none does).
- [ ] Every new call site is on the report path only: cite them.
- [ ] A dump meant to name the forked record is proven by forking: a test forks one record past
      the old dump's cap once per field the surface hash folds, diffs the before and after dumps the
      way a reader diffs the two peers' halves, and asserts that exactly that record's entry differs
      and only the edited field in it. List every field the record's sub-hash folds and check that
      each one shows in the dump. w928 (PR #1416): FFBox's `MoverDigestsDetail` printed seven group
      digests, but no group covered Position (which an owning rail folds) or the raw Flags (the
      `FlagAvoidanceTangentChosen` bit is the one folded field of a mirrored fleet rail that changes
      in play). A position or flag fork would have shown as a changed sub-hash with every group
      equal. The field-by-field fork test found it, and `pos=` and `fl=` were added before the merge.
- [ ] The PR's `## Evidence` says class 1, the call sites, the tests ([merges](merge.md)), then merge.
- [ ] CI red from `Tests.Performance.InterpolationRestoreCostTest.RestoringALateGameFrame_IsFasterThanTheSingleJob`
      alone is that wall-clock test's known flake on the shared runner (it also failed on unrelated
      PR heads aab19faf4 and d61b6c7fa, and on #1327's first attempt, which passed on rerun, w817).
      Read the failed test's name from the `editmode Test Results` annotations, then
      `gh run rerun <run id> --failed`; don't change code for it.

## 3. Class 2: proven red, then green

- [ ] A test that fails on master and passes with the fix: run both and quote the results.
- [ ] A 2-peer built-player check that reproduces the fork: red on master, green with the fix,
      with the heartbeat count (the `determinism-audit` skill; players start from the slot pool,
      never a new exe path).
- [ ] The repo's rules: `fp` only, no wall-clock or frame dependence, the crown-jewel surfaces,
      save compatibility (an UpgradeStep and a golden fixture if saved state changes).
- [ ] Save version bumped -> old-save load test present, run, green. Then the bump needs no person's
      sign-off (Ben, 2026-10-23, w1826: "its fine that a later version save doesnt load in an old
      version of the game lol. just backwards compatibility is important"): an older build refusing a
      newer save with the clean "newer version" error is fine. Only a change that would break loading
      of existing saves goes to a person ([lesson](../lessons/merge-your-own-pr.md#a-save-version-bump-that-keeps-old-saves-loading-needs-no-person-w1826-2026-10-23)).
- [ ] `## Evidence` Kind `simulation` with Tests, Determinism audit, Save compatibility
      (`pr_evidence.py` PASS), then merge.

## 4. Class 3: measure before you merge

**What to measure.** Tick time: the heartbeat's main-thread cost, mean and p95 (a capture that runs
every Nth heartbeat, like the fingerprint sampler every 8, hides in the median). Frame time: the
heartbeat-frame wall median. Master against the branch.

**Method** (game repo; `Documentation/Performance-Simulation-Big-Saves-2026-10-03.md` for the setup):

1. Two bench players, one from `origin/master` and one from the branch, the same way on the same
   machine: `Unity -batchmode -quit -projectPath . -buildTarget Win64 -executeMethod
   Editor.ShaderBenchBuild.BuildWindows -ffBenchBuildOutput "$PWD/builds/<name>/finalfactory.exe"`.
2. The biggest save you can load (JustPlay where present: on BEAST it is
   `LocalLow/Never Games/finalfactory/save-backups/JustPlay 0.20.0.91 0 (pre-columnar 2025-08-26).zip`, not in
   `saves/`, so copy it into `saves/` under a name nobody else uses and remove it after; else the biggest in the saves folder or the
   golden fixtures), the same save for both.
3. A session that runs the changed code. Solo: `-ffBench save:<name> -ffBenchSystems 1
   -ffBenchSeconds 180 -ffBenchOut <absolute dir>`. A capture that runs only in multiplayer (the
   runtime desync detector, the fingerprint sampler) needs two peers:
   `scripts/bench/run_mp_frame_bench.sh <player.exe> <outDir> 180 <save>` then
   `scripts/bench/analyze_frames.py`. Start every player through the slot pool
   (`scripts/nightly/player_slots.py launch`; in a worker-root sandbox that is its own pair, slotK-0 and slotK-1,
   and `--peer 1` gives a same-build client its own folder).
4. Interleave: master, branch, master, branch, at least 3 runs each. On a shared machine hold the
   bench lock (`bench_lock`, w1615) for each run and note what else ran.
5. `python scripts/bench/ab_summary.py <runs dir> <prefix> master branch` (solo runs): mean ± standard
   deviation per build of the heartbeat median, mean and p95 and the heartbeat-frame wall median.

**Negligible** means each of tick mean, tick p95 and frame median rises by less than 1% of master's
value, and the runs resolve it: the difference of the means is clear of the run-to-run spread, or
add runs until it is. A difference you cannot resolve is not negligible.

**When the whole-heartbeat runs cannot resolve 1%, time the added code itself** ([lesson](../lessons/settle-your-own-guesses.md#when-a-measurement-cannot-resolve-it-measure-closer-to-the-change-w824-2026-10-09)).
On a shared machine the 2-peer bench's spread can be far wider than 1% (w824 on BEAST, JustPlay, 4+4 interleaved
runs: host heartbeat mean 123.3 ± 3.6 against 125.3 ± 9.4 ms, standard error of the delta 5 ms against a 1% threshold
of 1.2 ms; about 280 runs would resolve it). Then:

- Load the same save in the editor, unpause it (drive-game recipes: runtime-provisioned state appears only after the
  unpause), and call each function the change adds on the heartbeat path through reflection, ~50 times with a
  `Stopwatch`. The editor figure is an upper bound (w824: the whole fingerprint took 225 ms in the editor against
  ~37 ms on the player's sampled heartbeat). Convert it: per-sample cost / sample interval against the tick mean,
  the per-sample cost against tick p95 and the frame median.
- Time the capture again with the case that triggers the change present (the preview, the ghost, the dead
  ship), interleaved with it absent. w824's fix was free in an ordinary world and cost 5 ms per vision hash while a
  preview was held (47.6 against 42.6 ms), because every holder paid a hash-set lookup; the review limited it to
  the chunks that can hold an excluded entity.
- Put both bench tables and the direct timing in the PR, and say which one resolves each number.

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
