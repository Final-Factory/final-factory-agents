---
name: watch-video
description: Watch a video WITH its sound and judge it like a viewer, and record + review 60 fps clips of visual effects. For a trailer cut or capture take, watch_video measures cuts, shot length, lingering and dead air, jump cuts, reused footage, tight framing, stacked action, the beat grid, exact music edits and loudness. For an effect (record_clip + watch_video --mode vfx) it measures the effect's lifetime, pops, one-frame snaps, flicker and judder, steps through every frame, and compares against the approved or before clip side by side. Gemini reviews the whole clip blind. Use before any trailer or video goes to Ben, and to verify ANY change to VFX, shaders, particles, animations, camera feel or other visual presentation (screenshots alone never count).
---

# watch-video: review a video the way a viewer would

Frame grabs and shot lists miss what a viewer notices at once: a shot that sits after the player
stops, a music chop, combat that is one clump of enemies, a camera that is too close. This skill
measures those things with timestamps, gets a whole-video opinion WITH sound, and hands you the
images to judge the rest yourself.

## Visual effects: record a clip, then review it (the rule)

Any change to visual effects, shaders, animations, particles, camera feel or other visual presentation is
verified with short **60 fps clips, before and after**, from gameplay angles, covering the effect's whole
lifetime, reviewed with `watch_video --mode vfx` against a written description of the intended look, plus
stepping through the frames. **Screenshots alone do not count.** The PR links the clips and the review
report. Once Ben has approved a look, compare against that approved clip, not just the previous build.

1. **Write the intended look** in a few lines (`look.md`): shape, size next to the ship, colours, how it
   starts, how long it lasts, how it ends, what it must not do.
2. **Record before and after** with `record_clip`. It records in real time what the screen shows (the
   simulation runs on wall-clock heartbeats, the VFX clock on frame time, so a frame-by-frame offline
   recorder like Unity Recorder would put them out of step):
   ```sh
   record_clip --player --effect afterburner --name ab_before            # a built player, over its agent channel
   record_clip --player --effect afterburner --name ab_after --review "$(cat look.md)" --compare <ab_before.mp4>
   record_clip --unity --name frenzy --seconds 4 --lead 1 --crop W:H:X:Y  # the editor: fire it yourself (MCP) when RECORDING prints
   ```
   Named effects (`--effect`): `afterburner`, `engine`, `bat-exhaust`, `plasma`, `frenzy`, `guardian`,
   `obliterator`. They send `ffauto:` verbs over the game's agent channel, so the player needs
   `-ffAgentControl true -ffAgentControlDev true` and must be launched from the slot pool. `--do
   "ffauto:..."` fires any other command, and `--pre` runs set-up first. Frame the effect first (e.g.
   `ffauto:camera.zoom|600`, UI hidden). The clip is a constant-60-fps MP4 in `<tmp>/vfx_clips/`, with
   `<clip>.json` recording when the effect fired. `watch_video` anchors on that time.
3. **Review** (`--review`/`--brief` runs it for you): `watch_video clip.mp4 --mode vfx --brief look.md
   [--compare approved.mp4] [--frames 2.4-3.1]`. Read `report.md`, then LOOK at `frames.jpg` (every
   frame of the effect's life, numbered), `sheet.jpg`, `compare.jpg` (the reference and this clip side
   by side, row by row from each onset), and `gemini.md` (a blind review at 10 fps; about $0.01 a clip).
4. **Put in the PR**: the before/after (or approved/after) clips, `report.md`, and your verdict against
   each line of the intended look, with frame numbers.

VFX flags: `SNAP` (the picture changes abruptly mid-effect: a part appears or vanishes in one frame),
`POP_IN` / `POP_OUT` (full strength within a frame; no fade), `FLICKER`, `STUTTER` (repeated frames
while moving), `EFFECT_CUT_OFF` / `EFFECT_MISSED_START` (record longer / raise `--lead`), `NO_EFFECT`.
On the Afterburner v2 capture it found the big plume collapsing into the thin trail in one frame
(f164 to f165), and Gemini, reviewing blind, described the same moment.

