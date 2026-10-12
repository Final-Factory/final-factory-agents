# Which build skill

master's players ship multiplayer (`FF_ENABLE_MULTIPLAYER_BUILD` in ProjectSettings, FinalFactory
#613/#614). Since w1137 (2026-10-12) master is the one trunk and develop is retired. ffbox sets a build's
main app live as it uploads (`release_lane.SETLIVE = {("master", "main"): ("development",)}`): a version
bump merged into master lands on **`development`**. Nothing sets `pre-release` or the default (public)
branch: Ben or Lothsahn move them by hand; agents never move a Steam branch and never ask Ben to.

Decision table:

| Ask | Skill | Result |
|---|---|---|
| A new dev / testers / friends build | [[ci-release]] (a version bump merged into **master**) | ffbox builds the players; main goes live on `development` by itself, demo is uploaded with nothing live |
| A release to players | not an agent's step | Ben or Lothsahn move `pre-release` or the default branch by hand on the partner site |
| A build while ffbox CI is actually down (with Ben's OK), or a special build Ben explicitly asks for that must not be a master bump | [[mp-beta-deploy]] (last-resort fallback) | built on the M5, uploaded with steamcmd, set live on the branch ffbox would have set |
| Local test players only, nothing uploaded | `honest-coop-play` / `LocalMultiplayerVerificationBuild` | local players |

Both skills still run **only when Ben or Lothsahn asks**, never on an agent's own initiative.

**ffbox CI is THE way to build releases and is expected to work** (Lothsahn, 2026-09-28). A player
that fails there is reported with the job log's reason and fixed through [[ci-release]], never
quietly swapped for an M5 build. History: the 2026-09-27 Mac "Disk full" failures on the
`ffghr-loth2400-*` runners (0.50.0.36/.37/.39) are fixed in ffbox.
