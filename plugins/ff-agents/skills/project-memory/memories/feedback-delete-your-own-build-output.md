---
name: feedback-delete-your-own-build-output
description: "Ben 2026-10-05 (w459): a worker deletes its own large build output (player builds, bench/feel runs, recordings) once its PR merges or its request closes, keeping only the proofs its report links; name build folders after the request (Builds/w123-...) or the commit sha so FF Factory's clean-up can attribute them, since output it cannot attribute is only listed, never removed."
---

# Delete your own build output once your PR merges (Ben, 2026-10-05, w459)

**Rule.** When your PR merges or your request closes, delete the large output you made for it: player builds in
`Builds/` or `.nightly-builds/<sha>-win`, bench and feel runs, recordings and screenshot sets. Keep only the proofs
your report or PR links (and those belong in `specs/<NNN>/proofs/` or the review folder, not in `Builds/`).

**Name what you build so it can be attributed:** `Builds/w123-<what>` (the request id) or `Builds/<sha>-win` (the
commit). Not `Builds/perf`, `Builds/bench-before3`, `Builds/mdfog`.

**Why.** Disk filled up again and again with nobody's builds: w451 freed 42 GB of stale player builds on LothDesktop
after its D: fell to the 50 GB guard and blocked new editors, and on 2026-10-05 BEAST's sandboxes held about 39 GB in
`Builds/`. Ben: "please just update the harness to do this cleanup regularly so i dont have to keep telling you".
FF Factory now does it (w459, ff-factory PR #111, `server/staleOutput.ts`): once a day and when space is low it
removes output named after requests that are closed in the ledger, one-commit builds untouched for 2 days, and e2e
runs past 14 days. But output it cannot attribute to a request or a commit is only **listed, never removed**, so an
unnamed folder stays until a person deletes it. Anything holding a git repo is never removed either.

**How to apply.**
- Before your final report: `du -sh Builds/* .nightly-builds/* 2>/dev/null`, delete what is yours and no longer
  needed, and say in the report what you freed.
- Building for a request: put it under `Builds/w<id>-...`; building a commit for an e2e run: `<sha>-win` (as
  `scripts/nightly/build_player.sh` does).
- Never delete another worker's output in a shared sandbox; the clean-up attributes it, or lists it for a person.
- Related: [[m3-scratch-sweep-refused-delete-named-roots]] (delete by name, never a wildcard sweep).