Recording notes:
- **macOS**: ScreenCaptureKit (`mac/sckrec.swift`, compiled on first use) records the window even
  when it is covered, but delivers ~58 fps with gaps, so ~25% of frames are repeats. Judge judder on
  Windows.
- **Windows**: `ddagrab` records the window's client area off the monitor, so keep it on top and
  unobstructed (toasts and overlapping windows are recorded). It must run in the logged-in desktop
  session: over ssh, launch it with `schtasks /create ... /it` then `schtasks /run`.
- **Editor Game view crop** (macOS, docked Game view): `execute_code` → `var gv =
  Resources.FindObjectsOfTypeAll(typeof(Editor).Assembly.GetType("UnityEditor.GameView"))[0] as
  EditorWindow; var m = EditorGUIUtility.GetMainWindowPosition(); var k =
  EditorGUIUtility.pixelsPerPoint; return $"{(int)(gv.position.width*k)&~1}:{(int)((gv.position.height-43)*k)&~1}:{(int)((gv.position.x-m.x)*k)}:{(int)((gv.position.y-m.y+71)*k)}";`
  (71 = the 28 pt title bar + the 43 pt tab row and Game toolbar). Check the first frame of
  `sheet.jpg`, and adjust if the layout differs.
- The editor throttles when it isn't focused, and a covered editor may render slowly. A built player
  from the slot pool gives the truest clip.
- **Sound**: `record_clip` records video only, and a player started with an automation role is muted.
  For a clip with sound, and on a desktop shared with other agents' windows, record the game's own frames
  and that one process's audio: project-memory `beast-clip-capture-and-slot-launch-traps`, items 1 and 11.

## Run it

```sh
watch_video <video> [--music ff] [--ref steam] [--brief brief.md] [--out <dir>]
```

`watch_video` is on PATH after `registerAgents.sh` (Windows: `watch_video.cmd`). Without the
launcher: `uv run --script <this skill's base directory>/watch_video.py ...`. Needs `uv` and
`ffmpeg`/`ffprobe`. The first run installs its Python packages (numpy, OpenCV, librosa,
PySceneDetect, Pillow) into uv's cache, which takes about a minute. It runs on macOS (M5) and on
Windows (BEAST). A 45 s cut takes ~25 s plus ~30 s for Gemini.

