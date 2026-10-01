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
4. **Never pass a slot's own folder to `player_slots.py launch`.** The fingerprint of `D:\work\ff-players\slotK\player`
   differs from the slot's marker, so the pool copies the build into another slot (minutes, 2 GB). Pass the
   original build folder, or accept the copy and keep passing the SAME path so later launches reuse it.
5. **`launch --detach ... | tail` does not return.** The detached player inherits the pipe. Redirect stdout and
   stderr to files and stdin from `/dev/null`, then read the JSON.
6. **A cold `build_player.sh` took 46 minutes on BEAST** (Burst's `bcl.exe` alone ran about 30), and it needs the
   sandbox editor stopped and a clean tree. Start it as soon as the fix is committed.
7. **`/v1/screenshot` of a multiplayer client came back upside down in one run.** Use the frame capture for
   anything you will show.
