# Burst's editor options are machine-wide: never flip them on a shared machine

**What:** `BurstCompiler.Options.EnableBurstSafetyChecks` (Jobs > Burst > Safety Checks), and its siblings
`EnableBurstCompilation`, `ForceEnableBurstSafetyChecks`, `EnableBurstCompileSynchronously` and `EnableBurstDebug`, are
editor preferences, not project settings. Unity keeps them per user in the registry,
`HKCU\Software\Unity Technologies\Unity Editor 5.x` (`BurstSafetyChecks_h2341251438`, `BurstCompilation_h2739774030`,
`BurstForceSafetyChecks_h202379155`, ...; macOS: the `com.unity3d.UnityEditor5.x` plist). Every sandbox editor on the
machine shares them under the one Windows account.

**Why (w1892, 2026-10-23, LothDesktop):** to get a release-like cost for a Burst job, the worker turned safety checks
off through `unity-bridge eval` in its own sandbox editor. With checks on, the job cost about 3x more, because every
NativeList index carries an AtomicSafetyHandle check (measured, unlocked editor). The switch then sat off for about
45 minutes on a machine with three editors. Any other sandbox editor reading it in that window ran its jobs and tests
without Burst's safety checks. A broken container access then passes silently instead of throwing.

**How to apply:**
- Never set a `BurstCompiler.Options` value from a script, eval or the menu on a machine other editors share. Time a
  job with checks on and compare old and new side by side in one run (a `[Category("Performance")]` test that holds a
  verbatim copy of the old job, e.g. the game repo's `SignalPropagationCostTest`). For release-player costs, time a
  release player under an exclusive ticket, or work on a one-slot timing machine.
- If one was flipped anyway, restore it and read the registry back:
  `(Get-Item 'HKCU:\Software\Unity Technologies\Unity Editor 5.x').GetValue('BurstSafetyChecks_h2341251438')` must be 1.
  Then name the window it was off in your report, so the workers whose tests ran then can judge them.
- The game repo's `NoTestSetsBurstOptionsGuardTest` keeps tests from setting these. An agent's eval is not covered, so
  this rule is the guard.
