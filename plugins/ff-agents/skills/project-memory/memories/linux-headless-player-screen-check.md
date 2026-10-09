---
name: linux-headless-player-screen-check
description: Checking a built player's screen size and UI fit headlessly on a Linux machine (Xvfb needs a window manager or the grab looks like a resolution bug), the no-root recipe, player_slots.py with a Linux build, the batch-mode route when a fresh sandbox's Unity MCP bridge never comes up, GPU (Vulkan) rendering on Xvfb, a locked desktop's 1 frame/s, Windows players under Proton (umu) and a cold Windows build's out-of-memory on biscuit.
---

w767 (2026-10-09, biscuit): verifying that a fresh install fills a 1280x800 screen with the whole UI, in a
built Linux player, on a Linux PC with no Deck and nobody's desktop to borrow.

**The trap: Xvfb with no window manager.** Unity opens its startup window at the project default
(`PlayerSettings` 1920x1080) and then asks the window manager for full screen. With no window manager nothing
answers, so the window stays 1920x1080 at (-320,-140) on the 1280x800 screen and a grab shows its middle: the logo
and every centred panel cut on both sides. That is exactly what a resolution bug looks like; it cost a wrong
"the fix doesn't work" reading. Check `DISPLAY=:77 xwininfo -root -tree` (the player's window must be
`1280x800+0+0`) and run an EWMH window manager on the display first.

**No-root recipe** (everything under `$TMPDIR`):

- `apt-get download xvfb openbox libobrender32 libobt2 libstartup-notification0 libimlib2t64`, `dpkg -x` each into
  `root/`. `root/usr/bin/Xvfb :77 -screen 0 1280x800x24 -nolisten tcp &`; openbox needs its own libraries and
  theme: `DISPLAY=:77 LD_LIBRARY_PATH=$PWD/root/usr/lib/x86_64-linux-gnu XDG_DATA_DIRS=$PWD/root/usr/share
  XDG_CONFIG_DIRS=$PWD/root/etc/xdg root/usr/bin/openbox &` (without them it exits on "Unable to load a theme").
- Whole-screen stills: Pillow `ImageGrab.grab(xdisplay=':77')`. Clips: ffmpeg `-f x11grab -framerate 60 -video_size
  1280x800 -i :77`; on biscuit, `apt-get download ffmpeg libavdevice62 libplacebo360 libjack-jackd2-0 libopenal1
  libdc1394-25` and `dpkg -x` them, run with `LD_LIBRARY_PATH=<root>/usr/lib/x86_64-linux-gnu` (the other libav
  libraries are installed; w773), or a static build. Clicks: XTest through
  ctypes (`libXtst.so.6` `XTestFakeMotionEvent`/`XTestFakeButtonEvent`); no xdotool.
- `XDG_CONFIG_HOME=<run dir>` gives the player its own PlayerPrefs (`<run dir>/unity3d/Never Games/finalfactory/prefs`,
  plain XML, so a stuck state can be seeded). Without it the player writes `~/.config/unity3d/...`, which every
  editor on the machine shares.
- End the player with `timeout -s TERM <s>` around the launch (or the game's `-ffSoloQuitAfterSeconds`, see
  [visual-check-players-must-quit-themselves](visual-check-players-must-quit-themselves.md)); the harness refuses
  killing a Unity-named process by hand.
- This is a stand-in for the Deck, not the Deck: say so with the real-Deck line ([evidence-gate deck list](../../evidence-gate/checklists/deck.md), w770).
- An X11 full-screen stretch maps input along with the image, so missed clicks from a gamescope/Proton scaling
  mismatch do not reproduce this way.

**`scripts/nightly/player_slots.py` and a Linux build:** since w773 (game repo, 2026-10-09) it slots a Linux player like
any other: pass `finalfactory.x86_64` or its folder and it mirrors the whole folder into a slot. Before that it
`execv`'d a folder (`PermissionError`) and launched the `.x86_64` where it was.

