# w741: a harness that improves itself — design (deep-think, 2026-10-09)

Labels: **PROVED** (command or file:line given), **SOURCED** (spot-checked external), **HYPOTHESIS**, **UNKNOWN**.
`ffa/` = final-factory-agents, `fff/` = FF Factory, `game/` = slot2. "HEAD" = committed, not drafts.

## 0. Verdict

**Mis-scoped.** The bottleneck is not that agents fail to write lessons. Three things are:

- workers run stale tools;
- prose that already existed did not change behaviour;
- a repeated correction is visible only to the orchestrator.

So: ship a one-line learning step, but put the weight on checks at DONE and at merge, an orchestrator correction tally, and tool freshness.

## 1. Measured (PROVED)

- **P1 Stale tools.** This Mac (m5) has ff-agents **1.20.41** installed (`~/.claude/plugins/installed_plugins.json`, updated 10-07 15:05Z). Master and the marketplace clone are at 1.22.1.
  - The w712 worker found pr_evidence with `ls …/ff-agents/*/skills/evidence-gate/pr_evidence.py | tail -1` (transcript `slot3/1bd3d986`, 22:44Z). A lexical sort picks **1.20.6**, from 10-02 (re-run now; nothing newer has been installed since 10-07).
  - Its PASSes on #1272 and #1277 both fail today's tool (`pr_evidence.py --pr 1277 --offline`).
  - Cause: `merge.md:91` says `<this skill's base directory>`, but no worker invokes evidence-gate as a Skill (P3), so none has that path.
- **P2 Prose existed and did not bite.** `project-memory/memories/ui-screenshot-worst-case-before-done.md:19` has said "every HUD element that can be visible at the same time, together" since 09-22 (2b19a63). `drive-game/SKILL.md:214-216` points to it, and UI workers loaded drive-game (sessions 798947c5, 1bd3d986). The w644/w733 "rest of the screen" misses happened anyway.
- **P3 What workers actually read.** 22 local worker transcripts (`the m5 sandboxes slot1-3 (`~/.claude/projects/`)`, 10-07..10-09):
  - pr_evidence ran in 15, and a checklist was read in 13.
  - Lesson files were read in 3, only by sessions writing lessons.
  - evidence-gate and project-memory were never invoked as Skills.
- **P4 Repeats cross requests.** The Deck corrections fell on different sessions (3973fea4, 311af22c, 1bd3d986, 798947c5, then 46458b0f elsewhere). The 22 sessions held 16 person follow-ups and no second same-kind correction inside one session.
- **P5 w732.** The request as filed (798947c5) quotes Ben: "the slide out button panels still intersect with the hotbar". The orchestrator made that "Done when: … 0 overlapping HUD element rects".
  - Commit 03ada4bac predates the w733 rule: `git merge-base --is-ancestor 500ccf17c 03ada4bac` is false.
  - `specs/w732-hud-corner/HANDOFF.md:47-48`: 1.22.0 was not installed on the m5.
  - The w733 lesson encodes the same reading and would enforce it next time.
- **P6 No review gate on harness changes.** Harness master shows `protected:false` (`gh api`). 80 of 92 first-parent commits since 09-25 are direct pushes, and `publish-skills/SKILL.md:125-126` says "commit, and push".
- **P7 What CI checks.** validate.yml runs pr_evidence's tests (`:81-82`) and a dead-link check (`:84`), not `unity-ui/tests`.
- **P8 Posted verdicts.** Since 10-02 there are 213 posted verdicts on 179 PRs (205 PASS, 8 FAIL); 388 PRs merged. Workers post only once they pass, so these comments cannot count catches.
- **P9 Code references.** 3 of 247 code references in project-memory are gone at game HEAD (`git grep -w` per symbol; an earlier run with a broken regex said 194).
- **P10 Lesson count.** 26 lessons on HEAD against the "about twenty" cap (`evidence-gate/SKILL.md:208`). Some lessons were not filed as "Harness:" requests: w587's brief asked for one; w503's worker chose to publish one (779e5cc).

## 2. Design

