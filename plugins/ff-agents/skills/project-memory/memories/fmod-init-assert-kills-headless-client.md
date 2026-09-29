---
name: fmod-init-assert-kills-headless-client
description: A headless built client sometimes dies at startup on the FMOD assert 'gSystemInitCount == 0' before loading anything; the paired audit then fails with missing reports. A startup flake on any build - re-run it.
---

# FMOD startup assert kills a headless client: re-run

087, 2026-09-28, BEAST: two of about fifteen headless (`-batchmode -nographics`) client launches,
one on each of two different builds, stopped logging right after

```
[FMOD] assert : assertion: 'gSystemInitCount == 0' failed
```

before the client connected. The host ran on alone, and the audit script reported
`ERROR: missing report(s) — host='none' client='none'` (driver rc=3). The same build passed
the runs just before and after, and a re-run passed.

- Check the client's `Client.log` tail for the assert before blaming the change under test.
- It happened when several players started within seconds of each other. Staggering launches by a
  few seconds is cheap, but not proven to help.

Related: [[beast-shared-machine-perf-ab-side-by-side]].
