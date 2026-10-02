---
name: lessons-belong-in-the-harness-repo
description: "A lesson about how to work goes into the version-controlled harness, where every agent and every fork gets it. A memory folder on one machine, or an orchestrator's memory, holds a pointer at most."
date: 2026-10-02
---

# Lessons belong in the harness repo

**Rule.** A rule worth keeping is written into a harness repo by pull request. A private memory
folder is a pointer to it, and a place for one person's preferences.

**Why.** Ben, 2026-10-02: "Your memory should be stored in this repos harness so it is enshrined
forever for anyone who forks it." His orchestrator had learned four rules that week (evidence
before recommending, visual fixes verified before calling them done, paste text plain, and this
one) and could only write them to `data/orchestrator-memory/` in the FF Factory install on one
machine. No worker, no other orchestrator and no fork could read them there.

**Where each kind lives.**

| Kind | Home |
|---|---|
| How to decide, verify and report | this skill: `lessons/`, `checklists/` |
| One system's traps (Unity, ECS, a tool) | the `project-memory` skill |
| Marketing checklists and lessons | the ff-marketing repo, `lessons/` |
| Rules the prompts state themselves | ff-factory, `server/agents.ts` |
| One person's preferences | their orchestrator's memory folder; never in a public repo |

**How to apply.**

- A worker that learns a durable lesson publishes it in the same session (`publish-skills`),
  with the checklist line or tool check that would have caught the miss.
- An orchestrator cannot write to a repo. It keeps a one-line pointer in its memory, files a
  request for the lesson, and tells its person. A worker opens the pull request, and the person
  approves it.
- Keep names, secrets and private details out of a lesson. Say what happened, with dates and
  pull request numbers, and nothing a public reader should not see.
- Don't write lessons to `~/.claude/projects/*/memory/`. They stay on that machine.
