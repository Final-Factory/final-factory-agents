# Never run the whole EditMode suite locally; FULL SUITE means the merge gate's list (w4735, 2026-11-19)

**The rule.** When the game repo's `python scripts/test_select.py` answers FULL SUITE, run the list it prints: the merge
gate's list, the same as `python .github/scripts/merge-gate-tests.py --base origin/master --local --names-out "$TMPDIR/gate.txt"` (the
depth-1 selection plus every repo-wide Guard, Census, TableRows and Lifecycle class and the Localization tests). Never
run all of `FFEditorTests` locally unless a person asks for it. The pull request's `Test in editmode` check (which runs
the whole suite itself for a framework, `Packages/` or `ProjectSettings/` change) and `master-batch.yml`'s whole-suite
run after the merge, which bisects a red batch to its pull request and reverts it, cover the rest.

**Why.** Report r290 (w4611, why station multi-select w4488 took so long) measured about 2.7 h of one feature's build
day lost to five local whole-suite runs, 37 to 50 min each on lothdesktop, and four of the five failed on unrelated
timing or environment tests. lothsahn filed the fix at high (w4735). The old rule (w1156, 2026-10-13: "run the whole
fast suite locally" on FULL SUITE) dated from when the gate ran only guards; the gate has since selected the asset
readers (w1533) and every repo-wide check (w1180).

**Why w4488 got FULL SUITE at all.** Its UI diffs (#3784, #3817) had no framework file: the local selection grew past
the 60% cut-off (72% and 81% of the suite's CI time) because (1) a new constant in `Messages.cs`/`Labels.cs` selected
every test naming `Messages` or `Labels`, about 1,500 classes through their users; (2) nested types with common names
(`StationGroupPanel.Row`, `StationGroupOrders.Order`, `StationRouteArrow.Route`) matched every test using the word;
(3) the localization tables' folder name `Localization` matched 169 test classes through the namespace. w4735 fixed
all three in the selector (46% and 40% after) with tests in `scripts/tests/test_test_select.py`.

**How to apply.** Copy the `test_names` the selector prints into `run_tests`. A red test in that list that is a timing
test not tagged `[Category("Performance")]` is mis-tagged: fix the tag, never the threshold.
