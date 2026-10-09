---
name: linux-headless-player-screen-check
description: Checking a built player's screen size and UI fit headlessly on a Linux machine (Xvfb needs a window manager or the grab looks like a resolution bug), the no-root recipe, player_slots.py with a Linux build, and the batch-mode route when a fresh sandbox's Unity MCP bridge never comes up.
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
- Whole-screen stills: Pillow `ImageGrab.grab(xdisplay=':77')`. Clips: a static ffmpeg
  (johnvansickle.com release build) `-f x11grab -framerate 60 -video_size 1280x800 -i :77`. Clicks: XTest through
  ctypes (`libXtst.so.6` `XTestFakeMotionEvent`/`XTestFakeButtonEvent`); no xdotool.
- `XDG_CONFIG_HOME=<run dir>` gives the player its own PlayerPrefs (`<run dir>/unity3d/Never Games/finalfactory/prefs`,
  plain XML, so a stuck state can be seeded). Without it the player writes `~/.config/unity3d/...`, which every
  editor on the machine shares.
- End the player with `timeout -s TERM <s>` around the launch (or the game's `-ffSoloQuitAfterSeconds`, see
  [visual-check-players-must-quit-themselves](visual-check-players-must-quit-themselves.md)); the harness refuses
  killing a Unity-named process by hand.
- An X11 full-screen stretch maps input along with the image, so missed clicks from a gamescope/Proton scaling
  mismatch do not reproduce this way.

**`scripts/nightly/player_slots.py` and a Linux build:** given the build folder it says "not a Windows or Mac
Final Factory player; launching it as is" and then `execv`s the directory (`PermissionError`). Pass the
`finalfactory.x86_64` executable; it still launches from where it is, not from a slot (no firewall prompt on Linux).

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
