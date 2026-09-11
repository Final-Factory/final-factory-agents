---
name: cross-platform-leg-staging-and-the-movers-position-residual
description: "How to stage and launch a Windows built host on BEAST from the Mac (tar.gz+scp, the nohup form that starts), and what the cross-platform movers fork is after mirrored Velocity/Heading stopped folding: one-ULP POSITION flips through Quantize, sticky — a fingerprint-scope call for Ben."
---

# Cross-platform leg staging, and the movers position residual (2026-09-11, 069)

**Staging a Windows build to BEAST (works):** on the Mac
`COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -cf - <buildDir> | gzip -1 > win.tar.gz`,
`scp` it, then in Git-bash `tar -xzf … --strip-components=1 -C <dst>` and run `make_manifest.py`
ON BEAST (the manifest's `artifactPath` is the BEAST path; the adapter checks
`--expected-source-revision` against it, so a dirty-tree diagnostic build can carry the HEAD
sha). What does NOT work: a tar pipe over ssh into Git-bash (`tar: -: Cannot read: Bad
address`), and `ssh -f beast '… nohup bash x.sh &'` (the host never starts). Launch with
`ssh beast '"C:\Program Files\Git\bin\bash.exe" -lc "cd … && (nohup bash ./x.sh > x.out 2>&1 &) ; sleep 3; cat <root>/status.txt"'`
in the background (it may hang the ssh session; the host runs anyway). Watch
`<build>/.ff-local-automation-status.json` Phase: the built host reaches
`waiting-host-peers-connected` ~20 s after launch, then start the editor client
(`.ff-local-automation.json`, Role Client); the host exits ~100 s after the join with a report
under `AppData/LocalLow/Never Games/finalfactory/DeterminismAudit/`.

**The residual after `c6754164e`** (mirrored rails' Velocity/Heading no longer fold): RED xplat5
forked `movers` from e1 hb1 on every heartbeat; xplat7/xplat8 agree for most heartbeats and fork
in windows. With every rail dumped (temporary `MaxMoverDetailRecords = 4096`; the
`CombatMoverFingerprintWireTest` quartet fails at 4096 by design — restore 64 before commit) the
diverging heartbeats each hold ONE fleet rail (flags `0x210`/`0x310`/`0x390` = Mirrored |
CollidesWithWorld | avoidance bits, `FlagInitialized` clear) whose `pos` differs by exactly one
float ULP through `CombatRailProvisioning.Quantize` — a plain `(fp)float` cast, so 2^21 raw on
x/z at ~2^11 magnitude, 8192 raw on y — plus ~14 rails of now-unfolded `v`/`h` noise. A flip
is sticky (rail 02C7 e2 hb51→53), so a verdict → recovery still follows, later than before. Not
frame cadence (the mirror reads `LocalTransform`), not editor-vs-editor (rejoin11 clean).
Whether `Position` also stops folding for mirrored rails is Ben's fingerprint-scope call
(`Documentation/Crown-Jewel-Surfaces.md`), never a silent narrowing; the structural fix is the
055 fp-rail migration. Method that got here: `movers_groupdiff.py` (which field group), then
raw values, then flags — before any theory.
