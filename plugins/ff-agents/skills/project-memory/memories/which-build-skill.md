# Which build skill

A recurring harness confusion: agents reached for `ci-release` when Ben asked for "a build" to test
multiplayer with friends. `ci-release` publishes to the PUBLIC/default Steam app/branch (production
settings strip `FF_ENABLE_MULTIPLAYER_BUILD`, so multiplayer is hidden for whoever gets that build) —
it can never produce a build anyone can playtest multiplayer with.

Decision table:

- **Multiplayer / testers / friends / closed beta** → [[mp-beta-deploy]] (builds on the M5, uploads to
  the password-protected `multiplayer-closed-beta` Steam branch).
- **An actual explicit public release** (Ben asks in those terms — "cut a public release on
  master/develop", "push live to Steam") → [[ci-release]] (ffbox CI, uploads to the PUBLIC/default
  Steam app — master or develop are BOTH public there, there is no quiet/internal mode).
- **Local test players only, no real build needed** → `honest-coop-play` /
  `LocalMultiplayerVerificationBuild`.

**Emphatic (Ben, 2026-09-25): `ci-release` must NEVER be used to get someone "a build" for testing.**
It is public-Steam-only and requires an explicit ask for a public release, in those terms — not a
generic "make a build" request, no matter who it's for.
