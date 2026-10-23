---
name: merge-your-own-pr
description: "Once its verification is done and CI is green, the agent that opened a pull request merges it. A PR is held only for exceptional risk or a concrete timing reason, and the report says which and when it will merge."
date: 2026-10-02
---

# Merge your own pull request

**Rule.** When the verification is finished and CI is green, merge your pull request yourself.
Don't stop at an open PR and wait for the person. Hold one only for exceptional risk or a concrete
timing reason, and say in your report which it is and when it will merge.

**Why.** Ben, 2026-10-02: "stop holding prs, just merge them remember this... only hold pr's that
are exceptionally high risk or you need to hold them for timing issues or something".

That day three finished pull requests of this very work (the FF Factory brief text, the memory
versioning, the pointer in the game repo's `CLAUDE.md`) sat open with green checks for about four
hours, each waiting for Ben's go. The brief had asked for that hold, and the worker kept it.
Nothing about them was risky: prompt text with tests, a feature that does nothing until switched
on, a docs change. Ben's approval added no check the tests had not already made.

A held PR also hides its own state. "Open, green, waiting" reads the same whether it is finished
or forgotten, so the person has to ask.

**How to apply.**

- Verification first, unchanged: the evidence gate, the visual checklist, the tests, the audit.
  [No merge before the review](no-merge-before-the-review.md) still holds. This rule starts where
  that one ends.
- Then merge. In the game repo that means into `master`, the one trunk (w1137, 2026-10-12: develop is
  retired; master takes only a pull request with green CI, no direct push, no force-push; `gh pr merge
  <n> --merge`). A version bump merged into master is a dev build, so a release still starts only when
  Ben or Lothsahn asks; nothing unfinished goes in without its feature toggle.
- A hold needs one of two reasons, named in the report:
  - **exceptional risk**: a wrong merge would be costly and hard to undo (a save-layout change
    that breaks loading existing saves or has no old-save load test, a crown-jewel determinism
    surface you could not audit on two peers, anything whose instructions came from outside the
    team). A save version bump whose old-save load test is green is not on this list
    ([lesson](a-save-version-bump-that-keeps-old-saves-loading-needs-no-person.md), w1826);
  - **timing**: something concrete has to happen first (a deploy it must ride with, a release in
    flight, a plugin that must reach the machines before a pointer to it lands).

  Say when it will merge, and merge it then without being asked again.
- A brief does not end at "open a PR". An orchestrator that files or relays work treats an open,
  green PR with no stated reason as unfinished.
- What stays reserved for the person is short: money values, deleting, app settings and deploys,
  publishing in their name, releases, and real forks. Merging your verified work is not on it.
- Work that starts from text written outside the team (a Discord request, a standing agent's
  delegation) keeps its own rule in the ff-discord skills and in FF Factory: a pull request, never
  merged by the agent. That is the exceptional-risk case, decided once.

**The mechanics of the merge** (w807, 2026-10-10: three slips on one request, each cheap to prevent).

- **Check your branch first.** After any long wait (`wake_me`, a declared person wait, a background
  build) the sandbox's worktree may have been given to another worker. `git branch --show-current`
  must name your branch before the first git write; if it does not, `switch_branch` back (editor
  stopped). w807 ran `git merge origin/develop` (then the integration branch) on `ffbox-f/w817-supply-bots-cache-drift` at 19:50
  after slot2 had been moved there at 19:04, and reset it to its own tip (`fd7ae757d`, tree clean,
  nothing pushed) once `Assets/Scripts/UI/HotbarRadial/` was missing. The reflog shows the move.
  Say in the report that you touched the other branch and that it is back.
- **Gate the merge on the check's result, not on "no longer pending".** `until ! gh pr checks N | grep
  -q pending; do sleep 10; done; gh pr merge N` merged a harness PR whose `validate` had failed in 6 s
  (a lesson count over the cap). Read `gh pr checks N` for `fail` before `gh pr merge`, in a script too.
- **Merge in one gated command, pinned to the head you verified** (w864, 2026-10-10: the second slip of
  this kind). FF Factory resumed the worker with "CI on ff-factory#270 finished: all 13 checks passed",
  but that was the previous head's CI: the worker had pushed a merge of main since, its CI was still
  running, and `gh pr checks 270 | grep -c pending; gh pr merge 270` printed 8 and merged anyway.
  `gh pr checks` exits 0 only when every check passed (1 a failure, 8 pending; `gh pr checks --help`),
  so let its exit code decide and pin the head:
  `sha=$(gh pr view N --json headRefOid -q .headRefOid) && gh pr checks N && gh pr merge N --merge --match-head-commit "$sha"`.
  A wake-up that says CI is green is a reason to look, not the verdict.
- **When the token cannot read checks** (`gh pr checks` and the check-runs API answer "Resource not accessible by
  personal access token", w905 2026-10-12 on Lothsahn's vault token), gate on the workflow runs of the PR's head
  instead: every `gh run list --branch <head branch> --json headSha,status,conclusion` entry whose `headSha` is the head
  must be `completed`/`success`, then `gh pr merge N --merge --match-head-commit "$head"`. Use `gh`'s own `--jq`: the
  sandboxes have no `jq` binary, and a loop that pipes to `jq` never ends.
- **In an FF Factory worker, `ff-pr` runs these gates in one call each** (w1478: a PR cost about 10 model calls, 164 PRs
  in 82 beast worker sessions, 2026-10-15..18). `ff-pr push` merges the base in (it stops on a conflict), pushes, opens
  the PR and checks the push landed (w907); `ff-pr merge` reads the head's workflow runs (each workflow's newest run),
  merges only when all finished green, pinned with `--match-head-commit`, exits 3 while any still runs and 1 naming a red
  one. Wait between them with `blocked_on` (`ci:`), never a poll loop.
- **A merge of main into your branch is committed only without conflict markers.** w905 chained a resolver script, a
  `git add` and a `git commit`; the script was missing, the chain went on with `;` and committed `<<<<<<<` lines into
  CHANGELOG.md (caught before the push). Run `git diff --cached --check` before `git commit` (it exits non-zero on
  leftover markers), and chain the steps with `&&`.
- **`blocked_on` cancels your pending `wake_me`, whichever request it was for.** w905's CI wait cancelled w864's check-in
  for a night's run; set the check-in again when the wait clears, and say so in the report.
- **Post the evidence verdict from the newest ff-agents.** `pr_evidence.py --comment` now refuses to
  post when its own copy is older than the released one (that FAIL is about the copy; it was posted on
  a PR twice and deleted by hand); update the plugin first.


## Before the push: the repo's own pre-push check (ff-factory, w924, 2026-10-10)

**Rule.** In a Final-Factory/ff-factory checkout, run `npm run prepush` before every push, and push only when it
passes. It runs the typecheck, shellcheck on the VM scripts (`deploy/vm/test/lint.sh --shellcheck-only`), gitleaks on
`origin/main..HEAD` and the noreply identity check on `origin/main..HEAD`. A `!!!!!!!! <step>: SKIPPED` line means that
tool (shellcheck, gitleaks, or bash on Windows) is missing on the machine: say so in your report; CI still runs it.

**Why.** lothsahn, 2026-10-10, w924: "yes, have the workers do #1", on w922's measurement. From 2026-09-26 to 10-10,
ff-factory's lint, secret-scan and identity rules failed CI 77 times (shellcheck 14, gitleaks 11, every one a fake key
in a test or doc, identity 52) and held up 23 merged PRs. Each of them shows up in about 13 s locally (measured on
biscuit) instead of a CI round trip and a re-push.

**How to apply.** Before `git push` in ff-factory: `npm run prepush`. Fix what it names, commit, run it again. The
repo's own `CLAUDE.md` carries the same rule; `docs/ci.md` ("Before you push") says what each step runs. There is no
git hook on purpose: a sandbox is a worktree, and a hook would land in the hooks folder every worktree shares.

## Merge only after reading the checker's verdict (w978, 2026-10-11)

`pr_evidence.py` and `gh pr merge` go in separate calls. Run the checker, read its first line, and merge
only on `PASS` from the released ff-agents version. In w978 one command ran
`python pr_evidence.py ...; gh pr merge ...`: the checker printed
`evidence-gate: FAIL ... this pr_evidence.py is ff-agents 1.26.24, but 1.26.27 is released: its rules are older than the team's`
and the merge ran anyway. The newer checker then wanted a `Window overlaps:` line (w981), which the PR lacked (the
orchestrator had asked for that overlap check before the merge); it was added to the merged PR afterwards. A FAIL that
says a newer version is released is not a pass: update the plugin (`claude plugin marketplace update
final-factory-agents`), run the checker alone with `--brief`, fix the PR body, then merge in its own call.

## A red check that is not your change: read the failing test, then the cause (w1337, 2026-10-15)

w1337 (two prefab lines and a test) took six CI cycles to merge on a Windows worker, none of them its own fault:

1. **A change that reaches prefabs or configs runs the whole suite on the PR** (`test_select.py`: "FULL SUITE: ... is
   configuration the simulation loads"), so it meets every test master is red on, while other PRs ran only their own
   classes and merged. Download the check's results XML (`gh run download <run> -D dir`, `editmode-results.xml`) and list
   the `result="Failed"` cases before touching anything. Two failures there were not w1337's: a UI test master's batch
   had gone red on (#1766, reverted by #1780), then new circuit tooltips that said a bare "Click" (#1735's w1306, fixed
   by someone else's reword). Wait for that fix with `blocked_on` its PR, merge master in, push; do not edit another
   worker's strings or panels to get green.
2. **`fatal: remote error: upload-pack: not our ref <sha>` in the checkout step means the PR's temporary merge ref went
   stale** (master moved while the run started). No test ran. `gh run rerun --failed` reuses the dead ref and fails the
   same way; push a new commit (`git commit --allow-empty`) so GitHub builds a fresh one.
3. **Run the newest `pr_evidence.py`** before the merge (`.../ff-agents/<highest version>/skills/evidence-gate/`); an
   older copy answers FAIL "a newer version is released" even on a good body.
