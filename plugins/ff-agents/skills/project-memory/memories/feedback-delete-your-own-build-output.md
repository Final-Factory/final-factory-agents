---
name: feedback-delete-your-own-build-output
description: "SUPERSEDED by w913 (2026-10-10): workers no longer delete their build output; put builds in $TMPDIR and the daemon removes them. Still true: output that is not in $TMPDIR and not attributed (request id or commit sha in the folder name) is only listed by FF Factory, never removed."
---

# Build output: leave it in $TMPDIR (Ben, 2026-10-05, w459; reversed by lothsahn, 2026-10-10, w913)

**Rule now.** Build player builds, bench and feel runs, recordings and screenshot sets under `$TMPDIR` and leave them; the
daemon removes them when your process ends ([workers do not clean up](../../evidence-gate/lessons/clean-up-after-yourself.md)).
Keep only the proofs your report links, in `specs/<NNN>/proofs/` or the review folder. A build that must live in a sandbox's
`Builds/` is named `Builds/w<id>-<what>` or `Builds/<sha>-win` so the daily pass can attribute it.

**History.** 2026-10-05 (w459): disk filled with nobody's builds; Ben: "please just update the harness to do this cleanup
regularly so i dont have to keep telling you". That became a daily pass (FF Factory `server/staleOutput.ts`) plus a rule that
workers delete their own output when their PR merges. 2026-10-10 (w913): "Random clean up commands take a lot of approvals"
(lothsahn), so the worker half was removed: the harness does it at the end of the session, and a delete under `$TMPDIR`
needs no approval. Related: [[m3-scratch-sweep-refused-delete-named-roots]] (delete by name, never a wildcard sweep, when a
clean-up request has to delete on a Mac over ssh).