**When a fresh sandbox's Unity MCP bridge never comes up** (the session's `UnityMCP` at `http://127.0.0.1:8080/mcp`
refused; the editor log says `[UnityMcpStdioAutoStart] UseHttpTransport pref is unset ... (first boot?)`;
`scripts/unity-bridge.py status` finds no bridge), stop the editor and use batch mode under `unity-slot run`:

- tests: `-batchmode -nographics -runTests -testPlatform EditMode -assemblyNames FFEditorTests -testFilter
  "<scripts/test_select.py's test_names joined by ;>" -testResults <xml> -logFile <log>`; the log with no `error CS`
  is the compile proof, recorded with `python scripts/hooks/cs-verified.py --how ... --log <log>`. A frame-count
  timing test can fail under `-nographics` and pass in CI (w767: `AuditWriteCommandTest`).
- a Linux player: `-batchmode -quit -nographics -buildTarget StandaloneLinux64 -executeMethod
  Editor.LocalMultiplayerVerificationBuild.BuildLinuxMultiplayerDev -ffVerificationBuildOutput <dir>/finalfactory.x86_64`
  (it deletes `<dir>` first); afterwards `git checkout -- Assets/Plugins/FMOD/platforms/linux/lib/x86_64/` (the
  target switch dirties `libfmodstudio.so.meta`). A before-build of an older commit: check out the old source files,
  move new test files that would not compile aside, build, restore.

## Rendering for real on that display, and Windows players under Proton (w773, 2026-10-09)

- **A locked desktop holds a window to about one frame a second.** biscuit's GNOME Wayland session, screen locked and
  display off (`gdbus call --session --dest org.gnome.ScreenSaver ... GetActive` → true, Mutter `PowerSaveMode` 3):
  a player on `:0` streamed its entity subscene in 180 s ("Streamed scene with 180060ms latency") at ~8 s of CPU, and
  the automation timed out at the title menu. Look at those two before trusting any frame time from `:0`.
- **GPU rendering on Xvfb:** `-force-vulkan` plus `MESA_VK_WSI_DEBUG=sw`. Vulkan still renders on RADV and Mesa copies
  the finished frame (presenting cost 3.4 % of a 70 ms frame on the Strange save; the subscene streamed in 1.0 s).
  Without the variable the player dies with "No DRI3 support detected - required for presentation". OpenGL on Xvfb
  is llvmpipe (software), useless for timing.
- **A Windows player under Proton (umu-launcher 1.4.4, UMU-Proton 10.0-4, no Steam needed):** the zipapp from
  GitHub releases, `XDG_DATA_HOME`/`WINEPREFIX` under `$TMPDIR`, `GAMEID=umu-1383150`; launch through
  `player_slots.slot_path()` then `umu-run <slot exe>`, `-logFile Z:\...` (a Windows path). It **crashes on Xvfb**
  (`Crash!!!` after input init, or at `DisplaySettingsController.LoadFromPlayerPrefs` when headless), so run it on
  `:0`, headless (`-batchmode -nographics`, nothing presented, so the lock does not throttle it). **One game per
  prefix**: a second `umu-run` in the same `WINEPREFIX` waits in `proton waitforexit`; a second peer needs its own
  prefix.
- **A cold Windows release build on biscuit (26 GB) runs out of memory**: Burst's AOT compiler reached 13.6 GB beside
  the 6.6 GB batch editor and the kernel killed it (`journalctl -k`). Burst sizes its threads from the CPU count,
  which Mono reads from the affinity mask: `unity-slot run -- taskset -c 0-7 <Unity> ...` built it.
- **Killing a player by hand:** the harness refuses a `kill` whose command line names a Unity thing, and a path under
  `~/.config/unity3d` counts. `pkill -f <pattern>` also matches the shell running it when the pattern appears
  anywhere in that command line, and exits 144: write `pkill -f "player/finalfactor[y]"`, and keep the literal path
  out of the rest of that command.
