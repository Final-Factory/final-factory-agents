# Which build skill

Updated 2026-09-26 (Lothsahn changed the pipeline): develop's players ship multiplayer
(`FF_ENABLE_MULTIPLAYER_BUILD` in develop's ProjectSettings, FinalFactory #613/#614), and ffbox
`a7809f9e1` sets a develop release's main app live on `multiplayer-closed-beta` as it uploads. So a
normal develop CI release IS the MP closed-beta build. The older rule ("ci-release is public-only,
multiplayer hidden, never for testers") is gone.

Decision table:

| Ask | Skill | Result |
|---|---|---|
| A new MP / closed-beta / testers / friends build | [[ci-release]] on **develop** | ffbox builds all four players; main goes live on `multiplayer-closed-beta` by itself, demo is uploaded with nothing live |
| A public release | [[ci-release]] on **master** | ffbox uploads with nothing set live; Lothsahn or Ben promotes it by hand |
| A beta build while ffbox CI is actually down (with Ben's OK), or a special build Ben explicitly asks for that must not be a develop release | [[mp-beta-deploy]] (last-resort fallback) | built on the M5, uploaded with steamcmd to `multiplayer-closed-beta` |
| Local test players only, nothing uploaded | `honest-coop-play` / `LocalMultiplayerVerificationBuild` | local players |

Both skills still run **only when Ben or Lothsahn asks**, never on an agent's own initiative.

**ffbox CI is THE way to build releases and is expected to work** (Lothsahn, 2026-09-28). A player
that fails there is reported with the job log's reason and fixed through [[ci-release]], never
quietly swapped for an M5 build. History: the 2026-09-27 Mac "Disk full" failures on the
`ffghr-loth2400-*` runners (0.50.0.36/.37/.39) are fixed in ffbox.
