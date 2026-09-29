---
name: watch-video
description: Watch a video WITH its sound and judge it like a viewer - a trailer cut, a capture take, a gameplay clip. Runs watch_video, which measures every cut, shot length, camera motion, dead air and lingering, jump cuts, reused footage, tight framing, stacked "all in one spot" action, the beat grid and cut-on-beat accuracy, exact music edits against the source track, and loudness, then asks Gemini to watch and listen to the whole cut blind. Writes a time-stamped report, a timeline image and per-shot contact sheets for the agent to look at. Use before any trailer or video goes to Ben, in the render -> watch_video -> fix loop, or when asked to watch, review, critique or check a video.
---

# watch-video: review a video the way a viewer would

Frame grabs and shot lists miss what a viewer notices at once: a shot that sits after the player
stops, a music chop, combat that is one clump of enemies, a camera that is too close. This skill
measures those things with timestamps, gets a whole-video opinion WITH sound, and hands you the
images to judge the rest yourself.

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
| `--sheet-fps 4` | Contact-sheet frames per second. |

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

- The key lives ONLY in `~/.config/ff-watch-video/gemini.env` (`GEMINI_API_KEY=...`, mode 600), or
  in the `GEMINI_API_KEY` env var. **Never** commit it, print it, or paste it into a report, PR or
  chat (write `AQ.…`). On a machine without the file the tool simply skips Gemini.
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

`watch_video.py` (one file; its dependencies are declared inline for `uv`); launchers in `bin/`.
Thresholds sit at the top of the script with the calibration they came from.
