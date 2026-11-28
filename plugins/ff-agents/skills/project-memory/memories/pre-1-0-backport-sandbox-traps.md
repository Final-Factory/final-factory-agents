# Backporting into pre-1.0 from a sandbox: three traps

**Request:** w6628 (port the developer knock into 0.50, PR #4456 into `pre-1.0`), 2026-11-27/28, m5/slot2.

## 1. The editor stalls on the private KNN git package

A sandbox switched to a `pre-1.0` branch opened its editor and sat in package resolution with
`could not read Username` for the private `com.akb.knn` git dependency: the fenced editor has no
git credentials for it.

Fix that worked:

1. `gh repo clone <the KNN repo named in Packages/manifest.json> "$TMPDIR/knn"` (gh has the token).
2. `git -C "$TMPDIR/knn" checkout <hash pinned in Packages/packages-lock.json>` (375be6b9ffb0 on 0.50).
3. Copy it into `Packages/com.akb.knn` (an embedded package, untracked) and let the editor resolve.
4. Before committing: remove `Packages/com.akb.knn` and `git checkout -- Packages/packages-lock.json`
   (the embed rewrites the lock entry). `git status` must show neither.

## 2. pre-1.0's `scripts/unity-bridge.py` is older

It has no `run-tests` or `wait-ready` verbs. Use the generic call:
`python3 scripts/unity-bridge.py call --project-path "$PWD" run_tests '{"assembly_names":["FFEditorTests"],"test_names":[...],"init_timeout":300000}'`.
A first run of ~900 classes hit a 120000 init timeout; 300000 was enough.
Also `scripts/test_select.py --base origin/pre-1.0` (not master) picks the classes.

## 3. A UI backport with waived stills cannot be merged by an agent

The merge guard (FF Factory `guard.ts` `makeGhEvidence`, `evidenceGate.ts` `evidenceVerdict`) passes
only when `pr_evidence.py` exits 0, and `pr_evidence.py` has no owner-waiver route: a `Kind: ui` PR
needs `Built player: yes`, Clips, Looked and the whole unity-ui census set. lothsahn waived the
two-machine stills ("Skip the two machine test.  I'll test it manually"); the check still failed
and both `ff-pr merge` and `gh pr merge` were refused.

Do not write a false "No visible change" row to get through. Record the waiver in the Evidence
section, quote the owner, and ask the owner (waiting_on_person) to merge it on GitHub himself;
lothsahn did for #4456 (merge 212607bc76).
