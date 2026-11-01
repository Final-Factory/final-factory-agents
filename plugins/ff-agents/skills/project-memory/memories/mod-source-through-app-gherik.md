---
name: mod-source-through-app-gherik
description: A mod's source code (Gherik's mods, TowBot among them) comes through the GitHub App app-gherik (gherikmodaccessor) before any Steam Workshop or steamcmd download. A run's gh shim and git credential helper hand out the app's installation token by themselves; list the installation's repos, clone, and match a commit to the Workshop item by ModVersion and the item's update date and tag. Never print the token.
metadata:
  node_type: memory
  type: project
  modified: 2026-11-01T06:00:00.000Z
---

# A mod's source: through app-gherik, before the Workshop

lothsahn (2026-11-01, w2755): "You can get the towbot mod from its repo using gherikappaccessor. Please update your
skills so you can do this". The app is **gherikmodaccessor** (https://github.com/apps/gherikmodaccessor; the portal's
vault entry `app-gherik`, App ID 5375457, owned by Final-Factory). Its installation on Gherik1 (account 173949906)
covers the mod author's private repositories. w2753 (reading TowBot for unsafe memory writes) did not know this and
waited on a Workshop download from another machine instead.

Use it for any question that needs a mod's code: a crash, hang or desync report with mods loaded, a mod
compatibility question, a mod's use of the game's API.

## You do not mint anything

The portal mints the installation tokens (one hour each) and the machine's daemon hands them to runs whose grant names
the app. Such a run has `FF_GH_APP_NAMES=app-gherik` in its environment, a `gh` shim first on its PATH, and git's
credential helper for `https://github.com` set to the daemon's (`machine/ghApp.ts` in ff-factory,
`docs/github-apps.md`). For a repository the installation covers, git and gh then use the app's token; for every
other repository, the run's own `GH_TOKEN`. So:

```sh
echo "$FF_GH_APP_NAMES"                       # app-gherik: this run may use the app

# The repos it covers. `installation/repositories` names no repo, so tell the shim which installation with GH_REPO
# (any repo it covers):
GH_REPO=Gherik1/TowBot gh api installation/repositories --jq '.repositories[].full_name'

# Fetch one, into your $TMPDIR, read-only:
git clone https://github.com/Gherik1/TowBot.git "$TMPDIR/towbot"
```

Measured 2026-11-01 on lothdesktop/slot2: 11 repositories (Gherik1/PlayerUpgrades, ItemCannon, TerrainNuke,
LogisticsBayVariants, PowerPylons, Collector, FleetPatrol, TowBot, Repaint, FinalFactoryMods20, Cruiser), all
private; the clone of TowBot worked; the shim's token was an installation token (`ghs_` prefix). The node shim prints an
`ExperimentalWarning` on stderr: harmless.

- **Never print the token.** No `gh auth token`, no `cat` of the daemon's tokens file, no `git config` dump of a URL
  with it. If you must show it is there, its last four characters at most.
- **Read-only.** Never push, open a PR, comment or file an issue in Gherik1's repositories (the app has Contents and
  Pull requests write; that does not make it ours to use).
- **No `FF_GH_APP_NAMES`** (the vault entry's grants decide: roles, machines, and a share of its owner's work only or
  anyone's; a run on the machine's own gh login, with no vault GitHub token, never gets an app): a clone fails with
  "Repository not found". Say so in your report and
  hand the fetch to your orchestrator for a worker on lothsahn's work; do not go around it with another token.

## The mod is not in the list

The installation covers only what Gherik picked. A mod by another author, or one of Gherik's not added, is not
reachable this way. Then, in order: the Workshop download (a signed-in Steam client's
`steamapps/workshop/content/<app id>/<item id>`, or steamcmd `workshop_download_item`, see
`steamcmd-vs-desktop-steam-login-conflict.md`), and decompile the DLL (ilspycmd). Say in the report that the source
was not available and which repo list you checked. Asking Gherik to add a repository is a person's ask: put it in the
report for lothsahn, never contact the author yourself.

## Which commit is the Workshop version

A mod's version lives in its code, not in a tag (TowBot has no tags):

- **ModVersion**: the `IUserMod.ModVersion` property, e.g. `Assets/Scripts/TowBotMod.cs:15`
  `public FFVersion ModVersion => new(1, 50, 0, 0);`. `git log -L15,15:Assets/Scripts/TowBotMod.cs` shows each commit
  that changed it (TowBot: 1.21.1.0 at 66fe42f 2026-10-05, 1.50.0.0 at 4f8072e 2026-10-15).
- **GameVersion**: written into the mod's `manifest.properties` at build time (`Assets/Editor/ScriptBatch.cs`
  `WriteToManifestFile`: `GameVersion={FFVersion.FinalFactoryVersion}`) from the game DLLs the author dropped into
  `Assets/FinalFactoryDlls/`. Those DLLs are not committed (only their `.meta`), so **the repo cannot tell you the
  GameVersion**: read it from the report's mod list or the Workshop folder's `manifest.properties`.
- **The Workshop item**: its upload date and its game-version tag, from Steam's public API (no key):

  ```sh
  curl -s -X POST https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/ \
    -d itemcount=1 -d 'publishedfileids[0]=3830304883' |
    python -c "import sys,json,datetime as d;f=json.load(sys.stdin)['response']['publishedfiledetails'][0];print(f['title'],d.datetime.fromtimestamp(f['time_updated'],d.UTC).isoformat(),[t['tag'] for t in f['tags']])"
  ```

  TowBot, measured 2026-11-01: item 3830304883 "Tow Bot", updated 2026-10-30T18:18:30Z, tags `0.50.0`, `Mod`; the old
  item 3468597392, 2025-04-22, tag `0.20.0`.
- **The match**: the newest commit before the item's `time_updated` whose ModVersion equals the version in the report
  (TowBot 1.50.0.0 in the 0.50.0.114 crash reports: HEAD deda05d, 2026-10-15, is the last commit before the
  2026-10-30 upload). Label it sourced, not measured: the author may build from uncommitted edits. A claim about the
  bytes that ran (a layout, an unsafe write) still rests on the shipped DLL; the source tells you where to look.
