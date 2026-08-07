---
name: update-docs
description: Audit the repo's living documentation for staleness after a stretch of work and bring it up to date. Cross-checks every status/path/API claim against the ACTUAL code + git state (docs lie about their own currency), fans out read-only auditors over the doc set, then fixes the real drift and commits. Invoke when the user says "update the docs", "do a docs pass", "make sure the docs are up to date", "audit the docs", or after landing a batch of features that the reference docs should now reflect.
---

# Update docs: audit living documentation for staleness

After a run of work, the reference docs drift: features shipped but a status doc still says "TODO",
an index omits a doc that now exists, a path points at a renamed file. Your job is to find and fix
that drift. **The load-bearing principle: a doc is not evidence of its own currency.** A plan that
says "COMPLETE" and a feature list that says "active/open" can both be wrong — establish ground truth
from **code + git**, then judge the docs against it. (This repo has literally shipped features while
CLAUDE.md still listed them as "active".)

## Procedure

1. **Establish ground truth FIRST — from code and git, never from the docs themselves.**
   - What actually shipped: `git log --oneline` over the recent window; group by feature prefix.
     For each spec under `specs/`, check whether its tip commits are ancestors of `origin/<branch>`
     (`git merge-base --is-ancestor <sha> origin/develop`) — "DONE + committed" in a handoff does
     NOT mean pushed, and "NOT pushed" notes go stale the moment develop advances past them.
   - Confirm feature status by the code, not the prose: does the named class/system/fingerprint
     surface exist? did the audited defect actually get fixed? Build a short written ground-truth
     list (feature → done/pushed/proven, plus any genuinely-open items and the documented
     out-of-scope residuals). This list is what every auditor checks against — get it right.

2. **Inventory the docs and split living from historical.**
   - **Living docs** (must be accurate as current guidance — audit these): `docs/*.md`,
     `Documentation/*.md`, root `CLAUDE.md` / `README.md`, any component `README.md`, the
     **header comments of the root `run_*.sh` harness scripts** (they are runbook docs — the
     "expect the counter to print 0" class of claim lives there), and **Claude memory**
     (`MEMORY.md` + the per-fact memory files) — a stale memory misleads every future session.
   - **Historical / append-only** (do NOT rewrite; only touch if they present a CLOSED feature as
     current work AND are pointed to as the live handoff): `specs/*/plan.md|spec.md|tasks.md`
     session logs, `measurements.md`. These are dated records; superseding blocks are fine.
     ⚠️ Spec handoffs make **cross-lane claims**: feature X's handoff routinely carries "open
     elsewhere: <finding in lane Y>" notes, and design-decision bullets describe behavior that a
     later commit changed. When lane Y's finding is resolved, the stale claim usually lives in
     OTHER specs' handoffs too — annotate those hits (`RESOLVED <date>` / `SUPERSEDED <date>: …`
     markers, historical text kept verbatim), never just the owning spec.
   - **Skip**: `.claude/skills/*`, `.specify/templates/*`, generated files, `Library/`, `Packages/`.
   - **Highest staleness risk**, audit first: index/catalog docs (e.g.
     `Documentation/Determinism-Documentation-Index.md`), audit/priority docs (e.g.
     `Factory-Determinism-Audit.md`, any `*-Audit.md`), and status/feature lists in `CLAUDE.md`.

   - **Targeted claim sweep** (do this BEFORE and in addition to the group audits whenever the
     work batch fixed, resolved, or DEBUNKED a specific documented claim): grep the **entire
     tree's** `**/*.md` — including `specs/`, CLAUDE.md, and memory — for the claim's distinctive
     phrases and numbers (the finding's name, its counters like "254 reports / 0 verdicts", the
     superseded semantics like "once per (client, epoch)"). Group-scoped auditors miss these
     because the claim hides in files "belonging" to other lanes. Every hit gets dispositioned:
     fix (living doc), annotate (historical), or leave (other lane's still-true expectation —
     e.g. a control-run's "zero verdicts" PASS criterion is not the same claim).

3. **Fan out READ-ONLY auditors** (parallel `Agent` subagents; use a `Workflow` only if the user has
   opted into multi-agent orchestration). Split the doc set into coherent groups (~8–13 docs each).
   Give every auditor: (a) the ground-truth list from step 1 verbatim, (b) the explicit
   out-of-scope residuals ("do NOT flag these"), (c) this rubric. Auditors REPORT ONLY, never edit.

   **Report only concrete factual staleness:**
   - Status claims now wrong — "open/in-progress/TODO/planned/not yet/proposed/unfixed" for something
     now DONE (or "done" for something removed). Audit/index/priority docs are the top offenders.
   - References to files/classes/systems/methods/singletons/system-groups/menu-items that no longer
     exist or were renamed — **verify with grep/read before claiming**.
   - Facts contradicting current code (wrong paths, wrong API, wrong group/singleton/surface names,
     wrong Unity/package versions, wrong setup steps).
   - Index/catalog omissions (a doc that now exists but isn't listed) and broken cross-doc references.

   **Do NOT report:** prose/style nits, subjective phrasing, or the known out-of-scope residuals.
   Ask each auditor to distinguish a **dated snapshot** (fine as-is, maybe add a "resolved" note)
   from **wrong current guidance** (must fix), to mark confidence, and to return per finding:
   `file · approx line · short quote · why stale · CORRECT value · confidence`.

4. **Synthesize and fix — you keep quality control.** Don't blind-apply auditor findings; for each,
   re-verify the CORRECT value against the code yourself before editing (especially determinism /
   MP claims, where a subtly-wrong "fix" is worse than stale). Prefer surgical edits: flip a status,
   correct a path, add a missing index row, add a dated "RESOLVED <date>: …" note to a historical
   audit rather than rewriting it. If a doc turns out to be a genuinely orphaned/stale stray file,
   flag it to the user rather than silently deleting.

5. **Verify nothing else broke.** These are doc edits, so no compile/test is usually needed — but if
   you changed a code comment or a doc that a test or tool reads, re-check that. Run `git status` and
   make sure only intended files changed. Also run
   `python scripts/generate-ffauto-reference.py --check` — exit 1 means
   `docs/ffauto-command-reference.md` drifted from the runner's dispatch table; regenerate it
   (never hand-edit the generated doc) and include it in the docs commit.

6. **Commit (and push if the user asked) in coherent chunks.** Group by doc area with clear messages
   (`docs: correct stale <area> — <what>`). Per repo policy, push only when the user OKs; on a shared
   branch `git fetch` + rebase before every push. Update Claude memory if you learned a durable fact
   about where docs drift or a corrected premise.

7. **Report a tight disposition.** Summarize: what was stale and fixed, what was verified-current,
   what was deliberately left (dated snapshots, out-of-scope). Lead with the highest-impact
   corrections, not a file-by-file dump.

## Notes
- The number-one failure mode is trusting a doc's self-assessment. When a doc and the code disagree,
  the code wins — chase the code.
- Feature "status" is a git fact, not a prose fact: done-locally ≠ pushed, and stale "unpushed" notes
  mislead in the other direction once the branch advances.
- Scale the fan-out to the doc count. A handful of docs: audit inline. Dozens: parallel subagents.
  Reserve a `Workflow` for when the user explicitly opts into orchestration.
- Bias toward leaving historical/research docs as dated records (annotate, don't rewrite); bias
  toward aggressively fixing anything that presents itself as current guidance.