| Option | Use |
|---|---|
| `--music ff` | The game's soundtrack (`<FinalFactory checkout>/Assets/Audio/Music`, or `$FF_REPO`). Also takes a track file or a folder. It finds which track plays at every moment and where every music edit is, frame-exact. Without it, music edits cannot be verified. Pass it whenever the music comes from a file you have. |
| `--beats grid.json` | The editor's own beat list (seconds, source-track time) instead of the tracked grid. |
| `--ref steam` | Compare against Final Factory's three official Steam trailers (downloaded and measured once, cached in `~/.cache/watch_video`). Also takes any video or an earlier `report.json`. Repeatable. |
| `--brief file` | What the cut must do (a capture plan or EDL notes). Gemini judges against it and the report quotes it. |
| `--model none` | Skip Gemini (free, offline). Default `auto`: run it when a key exists. |
| `--segment 12-30` | Send only that part to Gemini, to save cost on long videos. |
| `--gemini-model`, `--gemini-fps` | Default `gemini-3.8-flash` at 2 frames/s. |
| `--daily-limit 5` | Hard cap on Gemini spend per day in USD (ledger `~/.config/ff-watch-video/spend.json`). |
| `--sheet-fps 4` | Contact-sheet frames per second (12 in vfx mode). |
| `--mode vfx` | A short effect clip, not a cut: no pacing or music flags; effect lifetime, pops, snaps, flicker, judder; `frames.jpg`. Gemini at 10 fps. |
| `--compare clip` | vfx mode: the reference (before, or Ben's approved look). Side-by-side `compare.jpg`, a stats table, and Gemini sees both. |
| `--frames 2.4-3.1`, `--onset 2.4` | vfx mode: step through every frame in a window; when the effect fired (read from `record_clip`'s `<clip>.json` otherwise). |

## Then look at it (the part that needs you)

The tool writes `<out>/report.md` (default out: `<system temp>/watch_video/<name>/`). Read it, then:

1. **Look at `timeline.png`.** It shows every cut (green on the beat, red off it), the waveform
   with the beat grid, music edits (magenta), loudness, camera speed, on-screen change and the
   still stretches (red band) on one time axis. Also look at `overview.jpg` (every shot on one row).
2. **Open the contact sheet of every flagged shot** (`sheets/shot_NN.jpg`). Each frame is stamped
   with its time, camera speed and change, and marked STILL where nothing moves. Judge what the
   numbers cannot:
   - Is the combat believable, with enemies spread out and fighting? Or is it a ball of enemies
     on one spot?
   - Does the subject read? Does the frame show enough of the world?
   - Is a "build" a real structure going up, or two parts popping in?
   - Does the shot do what the brief asks?
3. **Read `gemini.md`.** Gemini watched and listened to the cut blind: it got the brief, never the
   flags. So a flag marked "[the blind model review heard/saw this too]" has two independent
   witnesses. Its "model-only" findings need checking on the sheets before you act on them.
4. **Write the critique:** for each problem, the time, what is wrong, and the fix. Lead with what
   Ben would notice first.

## What each flag means

| Flag | Meaning | How reliable (validated 2026-09-29, below) |
|---|---|---|
| `LINGER` | A shot keeps running after its motion stopped: the camera and the action both went still. | High |
| `DEAD_AIR` | A still stretch inside a shot. | High |
| `STATIC_SHOT` | The whole shot barely moves. On the end card: the card sits on footage that stopped. | High |
| `MOTION_DIES` | Motion fades to a fraction of the shot's peak before the cut (a slowing player). | Not yet seen in the test cuts |
| `ACTION_CLUMP` | All on-screen change sits in ~3% of the frame while the camera is still: stacked enemies, a lone effect, or a build that pops in. | High for static shots. **Blind to a clump the camera is moving over**, so check combat sheets yourself. |
| `MUSIC_EDIT` | The music jumps inside or between tracks (needs `--music`). Says whether it is on the bar, mid-phrase, on a picture cut, and the level step. | Exact (4/4 edits found; 0 false) |
| `MUSIC_EDIT?` | A possible edit, without `--music`: unverified. | Low |
| `OFF_BEAT` | A cut is more than 20% of a beat from the beat grid. | Good with `--music` (22/22 cuts correct) |
| `JUMP_CUT` / `REPEATED` | ORB feature matching: the next shot, or a later one, shows the same view. | High |
| `TIGHT` | Typical detail is ≥ 14% of the frame width: the camera is close. Planets and big titles also trigger it. | The weakest signal (5/9 right): always confirm on the sheet |
| `STUTTER` | Repeated frames while moving (a dropped game frame). | Measured, not eyeballed |
| `FLASH_CUT`, `LOUDNESS`, `PEAK`, `MUSIC_END` | A shot under 1 s; integrated loudness off −14 LUFS; true peak above −1 dBTP; music that stops dead. | Measured |

"Too zoomed in" is judged against Ben's taste (wide), not against the Steam trailers: those are far
tighter (detail 28-45% of the width, against ~6-10% for the wide shots Ben approved). The reference
table still shows their pacing (median shot 1.4-2.2 s), motion and loudness.

## Gemini: key, cost, limits

- Configured on the M5 and BEAST (2026-09-29). The key lives ONLY in `~/.config/ff-watch-video/gemini.env` (`GEMINI_API_KEY=...`, mode 600), or
  in the `GEMINI_API_KEY` env var. **Never** commit it, print it, or paste it into a report, PR or
  chat (write `AQ.…`). On a machine without the file the tool simply skips Gemini.
- A new machine: copy the file over ssh from one that has it (`scp ~/.config/ff-watch-video/gemini.env
  <host>:.config/ff-watch-video/`), then `chmod 600` it; on Windows it is
  `%USERPROFILE%\.config\ff-watch-video\gemini.env`, restricted with
  `icacls <file> /inheritance:r /grant:r %USERNAME%:F`. Never type or paste the key itself.
- The daily cap and its ledger (`spend.json` beside the key) are per machine.
- It uploads a 720p proxy through the Files API, samples it at 2 fps, then deletes the upload.
  A 45 s cut costs **~$0.02** (about 10k tokens in, 4k out). The tool estimates the cost first and
  refuses once today's spend would pass `--daily-limit` (default $5). The report prints the actual
  cost from the API's token counts.
- Prices are hard-coded in `PRICES` from ai.google.dev/gemini-api/docs/pricing (2026-09-29).
  Gemini 3.8 Flash doubles its price on 2027-01-01, so update the table then.
- Tested behaviour: given the machine flags, Gemini agreed with every one, including a false one.
  So it gets none: it reviews blind, and the tool cross-checks afterwards. Blind, it catches content
  problems well: UI clutter, stray tooltips, a build that is two modules, screen direction against
  the brief, floating-text spam. In three runs it **never heard a music edit**, and it caught the
  v4 stacked-enemy rings in one run of three. The machine flags carry music and timing; Gemini and
  your own look at the sheets carry content.

## Validation (2026-09-29, the Multiplayer Update trailer cuts)

Ground truth: the build logs (`build45.log`, `build_v4.log`), the source tracks, and Ben's notes on
the cuts. Each flag was judged against its contact sheet.

- **Cuts:** v3 11/11 and v4 11/11 at the build log's times. That includes a jump inside
  near-static combat footage (PySceneDetect alone missed it), a whip transition, and a white-flash
  end card counted as one cut.
- **Precision of the flags:** v3 26/27, v4 11/14. All four false alarms are `TIGHT`: the build
  shot in both cuts, the v4 fly-out, and a borderline v4 combat shot where a planet fills the frame.

| Ben's note | v3 45 s | v4 draft |
|---|---|---|
| Too zoomed in | `TIGHT` on the three combat pieces (close on one pylon effect) and the close asteroid shot | `TIGHT` on the combat blob by the planet; 3 false alarms |
| Lingers after the player stops | `LINGER` where the pan stops at 0:12.0, the 4.4 s dead fleet shot, the crew stopping at 0:40.7, the end card over stopped footage | `LINGER` at 0:40.45 (fly-out stops), end card over stopped footage, 0.6 s dead air at 0:17.1 |
| Awkward music chops | Both edits, exact: 0:18.12 (track 0:26 → 1:21, mid-phrase, +3.3 dB) and 0:25.95 (enters 2 bars into a section) | Both edits, exact: 0:16.83 (0:19 → 2:03, off the bar, mid-phrase) and 0:38.68 (inside a shot, −17.8 dB). The draft's audio was NOT the planned one continuous run. |
| Stacked-enemy combat | `ACTION_CLUMP` + `STATIC_SHOT` on shots 4-5 | **Missed by the machine** (the camera moves). Gemini named the "stacked geometric enemy rings" in 1 run of 3. The contact sheets show it plainly. |
| Solar-panel build shot | `ACTION_CLUMP` + `STATIC_SHOT` + `LINGER` on shot 8 | The same, and Gemini: "only two small green blocks (solar panels) … instead of a ≥ 20-structure blueprint" |

## Not built yet

A local open video model on BEAST's RTX 4080 as the fallback when there is no Gemini key (e.g.
Qwen2.5-Omni-7B, which takes video and audio). It needs a GPU window when the trailer capture is not
recording, so ask the orchestrator first.

## Source

`watch_video.py` (one file; its dependencies are declared inline for `uv`), `record_clip.py` (standard
library only) and `mac/sckrec.swift`; launchers for both in `bin/`. Thresholds sit at the top of
`watch_video.py`, with the calibration they came from.
