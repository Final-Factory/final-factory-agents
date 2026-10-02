---
description: When a fix must be proven in a macOS built player before merge, build it on the M3's nightly lab clone with build_player.sh (8 min) and run the paired audit there; put the clone back. CI builds Mac players only on a release.
---

# A Mac built player of a branch: the M3 lab clone (w169, 2026-10-01)

- CI builds osx players only on a version bump (`main.yml`). For a pre-merge Mac proof use the nightly
  lab clone on the M3: `~/nevergames/ff-nightly/FinalFactory` (detached HEAD, builds cached in
  `../builds/<sha>-mac/player/finalfactory.app`). Check it is idle first: no Unity or `ffnightly`
  process, and the nightly runs at 01:30.
- `git fetch origin <branch> && git checkout --detach <sha>`, then
  `bash scripts/nightly/build_player.sh <clone> <40-hex sha> mac <clone>/../builds`. 8 minutes on the M3
  against 14 on BEAST. Then `FF_BUILD_DIR=<...>/player FF_LOG_DIR=<...> ./scripts/audit/run_build_multiplayer_audit.sh --skip-build ...`
  in that clone; both players run on the M3 through its slot pool.
- Afterwards: check the previous sha out again, delete your `builds/<sha>-mac` and run folders (the disk
  is at 93 %).
- Two sandbox hooks get in the way from BEAST: a remote command containing `git checkout` is refused
  while YOUR sandbox editor runs (stop it first; you stop it for the Windows build anyway), and any
  command naming Ben's own clone path is refused outright. The lab clone path is fine.
- The lab players are development builds (Mono and Burst, the shipped backend), not the Steam release
  configuration: say so in the PR.
