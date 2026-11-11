## A desync in Gherik's mod gets a fix PR on the mod's repo

**Rule.** When a desync's cause is in a mod owned by Gherik (the Gherik1 GitHub org), get the mod's source through the
gherikmodaccessor App ([fetch the source through app-gherik](settle-your-own-guesses.md#mod-code-fetch-the-source-through-app-gherik-before-steam-workshop-or-steamcmd-w2755-2026-11-01))
and open a pull request with the fix on the mod's repo. Base it on the mod's `develop` branch when that is ahead of
`master`. The description gives the desync report ids, what differs between peers, and why the fix is deterministic.
Propose only: never merge, Gherik reviews. No person's permission is needed. A Modding-Support doc note alone is not
enough; one may go alongside the PR. If the App cannot open the PR, attach the patch to your report with
`publish_attachment` and say so.

**Why.** lothsahn: "for mods owned by Gherik we can always propose fixes for his desyncs" and "If so and a mod you have
access to with Gherikmodaccessor, please propose a PR to fix it. It may be in a develop branch of the mod". A worker that
only wrote the cause into a doc note left the desync open.

**How to apply.** Clone from the App, `git log origin/develop..origin/master` and `origin/master..origin/develop` to see
which branch is ahead, branch from it, fix, `gh pr create` on the mod's repo (the shim uses the App's token; never print
it). Name the PR in your report.
