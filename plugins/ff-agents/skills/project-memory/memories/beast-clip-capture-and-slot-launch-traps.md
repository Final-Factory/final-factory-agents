# Recording clips on BEAST: no desktop frames, and two slot-pool launch traps

**Learned:** 2026-09-30, w139, recording before/after clips of built players on BEAST from a sandbox agent.

1. **`record_clip` (ddagrab) can hang with a 0-byte file.** Desktop duplication delivered no frames at all that
   night (a plain `ffmpeg -filter_complex ddagrab=... -t 2` wrote nothing in 25 s; the display was most likely
   asleep). Another agent's fullscreen borderless player was also on the one display. Do not fight it: record
   the game's own frames instead. Launch the player with
   `-ffFeelProbe <csv> -ffFeelFrames <dir> -ffFeelFramesAt 0+50 -ffFeelFramesWidth 1280 -ffFeelVsync 0
   -ffFeelFps 60` (`Diagnostics/FeelFrameCapture.cs`), fire the effect over the agent channel, and assemble the
   JPGs into a constant 60 fps MP4 with ffmpeg's concat demuxer using the frame times in `frames/frames.csv`.
   `watch_video --mode vfx --onset <s>` reviews it like any other clip. Capture costs frame rate (about 45 fps at
   1280 wide), and a concurrent player build dropped a two-player run to 18 fps: record when the machine is quiet.
2. **`-ffSoloNewGame <seed>` starts a single-player game** (wait for `solo-ready` in the log). For two players use
   the automation Host/Client roles; add `-ffFeelKeysWaitPeer` so the client's capture clock starts at the join.
   The dash has one charge at the start in multiplayer: a second `ability.afterburner` 8 s later is rejected.
3. **A remote ship's dash leaves the client's screen.** The dash covers about 325 units (725 px at default zoom).
   Fly the other player to the far side first and dash it back across the view.
4. **Never pass a slot's own folder to `player_slots.py launch`.** The fingerprint of a slot's own `player` folder (`<slot root>\slotK\player`; on LothDesktop now
   `D:\work\ffw\players\slotK-P\player`)
   differs from the slot's marker, so the pool copies the build into another slot (minutes, 2 GB). Pass the
   original build folder, or accept the copy and keep passing the SAME path so later launches reuse it.
5. **`launch --detach ... | tail` does not return.** The detached player inherits the pipe. Redirect stdout and
   stderr to files and stdin from `/dev/null`, then read the JSON.
6. **A cold `build_player.sh` took 46 minutes on BEAST** (Burst's `bcl.exe` alone ran about 30), and it needs the
   sandbox editor stopped and a clean tree. Start it as soon as the fix is committed.
7. **`/v1/screenshot` of a multiplayer client came back upside down in one run.** Use the frame capture for
   anything you will show.
8. **A Windows Firewall prompt dims every desktop recording** (w157, 2026-10-01). "Do you want to allow public
   and private networks to access this app?" for some `finalfactory.exe` sat on the desktop for over an hour.
   Windows dims everything behind it, so every `record_clip` (ddagrab) clip came out dark, and the prompt itself
   covered part of a window placed mid-screen. It does not show in a window enumeration. Grab the desktop once
   (`ffmpeg -init_hw_device d3d11va -filter_complex "ddagrab=output_idx=0,hwdownload,format=bgra" -frames:v 1`)
   when a clip looks dark. Do not click it: tell Ben. `/v1/screenshot` is the game's own frame and is not dimmed;
   move player windows clear of the screen centre with `SetWindowPos`.
9. **Gemini cannot read a HUD panel or see a few-pixel ship on the full 1280x720 frame.** Blind, it reported the
   count unchanged on a clip where it dropped, and quoted error texts the game does not contain. Review crops
   instead: a 2x crop of the panel for text and counts, a 3x crop of the world for a small ship (`ffmpeg -vf
   "crop=...,scale=..."`, pass `--onset`), and say in the brief which ship is the acting one (in a client's view
   the labelled ship is the OTHER player). Keep the raw clips as the evidence and say what the crops are.
10. **A warm player build from the running sandbox editor takes 3 to 5 minutes**: schedule
   `BuildPipeline.BuildPlayer` (StandaloneWindows64, Development) on `EditorApplication.update` from
   `execute_code` and write the `BuildReport` summary to a marker file. No second Unity, no stopped editor,
   against item 6's 46 minutes cold.
11. **A clip WITH sound: automation sessions are muted, and the desktop mix is everybody's** (w160, 2026-10-01).
   `-ffAutomationRole` and `-ffSoloNewGame` mute FMOD for the whole session (`AudioController.SetAutomationMuted`,
   log line `[ffauto] audio muted for automation`): a capture of such a player is digital silence. For a clip
   with sound use a real single-player load: build the fixture world in an automation session, save it over the
   agent channel (`ffauto:game.save|<name>`), then relaunch with `-ffFeelProbe <csv> -ffFeelLoad <name>
   -ffFeelFrames <dir> -ffFeelFramesAt 0+200 -ffFeelFramesWidth 960 -ffFeelVsync 0 -ffFeelFps 60 -ffAgentControl
   true -ffAgentControlDev true` (no automation role, so not muted; the channel still drives it; delete the save
   after). Record THAT process's audio alone with WASAPI process loopback: `uv run --with proc-tap --with
   soundfile`, `ProcessAudioCapture(pid, on_data=cb).start()` gives 48 kHz stereo float32 and keeps delivering
   through silence, so sample count is time. A machine-wide loopback (`soundcard`) also records every other
   agent's game. Both clocks are QueryPerformanceCounter (`frames.csv` `t_ns` is Stopwatch; Python
   `time.perf_counter_ns()` is the same counter), so stamp the first audio chunk and each `ffauto` fire with
   `perf_counter_ns()`, cut frames and samples by the same marks, and mux. The music stays on (PlayerPrefs are
   shared by every checkout on the machine: do not change volumes), so take sound onsets from the review, not
   from a loudness envelope.
