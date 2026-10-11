# The m5 manual build: Windows + Mac main, set live on development, by hand

**When:** only while Ben has moved develop builds to his m5. Ben, 2026-10-10 (w930), verbatim:
"for the next build, please just do the process on my m5 and just do the windows and mac builds (we
dont need demo or linux builds yet) ffbox is having issues with build speed so we are going to
manually use my m5 for builds for a couple days, remember this", and "also when you do a m5 build
have all the workers stop and close out the open unity editors or game instance so we can use the
full power of my m5 to do builds. remember this". It is the one exception to "releases only through
FFBox's lane", and it covers **develop builds set live on `development` only**: never the default
branch, never pre-release, never the demo app, no Linux. When Ben or Lothsahn says FFBox builds again,
go back to `SKILL.md` section 1.

First run: Build 97 (0.50.0.97, bump `ca8185dd6`, w930, 2026-10-11). Every number below is from it.

## 1. Clear the m5 first

- The dispatcher asks the other m5 workers to commit, push, close their editors and players and end
  their turns. Check yourself before any Unity build:
  `ps -axo pid,etime,command | grep -E "Unity.app/Contents/MacOS/Unity |finalfactory" | grep -v AssetImportWorker`
  and `unity-slot status`.
- Quit any FF Factory sandbox editor or player still running cleanly (`mcp__machine__unity` stop for
  a sandbox's editor; AppleScript quit or SIGTERM for a player; kill -9 only after 2 minutes of being
  ignored). **Never touch Ben's own editor** (`-projectpath /Users/benryding/nevergames/FinalFactory`)
  or his main clone: leave it and say so in the report.
- When the upload is done, say in a turn report that the other m5 workers can be resumed.

## 2. Bump develop with `--skip-ci`, so FFBox builds nothing

```sh
scripts/trigger-ci-release.sh develop --skip-ci --notes Temp/release-notes-<version>.md
```

