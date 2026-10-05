---
name: built-mac-player-ui-capture-resolution-and-clips
description: Screenshotting UI in a built Mac player at 1080p/1440p/1280x800 and recording a clip (w449, m3, 2026-10-05) - the window size comes from the shared PlayerPrefs, not launch args; ff-agent wants --pid after the subcommand; build_player.sh reverts tracked edits made while it runs; the m3 agent host cannot screen-record, so use the game's own visual episode
---

# UI capture in a built Mac player: resolution, clips, and what the build undoes

w449 took 36 built-player frames per round (3 resolutions x empty/few/many stations x 4 views) and a
clip, on the m3. Recipe and traps; scripts in the game repo at
`specs/w449-mobile-station-overview/proofs/tools/` (`capture.sh`, `perf.sh`, `mp_check.sh`,
`clip_episode.sh`).

**Resolution.** `-screen-width/-screen-height` do not decide the window:
`DisplaySettingsController.LoadFromPlayerPrefs` calls `Screen.SetResolution` with `ResolutionWidth`,
`ResolutionHeight` and `FullscreenMode` (3 = windowed) from `com.Never-Games.finalfactory`, which
every copy of the game on the Mac shares (Ben's Steam install included), and `UiScale` (a float;
the game's default is 0.9) sets the UI scale. So: `defaults export <domain> before.plist`, write
the keys (`defaults write ... -int`, `UiScale -float 0.9`), launch, and `defaults import` the export
afterwards (the player also rewrites Unity's own `Screenmanager Resolution ...` keys on quit, so
restore the whole file, not just your keys). Check the live size with
`ffauto:pointer.moveto|999999|999999|screen` (its warning names the view). A windowed 2560x1440
player fits a 14-inch Retina screen (pixels, not points).

**Screenshots.** `ff-agent screenshot --pid <pid> -o f.png --max-edge 1920`: the channel caps the
long edge at 1920, so a 2560x1440 view comes back scaled (fine for layout, say so). Global flags go
AFTER the subcommand: `ff-agent cmd --pid <pid> "ffauto:..."`; `ff-agent --pid <pid> cmd` fails with
"unknown command --pid". Panels open with `ffauto:ui.open|<panel>`, tabs and switches with
`ui.click|<panel>|<path>`, a search box with `ui.set|<panel>|<path to the TMP_InputField>|text`; a
`Name[text=Station 3]` selector picks one card among clones.

**`scripts/nightly/build_player.sh` reverts tracked edits made while it runs.** It restores every
tracked file that changed during the build (`git diff --name-only` then `git checkout --`), so a
plan.md edit made in the checkout during a 7-minute build was silently undone. Edit only after the
build finishes (or in another clone), and commit first: it also refuses a dirty tree.

**Clips without Screen Recording.** On the m3 the agent host has no macOS Screen Recording
permission (`screencapture` is black, `sckrec` finds the window and writes 0 frames) and Xcode's
license is not accepted (`swiftc` exits 69, so `record_clip` cannot even rebuild its recorder;
granting either needs a person at the Mac). Use the game's own visual episode in a player launched
with `-ffAgentControlDev true`: `ffauto:visualepisode.start|<id>`, poll `visualepisode.status`
until Recording with the preflight Passed, `visualepisode.mark|<name>` before each step,
`visualepisode.stop|<reason>`. It writes 960x540 composited frames (overlay UI included) at about
89 a second under `PlaytestSessions/<label>/visual-episodes/<id>/`. Make the MP4 from
`observations.jsonl` (`realtimeSeconds` per frame) as an ffmpeg concat list with per-frame
durations, then `fps=60`; the marker times come from `manifest.json` markers matched to the nearest
`engineFrame`. Its "Invalid: cadence-minimum-below-3" is the heartbeat-motion rule, not a broken
recording. `watch_video --mode vfx` then flags every instant panel change as POP/SNAP; read them
against the step times.

**Editor nuances on the same machine.** After an editor crash, `Temp/__Backupscenes` makes every
relaunch hang on the scene-recovery modal (150 MB, 0% CPU, nothing after the licensing lines), and
the machine's `unity start/restart` tool does not clear it: remove the folder (your own crash, clean
scene in git) and start again. A Safe Mode prompt (a compile error on disk at boot) looks the same in
`sample` (`ProcessScriptsAndDomainReloadIfNeeded -> GetDialogResponseComplex`): fix the error on disk,
force-stop, start. Adding an input action edits `GameInput.inputactions`, but the generated
`GameInput.cs` may compile before the importer regenerates it; patch the wrapper the way the
generator writes it (the embedded JSON is the asset with `"version": 1` first, quotes doubled) and
confirm a forced reimport leaves it byte-identical.

Related: [[built-player-screenshot-coordinate-scale]], [[visual-capture-native-resolution-and-review]],
[[pumped-execute-code-scripts-can-wedge-the-editor]], [[feedback-built-players-run-from-the-slot-pool]],
[[station-rider-runs-and-clips-lessons-2026-10-02]] (first noted the saved display size and the restore).