| Question | Pick | Why (alternatives rejected) |
|---|---|---|
| **Trigger** | A person's correction or reopen is the enforced trigger. Every DONE carries one `Learned:` line. A cluster is concrete: `git log --since=14.days -- <your files>` shows another fix. | Self-reflection without outside feedback is weak (Huang 2310.01798, not re-fetched). Compiled corrections cut repeats (TRACE 2606.13174, SOURCED, simulated users; 2607.13091, SOURCED, 11 sessions). The ledger already knows reopens (`ledgerRules.ts:127` `afterReopen`). |
| **Second correction** | The **orchestrator** counts. One memory line per correction: date, wNNN, kind, **verbatim** words. On the 2nd of a kind it files "Harness: <kind>" in that turn, quoting both. | Workers rarely see the first one (P4). Memory writes happen only in the person's own turn (`docs/orchestrators.md` HEAD:713-716), so this is injection-safe. |
| **Writer** | The worker writes small items: a checklist line, a doc beside the code, a project-memory trap. A dedicated request builds tool checks. | Tool checks need fixtures and tests. The existing ones came from w438, w718 and w733. |
| **Reviewer** | A CI shape gate and a count cap, plus the person. The orchestrator relays each harness-changing `Learned:` line in one line, so the person can veto. | Nobody reviews today (P6). An admission gate matters (Voyager's ablation and SkillsBench, per brief). A person would have stopped P5. |
| **Retrieval** | Checks at merge and at DONE first, then the brief, then grep. Game and code facts go in the **game repo, beside the code** (`Documentation/<system>.md`, `docs/HowToPlay.md`). project-memory is for tool and environment traps. | Lesson indexes go unread (P3). The brief works: after the w712 reopen brief, #1283 met 1.21's UI lines. Docs in the game repo change in the same PR as the code. |
| **Did it help** | Per-rule catches: pr_evidence's PASS comment lists the rules that failed first. Recurrence of a kind in the orchestrator's tally. | Posted verdicts hide catches (P8). No stable task set for A/B runs. |
| **Retirement** | The cap enforced in CI at today's count: an addition merges or retires one (Mem0-style UPDATE over ADD). A rule a tool enforces shrinks to its "why". Weekly: the P9 probe and `/doctor prompt-audit <path>` (Claude Code memory docs, SOURCED). | The cap exists only in prose (P10). |
| **Contradiction** | The person's latest verbatim words beat a lesson or a check. The worker follows them, says so, and edits the lesson in place. An override quotes the person, never a paraphrase. | Claude Code docs: conflicting rules are resolved "arbitrarily" (SOURCED). |

## 3. (A) Ship now

1. **fff `server/work.ts:351` `doneRule`.** One sentence: each `DONE:` report carries `Learned: <path or PR>` or `Learned: nothing new`. It replaces `LEARN_RULES`.
2. **fff `server/ledgerRules.ts:345` `doneProblem`,** with a test.
   - Refuse a DONE without a `Learned:` line.
   - On a request a person reopened, also refuse `nothing new`; accept a path, a PR, or `no check possible: <why>`.
   - It merges now; it goes live at Lothsahn's next deploy.
3. **fff `personalBrief`.**
   - The correction tally, verbatim.
   - On the 2nd of a kind, file the harness work in that turn, unless an open request already covers it.
   - Name the checklist for the kind of change in each brief.
   - Quote the person and label your own reading; no metric without their words (P5).
   - Relay harness `Learned:` lines.
4. **ffa `evidence-gate/SKILL.md:204-211`.** Rewrite as the protocol:
   - triggers: a correction or reopen, a failed check, 3+ redos, a cluster;
   - homes, strongest first: tool, checklist line, the doc where you looked first, lesson;
   - search, then UPDATE rather than ADD;
   - verbatim words; the latest correction wins.
5. **ffa lessons.** Extend `lessons-belong-in-the-harness-repo.md` (`:30-31` already says to publish in the same session) rather than add a 27th file.
6. **ffa `validate.yml`.**
   - Run `unity-ui/tests`.
   - Check lesson shape: a frontmatter date, a `w\d+` or `#\d+` in "Why", an index line, a checklist or tool link.
   - Fail above 26 lessons.
7. **ffa `merge.md:91` and fff `EVIDENCE_RULES`.** One exact command for the released pr_evidence: the marketplace clone, or `sort -V`. Never `ls | tail -1` (P1).
8. **ffa `publish-skills/SKILL.md:125`.** "Open a PR, merge when green", if PRs are now the rule (P6).

## 4. (B) Follow-ups

1. **Freshness (highest value).**
   - The FF Factory daemon runs `claude plugin update ff-agents@final-factory-agents` before each worker start, and prunes cache versions older than the installed one.
   - The brief states the version.
   - Cost: daemon code plus Lothsahn's deploy.
2. **Game CI runs pr_evidence on every PR.** The w733 lesson HEAD:71-72 says it is written and waits for a token that may push workflow files.
3. **Protect harness master and require validate.** A settings change: Ben's call.
4. **pr_evidence records rules that failed before PASS,** plus a weekly `gh api` count per rule.
5. **Weekly orchestrator timer.** `search_transcripts` for corrections, cluster them, file "Harness:" requests (an ExpeL/Letta-style sweep).
6. **Scheduled staleness job:** P9 plus a prompt audit. It needs a game checkout.
7. **Retire or re-trigger `game/docs/Lessons-Index.md`.** Last row 09-20; its trigger, "spec closed", stopped firing when work moved to wNNN requests.

## 5. Critique of the drafts

- **`learn-before-done.md`.**
  - It is a 27th lesson duplicating `lessons-belong…:30-31` and the publish-skills description.
  - Triggers (a) "several tries" and (d) "a fact" fire on most requests, which contradicts `:58` "most end nothing new".
  - (c) gives no way to detect a cluster.
  - The "Why" (`:32-33`) misses P2: the rule existed and failed.
  - Nobody will maintain "Caught:" lines (each needs a harness PR); use B4.
- **`done.md`.**
  - Item 7 repeats the lesson; keep one line and a link.
  - Item 2 (w704) is good: both #1263 fix commits are ancestors of 8bba83e65.
- **`LEARN_RULES`** adds about 1,000 characters to every worker turn. It cannot see a second correction (P4) and nothing enforces it. A1 and A2 do its job.
- **The personalBrief bullet.**
  - It has no memory tally, so the first correction is forgotten after a compaction.
  - "Tell the worker … harness step applies" risks duplicate harness PRs: name one owner.
- **byDesign entry.** Its `who` is "the worker's words", which breaks its own "the person's own correction" rule. Get Ben's verbatim words first.
- **Not covered by any draft:** freshness (P1), the review gate (P6), the cap (P10), CI not running the unity-ui tests (P7).

## 6. Could not determine: cheap probes

- Ben's verbatim w732 correction: `read_work w732` log at 03:27-03:28Z.
- Whether his orchestrator memory already logged the Deck corrections: list `data/orchestrator-memory/person-<ben>/` on the portal host.
- Installed versions on BEAST and LothDesktop: their `installed_plugins.json`.
- How many lessons were self-initiated: grep ledger briefs for "lesson|harness".
- Spot-checked: ACE (the abstract confirms brevity bias and collapse; no counters in it), TRACE, 2602.11988, 2607.13091, the Claude Code memory docs. Not re-fetched: Voyager, ExpeL, SkillsBench, Skill Issue. The "20-50 tasks" quote was not found verbatim.

## 7. Where the brief was wrong

- "A lesson pushed an agent wrong": false for 03ada4bac (P5).
- "validate.yml checks versions/JSON only": false (P7).
- "PRs only": not enforced (P6).
- Ask (2) as a worker trigger rarely fires (P4).
- The hypothesis "prose is rarely read; tools change behaviour" is **supported** (P2, P3), with one refinement: prose works inside the brief, at the moment of action (#1283).

## 8. What w741 shipped (the parent's adjudication, 2026-10-09)

Adopted: the `Learned:` line in FF Factory's DONE rule (`server/work.ts` `doneRule`) and refused by the ledger when
missing (`server/ledgerRules.ts` `learnedProblem`, live DONEs only, so stored DONEs from before the deploy still close),
`nothing new` refused on a reopened request; the orchestrator's correction tally (`personalBrief`: verbatim, by kind,
filed on the second, the person's words quoted and the orchestrator's own reading labelled in every brief); the
lesson folded into `lessons-belong-in-the-harness-repo.md` (no 27th file); the protocol in `SKILL.md` "Adding a lesson";
CI running `unity-ui/tests` and `scripts/check_lessons.py` (shape, index, incident, cap 26); one `sort -V` command for
the released `pr_evidence.py` (`checklists/merge.md`) and its stale message; `publish-skills` step 4 as a PR.
Dropped: the 1,000-character `LEARN_RULES` block in every worker brief (A1/A2 do its job); "Caught:" lines (B4 instead).
Kept from the drafts: done.md item 2 (the brief's Done, item by item; w704). The `byDesign` entry still carries the
w732 worker's paraphrase: replace it with Ben's verbatim words when w732's PR quotes them.

Follow-up added: `claude plugin eval` (Claude Code's own eval runner: cases under `evals/`, scored with graders, with a
no-plugin baseline arm) is the natural home for B4/B5's "did it help": one case per past miss (#1251's tour, #1272's
navy, w704's DONE on unit tests), run before and after a harness change.