The bump commit's message gets a `[skip ci]` line. GitHub then starts no `main.yml` run for that
push, and FFBox's release lane only ever acts on a CI job's request (ffbox `scripts/release_lane.py`
`decide()` answers the job's `release.info`; `ci_lane.py` calls it), so FFBox builds, uploads and sets
live nothing for that version. Check it: `gh run list -R Final-Factory/FinalFactory -c <bump sha>`
prints `[]` (Build 97: `[]` 45 s after the push).

Not the other way: a bump that also changes `cicd/depot_build_*.vdf` (the Build menu's mark) still
makes FFBox **build** both editions for symbols, only skipping the upload (`release_lane.py:99-101,
389, 1041`), which is the load Ben is moving off FFBox.

**No release run means no test gate.** Dispatch the suite on the bump commit and report it beside
the build (it never releases, `main.yml` header):
`gh workflow run main.yml -R Final-Factory/FinalFactory --ref develop`. Ben's rule for these builds:
don't hold the upload for it, report any real failure.

`release-status.py` cannot see a manual build (it reads the release run and FFBox's ledger). Verify
on Steam instead (section 5).

## 3. Build both players with Editor.ReleaseBuild, the way FFBox does

Not Build and Upload All: `BuildCommand2` builds the demo too, finds `steamcmd.exe` through a
`;`-split PATH (Windows only), and sets nothing live. `Editor.ReleaseBuild.Build` is FFBox's own
per-player entry point (ffbox `scripts/ffrelease-build.sh`): localization harvest + font rebake,
Addressables, the player with `BuildOptions.None`, Localization copied in, the Burst
`*_DoNotShip` folder moved out to `symbols/`.

In your sandbox, on the bump commit (`git merge --ff-only origin/develop`), editor stopped, one
target per batchmode session (it never switches target itself), each under `unity-slot`:

```sh
U=/Applications/Unity/Hub/Editor/6000.3.19f1/Unity.app/Contents/MacOS/Unity
export MONO_GC_PARAMS=nursery-size=1g        # FFBox's Burst speed-up, same line
for T in win64:StandaloneWindows64 osx:StandaloneOSX; do
  k=${T%%:*}; bt=${T#*:}
  unity-slot run --label "<wNNN> Build <R> $k main" -- "$U" -batchmode -quit -nographics \
    -projectPath "$PWD" -buildTarget $bt -executeMethod Editor.ReleaseBuild.Build \
    -ffEdition main -ffOut "$TMPDIR/b<R>/$k" -logFile "$TMPDIR/b<R>/$k.log" || break
done
```

Run it in the background and wait on its exit. Each `-ffOut` gets `player/` (exactly what ships),
`symbols/` and `release-build.json` (`result`, `build_errors`, `phases` in seconds).

Times (Build 97, m5, Apple M5 Pro, nothing else building): Windows 23.5 min (player step 1262 s; the
sandbox had never been imported for Windows, so this includes a full import), then Mac 7 min (player
346 s). Bump to live: 33 min (02:58 to 03:31 UTC).

`release-build.json` counted 8 `build_errors` on each (NullReferenceException from
`EntitiesGraphicsSystemUtility.RootsHandlerDelegate` and `RenderTexture.Create failed`): the headless
editor opening `main.unity` in `BuildCommand2.SetDemoMode`, not the player. FFBox ignores that count
too. Run FFBox's own check on each output (it reads `<dir>/release.json`, `<dir>/release/` and
`<dir>/build.log`):

```sh
mkdir -p chk/win64 && ln -sfn "$TMPDIR/b<R>/win64" chk/win64/release && ln -sf "$TMPDIR/b<R>/win64.log" chk/win64/build.log
echo '{"target":"win64","edition":"main","exit":0,"version":"<version>"}' > chk/win64/release.json
python3 -I <ffbox clone>/scripts/ffrelease-check.py chk/win64 --version <version>     # win64: GOOD
```

(the same for osx). Both were GOOD on Build 97.

The harvest and the bundleVersion sync can leave tracked files changed in the sandbox (FFBox would
open its `ffbox/release-<version>-regenerated` PR for them). Commit any that changed on a branch and
open a PR into develop for them. On Build 97 they were the same seven files FFBox's release PRs carry
(`main.unity` and the Noto Sans JP/KR/SC atlases and character sets; #1377, #1387, #1421): PR #1441.

## 3b. The stills come from the release player through Agent Control

A release player has no Deck tour (`DeckTour.cs` refuses without `Debug.isDebugBuild`). Start it
through `scripts/nightly/player_slots.py launch` with `-ffAgentControl true`, which starts the agent
HTTP channel and every `ffauto` command in a release build (`AgentControlRelease.cs` header), and
drive and capture through that channel (`/v1/screenshot` gives a whole-screen PNG; add
`-ffAgentControlDev true`, and every still shows an "Agent control ON" chip at the top). What Build 97
taught (w930):
- `player_slots.py launch --detach <player> -- <args>`: `--detach` goes BEFORE the player path, or the
  launch blocks.
- The player ignores `-screen-width/-screen-height`; it takes the size from the stored prefs
  (`com.Never-Games.finalfactory` `ResolutionWidth/Height`). Save them, set 1920x1080, put them back.
- The channel only takes commands while a game is playing, so the title screen and New Game options
  cannot be driven through it. Start a game with the tutorial on as `-ffSoloNewGame <name>
  -ffSoloObjectives Normal` (Tutorial ON is `ObjectivesMode.Normal`, `NewGameOptionsPanel.cs:66`) and
  off without the second flag. A New Game screen still needs OS clicks, so a locked Mac (Ben away)
  cannot give one: say so.
- `ffauto:wait` runs on game time and stalls while the Esc menu pauses the game.

**The whole Normal tutorial, solo, in 6 minutes** (Build 98, w949: the tutorial-end clip). w923's
two-player tutorial runner also plays one host: every recipe whose `by` is not a peer goes to the host
(`tutorial_play.py` `actor`). Put an uncommitted scenario in `scripts/nightly/scenarios/` (the runner
only reads that folder) shaped like `MP-tutorial-e2e-loth.json`, with `"mode": "sp"`,
`"peers": ["host"]`, `"peerArgs": {"host": ["-ffTutorialTrace", "true"]}` and the assert's
`"peers": ["host"]`, and run
`python3 scripts/nightly/ffnightly.py run --player <out>/osx/player/finalfactory.app --sha <bump sha>
--scenario <id> --no-retry --invariants off --out "$TMPDIR/tut"` (it launches through the player slots).
Two things the solo run needs, both measured on Build 98:
- **The seed `nightly-tutorial-e2e`**: the recipes' coordinates are that world's (another seed: step 2
  "mining.until stopped at 0/8 Bauxite Ore").
- **A recipes copy whose step 24 `prep` also adds `ffauto:inventory.add|Low Density Structure|2`**: in
  two-player the client carries them; solo, the host's hand crafts used them up and the drop-in was
  refused (`InventoryTransfer ... NothingInSource`), stopping the run at step 24.
Then all 40 steps PASS (`tutorial-report.md`, 0 failures), and the host log's `[TutorialTrace]` `reveal`
and `sub show` lines, mapped to titles through `scripts/nightly/tutorial-normal-steps.json` by `uid`,
give the order of cards and voice lines. For the clip, poll `/v1/screenshot?maxEdge=960` once a second
beside the run (port and token from `AgentControl/session-<pid>.json` in the game's data folder) and
join the frames with ffmpeg's concat demuxer at their real times. It is about 1 fps, not a 60 fps capture:
say so. Delete the two uncommitted files afterwards.

## 4. Upload the main app's two depots, set live on development

steamcmd on the m5 runs with its own home, `HOME=/Users/benryding/.steamcmd-home`, as `slims20`,
with the token Ben's last sign-in cached (`steam-upload` skill). Test it first, with no tty so a
missing token fails instead of prompting:

```sh
HOME=/Users/benryding/.steamcmd-home steamcmd +login slims20 +quit < /dev/null
```

`Logging in using cached credentials` ... `OK` means no sign-in is needed. Anything else: stop.
Never read, print or copy `cicd/credentials.txt`, never handle a password. Tell Ben to open
Terminal on the m5 and run `HOME=/Users/benryding/.steamcmd-home steamcmd +login slims20`, type his
password and approve Steam Guard, then `quit`; end the turn with `waiting_on_person` (Ben).
A steamcmd login replaces the Steam desktop app's session on the m5: tell Ben to restart Steam after.

Write the vdfs in `$TMPDIR` (never the tracked `cicd/` ones), in FFBox's form (ffbox
`scripts/ffsteam.py` `depot_vdf` / `app_vdf`): app 1383150, depots **1383152 = Windows**
(contentroot `<out>/win64/player`, `finalfactory.exe` executable) and **1383151 = Mac**
(`<out>/osx/player`), `FileExclusion` `*DoNotShip*` and `*.exclude`, `"setlive" "development"`,
`"desc"` = `<version> (<sha9>): <steam_description line>` (no `"` or `\`, at most 200 characters).
Then:

```sh
HOME=/Users/benryding/.steamcmd-home steamcmd +login slims20 +run_app_build "$S/app_1383150.vdf" +quit < /dev/null > "$S/steamcmd.log" 2>&1
grep "Successfully finished AppID 1383150 build" "$S/steamcmd.log"     # (BuildID <n>)
```

Build 97: the cached token logged in, both depots uploaded in about 40 s (chunk dedupe), and the
log ended `Successfully finished AppID 1383150 build (BuildID 25859327)`. The `depot_build_*.log`
files in `buildoutput` name each depot's `New manifestID`.

## 5. Verify on Steam, then the rest of the release

```sh
steamcmd +login anonymous +app_info_update 1 +app_info_print 1383150 +quit < /dev/null | awk '/"branches"/,/^\t\t}/'
```

`development`'s `buildid` must be the BuildID from the upload log and its `timeupdated` the upload's
time (anonymous login, default home: it lists development, measured on Build 97). Report the
BuildID before and after, and compare each depot's `development` `gid` in the same output with the
`New manifestID` in the upload's `depot_build_<depot>.log` (Build 97: development 25856972 to
25859327 at 03:31:02 UTC, both gids equal to the new manifests).

`python scripts/release-status.py <version>` reads Steam correctly but its VERDICT is wrong for a
`[skip ci]` build: it takes the dispatched test run as the release run and says "A Release job
failed" because that run's `Release` job is skipped (Build 97). Quote its Steam lines and the test
result; say the verdict does not apply to a manual build. The patch notes (section 3), the UI stills of the built players (launch only
through `scripts/nightly/player_slots.py`) and the first-hour check (section 4) are unchanged, except that **the m5 cannot read the
crash/desync intake**: it has no ffdiscord token (`ffdiscord.py read` says "no bot token"), the
portal's logs carry no report intake, and `fetch_ffbox_report` needs an id. Ask the orchestrator
for `ffbox_activity` reports/signatures for the version at the hour mark, fetch any report it names
by id, and confirm the BuildID on `development` yourself (Build 97).
